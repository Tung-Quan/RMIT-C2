import hashlib
import re
from dataclasses import dataclass
from importlib import metadata
from io import BytesIO
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import models
from app.services.storage_service import StorageService

PARSER_NAME = "pypdf"
UNSUPPORTED_PARSER_NAME = "unsupported"
PARSER_VERSION_FALLBACK = "unknown"
MAX_BLOCK_CHARS = 1200


@dataclass
class ExtractionResult:
    document_text: models.DocumentText
    skipped_cached: bool


@dataclass
class DocumentTextData:
    status: str
    parser_name: str
    parser_version: str
    raw_text: str | None = None
    blocks_json: list[dict] | None = None
    semantic_groups_json: list[dict] | None = None
    text_hash: str | None = None
    error_message: str | None = None


def document_text_payload(
    document_text: models.DocumentText,
    *,
    skipped_cached: bool | None = None,
) -> dict:
    payload = {
        "id": document_text.id,
        "document_id": document_text.document_id,
        "raw_text": document_text.raw_text,
        "blocks_json": document_text.blocks_json,
        "semantic_groups_json": document_text.semantic_groups_json,
        "parser_name": document_text.parser_name,
        "parser_version": document_text.parser_version,
        "text_hash": document_text.text_hash,
        "extraction_status": document_text.extraction_status,
        "error_message": document_text.error_message,
        "created_at": document_text.created_at,
        "updated_at": document_text.updated_at,
    }
    if skipped_cached is not None:
        payload["skipped_cached"] = skipped_cached
    return payload


def get_parser_version() -> str:
    try:
        return metadata.version("pypdf")
    except metadata.PackageNotFoundError:
        return PARSER_VERSION_FALLBACK


def get_or_create_document_text(
    db: Session,
    document: models.Document,
    *,
    parser_name: str = PARSER_NAME,
) -> models.DocumentText:
    existing = (
        db.query(models.DocumentText).filter(models.DocumentText.document_id == document.id).first()
    )
    if existing:
        return existing

    document_text = models.DocumentText(
        document_id=document.id,
        parser_name=parser_name,
        parser_version=get_parser_version(),
        extraction_status="pending",
    )
    db.add(document_text)
    db.flush()
    return document_text


def extract_document_text(
    db: Session,
    document: models.Document,
    *,
    force: bool = False,
) -> ExtractionResult:
    document_text = get_or_create_document_text(db, document)
    if document_text.extraction_status == "succeeded" and not force:
        return ExtractionResult(document_text=document_text, skipped_cached=True)

    data = build_document_text_data(file_name=document.file_name, s3_key=document.s3_key)
    apply_document_text_data(document_text, data)
    db.commit()
    db.refresh(document_text)
    return ExtractionResult(document_text=document_text, skipped_cached=False)


def build_document_text_data(*, file_name: str, s3_key: str) -> DocumentTextData:
    extension = Path(file_name).suffix.lower()
    if extension not in {".pdf", ".txt"}:
        return DocumentTextData(
            status="unsupported",
            parser_name=UNSUPPORTED_PARSER_NAME,
            parser_version="pdf-or-utf8-text",
            error_message="Automatic CV analysis supports text-based PDF or UTF-8 TXT. Other files can be reviewed manually.",
        )

    parser_name = "utf8-text" if extension == ".txt" else PARSER_NAME
    parser_version = "1" if extension == ".txt" else get_parser_version()
    try:
        file_bytes = StorageService().read_file_bytes(s3_key)
        text_hash = hashlib.sha256(file_bytes).hexdigest()
        pages = [{"page": 1, "text": file_bytes.decode("utf-8-sig")}] if extension == ".txt" else extract_pdf_pages(file_bytes)
        raw_text = normalize_raw_text(
            "\n\n".join(page["text"] for page in pages if page["text"].strip())
        )
        if not raw_text:
            return DocumentTextData(
                status="failed",
                parser_name=parser_name,
                parser_version=parser_version,
                text_hash=text_hash,
                error_message=(
                    "The document contains no extractable text. Scanned PDFs require OCR before upload."
                ),
            )
        blocks = build_blocks_from_pages(pages)
        semantic_groups = build_semantic_groups(blocks)
        return DocumentTextData(
            status="succeeded",
            parser_name=parser_name,
            parser_version=parser_version,
            raw_text=raw_text,
            blocks_json=blocks,
            semantic_groups_json=semantic_groups,
            text_hash=text_hash,
        )
    except Exception as exc:
        return DocumentTextData(
            status="failed",
            parser_name=parser_name,
            parser_version=parser_version,
            error_message=str(exc)[:2000],
        )


def apply_document_text_data(
    document_text: models.DocumentText,
    data: DocumentTextData,
) -> None:
    _set_result(
        document_text,
        status=data.status,
        parser_name=data.parser_name,
        parser_version=data.parser_version,
        raw_text=data.raw_text,
        blocks_json=data.blocks_json,
        semantic_groups_json=data.semantic_groups_json,
        text_hash=data.text_hash,
        error_message=data.error_message,
    )


def extract_pdf_pages(file_bytes: bytes) -> list[dict]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is not installed. Install backend requirements before extracting PDF text."
        ) from exc

    reader = PdfReader(BytesIO(file_bytes))
    pages: list[dict] = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append(
            {
                "page": index,
                "text": page.extract_text() or "",
            }
        )
    return pages


def normalize_raw_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_blocks_from_pages(pages: list[dict]) -> list[dict]:
    blocks: list[dict] = []
    block_index = 0

    for page in pages:
        source_page = page.get("page")
        lines = _normalize_lines(page.get("text", ""))
        heading: str | None = None
        pending: list[str] = []
        pending_method = "paragraph"

        def flush(
            current_heading: str | None,
            current_source_page,
            current_method: str,
        ) -> None:
            nonlocal block_index, pending, pending_method
            text = normalize_raw_text(" ".join(pending))
            pending = []
            if not text:
                return
            for chunk in _split_long_text(text):
                blocks.append(
                    {
                        "block_id": f"b{block_index + 1}",
                        "heading": current_heading,
                        "text": chunk,
                        "order_index": block_index,
                        "source_page": current_source_page,
                        "confidence": 0.72 if current_heading else 0.58,
                        "method": current_method,
                    }
                )
                block_index += 1

        for line in lines:
            if not line:
                flush(heading, source_page, pending_method)
                pending_method = "paragraph"
                continue
            if _looks_like_heading(line):
                flush(heading, source_page, pending_method)
                heading = line
                pending_method = "paragraph"
                continue

            is_bullet = _looks_like_bullet(line)
            if is_bullet and pending and pending_method != "bullet_group":
                flush(heading, source_page, pending_method)
            if not is_bullet and pending_method == "bullet_group":
                flush(heading, source_page, pending_method)
                pending_method = "paragraph"
            if is_bullet:
                pending_method = "bullet_group"
            pending.append(_strip_bullet_marker(line))

        flush(heading, source_page, pending_method)

    if not blocks:
        raw_text = normalize_raw_text("\n\n".join(page.get("text", "") for page in pages))
        for index, chunk in enumerate(_split_long_text(raw_text)):
            blocks.append(
                {
                    "block_id": f"b{index + 1}",
                    "heading": None,
                    "text": chunk,
                    "order_index": index,
                    "source_page": None,
                    "confidence": 0.45,
                    "method": "fallback_chunk",
                }
            )

    return blocks


def build_semantic_groups(blocks: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {
        "candidate_overview": [],
        "capability_evidence": [],
        "work_or_project_evidence": [],
        "education_training": [],
        "additional_signals": [],
        "unknown_or_general": [],
    }

    for block in blocks:
        group_name = classify_block(block)
        grouped[group_name].append(block)

    groups: list[dict] = []
    for group_name, group_blocks in grouped.items():
        if not group_blocks:
            continue
        groups.append(
            {
                "group_name": group_name,
                "text": "\n\n".join(block["text"] for block in group_blocks),
                "source_block_ids": [block["block_id"] for block in group_blocks],
                "method": "phase1_light_semantic_grouping",
            }
        )
    return groups


def classify_block(block: dict) -> str:
    text = f"{block.get('heading') or ''} {block.get('text') or ''}".lower()
    order_index = block.get("order_index") or 0

    if order_index <= 1 and _has_any(
        text, ["summary", "profile", "objective", "about", "contact", "email", "phone"]
    ):
        return "candidate_overview"
    if _has_any(
        text,
        [
            "experience",
            "intern",
            "project",
            "built",
            "developed",
            "implemented",
            "led",
            "worked",
            "research",
        ],
    ):
        return "work_or_project_evidence"
    if _has_any(
        text,
        ["education", "university", "college", "degree", "major", "gpa", "coursework", "training"],
    ):
        return "education_training"
    if _has_any(
        text, ["skills", "technologies", "tools", "framework", "programming", "database", "cloud"]
    ):
        return "capability_evidence"
    if _has_any(
        text,
        [
            "certification",
            "certificate",
            "award",
            "language",
            "github",
            "linkedin",
            "portfolio",
            "volunteer",
        ],
    ):
        return "additional_signals"
    return "unknown_or_general"


def _set_result(
    document_text: models.DocumentText,
    *,
    status: str,
    parser_name: str,
    parser_version: str,
    raw_text: str | None = None,
    blocks_json: list[dict] | None = None,
    semantic_groups_json: list[dict] | None = None,
    text_hash: str | None = None,
    error_message: str | None = None,
) -> None:
    document_text.extraction_status = status
    document_text.parser_name = parser_name
    document_text.parser_version = parser_version
    document_text.raw_text = raw_text
    document_text.blocks_json = blocks_json
    document_text.semantic_groups_json = semantic_groups_json
    document_text.text_hash = text_hash
    document_text.error_message = error_message


def _normalize_lines(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]


def _looks_like_heading(line: str) -> bool:
    if _looks_like_bullet(line):
        return False
    clean = line.strip(" :-")
    if not clean or len(clean) > 80 or clean.endswith("."):
        return False
    words = clean.split()
    if len(words) > 8:
        return False
    letters = [char for char in clean if char.isalpha()]
    if letters and sum(1 for char in letters if char.isupper()) / len(letters) > 0.65:
        return True
    return clean.istitle()


def _looks_like_bullet(line: str) -> bool:
    return bool(re.match(r"^\s*(?:[-*+]|\u2022|\u25e6|\d+[.)]|[A-Za-z][.)])\s+", line))


def _strip_bullet_marker(line: str) -> str:
    return re.sub(r"^\s*(?:[-*+]|\u2022|\u25e6|\d+[.)]|[A-Za-z][.)])\s+", "", line).strip()


def _split_long_text(text: str) -> list[str]:
    if len(text) <= MAX_BLOCK_CHARS:
        return [text]

    chunks: list[str] = []
    words = text.split()
    current: list[str] = []
    current_len = 0
    for word in words:
        if current and current_len + len(word) + 1 > MAX_BLOCK_CHARS:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
        current.append(word)
        current_len += len(word) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def _has_any(text: str, signals: list[str]) -> bool:
    return any(signal in text for signal in signals)
