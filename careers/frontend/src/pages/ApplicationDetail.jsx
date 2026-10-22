import {downloadDocument} from "../api/documents";
import { FilePlus2, FileText, MessageSquareText, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getApplication } from "../api/applications";
import { api, getErrorMessage, resolveApiUrl } from "../api/client";
import {
  deleteDocument as deleteDocumentRequest,
  getDocumentDownloadUrl,
  listApplicationDocuments,
  uploadApplicationDocument
} from "../api/documents";
import { Alert } from "../components/Alert";
import { StatusBadge } from "../components/StatusBadge";
import { DOCUMENT_TYPES } from "../constants";
import { isDirectDocumentsApplication } from "../utils/systemApplications";
import { clearFieldError, cvAnalysisSchema, fieldError, validateDocumentFile, validateForm } from "../validation/forms";

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeAnalysis(value) {
  if (!value) return null;
  return {
    ...value,
    matched_skills: asArray(value.matched_skills),
    missing_skills: asArray(value.missing_skills),
    suggested_improvements: asArray(value.suggested_improvements)
  };
}

export function ApplicationDetail() {
  const { id } = useParams();
  const [application, setApplication] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [cvText, setCvText] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [uploadType, setUploadType] = useState("CV");
  const [uploadFile, setUploadFile] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [activeDocumentId, setActiveDocumentId] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isGeneratingQuestions, setIsGeneratingQuestions] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [uploadInputKey, setUploadInputKey] = useState(0);

  const txtCvDocuments = useMemo(
    () => documents.filter((document) => (
      document.document_type === "CV" && String(document.file_name || "").toLowerCase().endsWith(".txt")
    )),
    [documents]
  );

  async function loadData() {
    setIsLoading(true);
    setError("");
    try {
      const [appResponse, docsResponse] = await Promise.all([
        getApplication(id),
        listApplicationDocuments(id)
      ]);
      setApplication(appResponse.data);
      setDocuments(asArray(docsResponse.data));
      setQuestions([]);
      setAnalysis(null);
      try {
        const resultResponse = await api.get(`/applications/${id}/ai/result`);
        setAnalysis(normalizeAnalysis(resultResponse.data));
      } catch (err) {
        if (err?.response?.status !== 404) throw err;
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [id]);

  async function uploadDocument(selectedFile) {
    const fileToUpload = selectedFile || uploadFile;
    if (!fileToUpload || isUploading) return;
    const fileError = validateDocumentFile(fileToUpload);
    if (fileError) {
      setError(fileError);
      return;
    }
    setError("");
    setSuccess("");
    setIsUploading(true);
    const formData = new FormData();
    formData.append("document_type", uploadType);
    formData.append("file", fileToUpload);
    try {
      await uploadApplicationDocument(id, formData);
      await loadData();
      setUploadFile(null);
      setUploadType("CV");
      setUploadInputKey((current) => current + 1);
      setSuccess("Document uploaded successfully.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsUploading(false);
    }
  }

  async function deleteDocument(documentId, fileName) {
    if (!window.confirm("Delete this document?")) return;
    setError("");
    setSuccess("");
    setActiveDocumentId(documentId);
    try {
      await deleteDocumentRequest(documentId);
      setDocuments((current) => current.filter((document) => document.id !== documentId));
      setSelectedDocumentId((current) => (Number(current) === documentId ? "" : current));
      setSuccess(`${fileName} deleted.`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActiveDocumentId(null);
    }
  }

  async function openDocument(documentId) {
    setError("");
    setSuccess("");
    setActiveDocumentId(documentId);
    try {
      await downloadDocument(documentId);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setActiveDocumentId(null);
    }
  }

  async function analyzeCv(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const validation = validateForm(cvAnalysisSchema, { selectedDocumentId, cvText });
    if (!validation.data) {
      setFieldErrors(validation.errors);
      setError(validation.formError);
      return;
    }
    setFieldErrors({});
    setIsAnalyzing(true);
    try {
      const payload = validation.data.selectedDocumentId
        ? { document_id: Number(selectedDocumentId) }
        : { cv_text: validation.data.cvText };
      const response = await api.post(`/applications/${id}/ai/analyze`, payload);
      setAnalysis(normalizeAnalysis(response.data));
      setSuccess("AI analysis complete");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function generateQuestions() {
    setError("");
    setIsGeneratingQuestions(true);
    try {
      const response = await api.post(`/applications/${id}/ai/interview-questions?count=5`);
      setQuestions(asArray(response.data));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsGeneratingQuestions(false);
    }
  }

  if (isLoading) return <p className="text-sm text-zinc-500">Loading application</p>;
  if (!application) return <Alert>Application not found</Alert>;

  const isDocumentLibrary = isDirectDocumentsApplication(application);
  const documentsSection = (
    <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2">
        <FilePlus2 className="h-5 w-5 text-zinc-700" />
        <h2 className="text-base font-semibold text-zinc-950">Documents</h2>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-[150px_1fr]">
        <select
          value={uploadType}
          onChange={(event) => setUploadType(event.target.value)}
          disabled={isUploading}
          className="rounded-lg border border-zinc-300 px-3 py-2 text-sm"
        >
          {DOCUMENT_TYPES.map((type) => (
            <option key={type} value={type}>{type}</option>
          ))}
        </select>
        <input
          key={uploadInputKey}
          type="file"
          disabled={isUploading}
          onChange={(event) => {
            const selectedFile = event.target.files?.[0] || null;
            setUploadFile(selectedFile);
            if (selectedFile) uploadDocument(selectedFile);
          }}
          className="rounded-lg border border-zinc-300 px-3 py-2 text-sm"
        />
      </div>
      <p className="mt-3 text-xs text-zinc-500">
        Allowed file types follow the backend configuration. Large files or unsupported extensions will be rejected.
      </p>
      {isUploading && (
        <p className="mt-2 text-xs font-medium text-zinc-700">
          Uploading document...
        </p>
      )}
      {uploadFile && !isUploading && (
        <p className="mt-2 text-xs text-zinc-500">
          Selected: {uploadFile.name}
        </p>
      )}

      <div className="mt-4 divide-y divide-zinc-100">
        {documents.length === 0 && <p className="py-5 text-sm text-zinc-500">No documents uploaded.</p>}
        {documents.map((document) => (
          <div key={document.id} className="flex items-center justify-between gap-4 py-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-zinc-950">{document.file_name}</p>
              <p className="text-xs text-zinc-500">
                {document.document_type} - Uploaded {new Date(document.created_at).toLocaleString()}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => openDocument(document.id)}
                disabled={activeDocumentId === document.id}
                className="rounded-lg border border-zinc-200 p-2 text-zinc-700 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60"
                aria-label="Open document"
                title="Download document"
              >
                <FileText className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => deleteDocument(document.id, document.file_name)}
                disabled={activeDocumentId === document.id}
                className="rounded-lg border border-zinc-200 p-2 text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
                aria-label="Delete document"
                title="Delete document"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );

  if (isDocumentLibrary) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-950">Document Library</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Reusable CVs and supporting documents uploaded directly from job applications.
          </p>
        </div>

        {error && <Alert>{error}</Alert>}
        {success && <Alert type="success">{success}</Alert>}

        {documentsSection}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="break-words text-2xl font-semibold text-zinc-950">{application.company_name}</h1>
            <StatusBadge status={application.application_status} />
          </div>
          <p className="mt-1 text-sm text-zinc-500">{application.position_title}</p>
          {application.deadline && <p className="mt-1 text-sm text-zinc-500">Deadline: {application.deadline}</p>}
        </div>
        <Link
          to={`/applications/${id}/edit`}
          className="inline-flex items-center justify-center rounded-lg border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-800 hover:bg-zinc-100"
        >
          Edit
        </Link>
      </div>

      {error && <Alert>{error}</Alert>}
      {success && <Alert type="success">{success}</Alert>}

      <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-zinc-950">Job description</h2>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-700">{application.job_description}</p>
        {application.notes && (
          <div className="mt-4 border-t border-zinc-100 pt-4">
            <h3 className="text-sm font-semibold text-zinc-950">Notes</h3>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-600">{application.notes}</p>
          </div>
        )}
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        {documentsSection}

        <section id="ai-cv-match" className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5 text-zinc-700" />
            <h2 className="text-base font-semibold text-zinc-950">AI CV match</h2>
          </div>
          <form onSubmit={analyzeCv} className="mt-4 space-y-4">
            <label className="block">
              <span className="text-sm font-medium text-zinc-700">Uploaded .txt CV</span>
              <select
                value={selectedDocumentId}
                onChange={(event) => {
                  setSelectedDocumentId(event.target.value);
                  setFieldErrors((current) => clearFieldError(current, "cvText"));
                }}
                aria-invalid={Boolean(fieldError(fieldErrors, "cvText")) || undefined}
                className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm"
              >
                <option value="">Use pasted CV text</option>
                {txtCvDocuments.map((document) => (
                  <option key={document.id} value={document.id}>{document.file_name}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-sm font-medium text-zinc-700">CV text</span>
              <textarea
                rows="8"
                value={cvText}
                disabled={Boolean(selectedDocumentId)}
                onChange={(event) => {
                  setCvText(event.target.value);
                  setFieldErrors((current) => clearFieldError(current, "cvText"));
                }}
                aria-invalid={Boolean(fieldError(fieldErrors, "cvText")) || undefined}
                className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-900 focus:ring-2 focus:ring-zinc-200 disabled:bg-zinc-100"
              />
              {fieldError(fieldErrors, "cvText") && <p className="mt-1 text-xs font-semibold text-rose-600">{fieldError(fieldErrors, "cvText")}</p>}
            </label>
            <button
              type="submit"
              disabled={isAnalyzing}
              className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-zinc-800 disabled:opacity-60"
            >
              <RefreshCw className="h-4 w-4" />
              {isAnalyzing ? "Analyzing" : "Analyze CV"}
            </button>
          </form>
        </section>
      </div>

      {analysis && (
        <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-base font-semibold text-zinc-950">Latest AI result</h2>
              <p className="text-sm text-zinc-500">Score created {new Date(analysis.created_at).toLocaleString()}</p>
            </div>
            <div className="text-3xl font-semibold text-zinc-950">{analysis.match_score}%</div>
          </div>
          <div className="mt-4 h-3 overflow-hidden rounded-full bg-zinc-100">
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${analysis.match_score}%` }} />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <SkillList title="Matched skills" skills={analysis.matched_skills} tone="emerald" />
            <SkillList title="Missing skills" skills={analysis.missing_skills} tone="rose" />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold text-zinc-950">Suggested improvements</h3>
              <ul className="mt-3 space-y-2 text-sm text-zinc-700">
                {analysis.suggested_improvements.length === 0 && (
                  <li className="rounded-lg bg-zinc-50 px-3 py-2 text-zinc-500">None</li>
                )}
                {analysis.suggested_improvements.map((item) => (
                  <li key={item} className="rounded-lg bg-zinc-50 px-3 py-2">{item}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-950">Cover letter draft</h3>
              <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-zinc-50 p-3 text-sm leading-6 text-zinc-700">{analysis.cover_letter}</pre>
            </div>
          </div>

          <div className="mt-6 border-t border-zinc-100 pt-5">
            <button
              type="button"
              onClick={generateQuestions}
              disabled={isGeneratingQuestions}
              className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 px-4 py-2.5 text-sm font-semibold text-zinc-800 hover:bg-zinc-100"
            >
              <MessageSquareText className="h-4 w-4" />
              {isGeneratingQuestions ? "Generating questions" : "Generate interview questions"}
            </button>
            {questions.length > 0 && (
              <div className="mt-4 space-y-3">
                {questions.map((question) => (
                  <div key={question.id} className="rounded-lg border border-zinc-200 p-4">
                    <p className="font-medium text-zinc-950">{question.question}</p>
                    <p className="mt-2 text-sm text-zinc-600">{question.answer_hint}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

function SkillList({ title, skills, tone }) {
  const toneClass = tone === "emerald" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700";
  const skillItems = asArray(skills);
  return (
    <div>
      <h3 className="text-sm font-semibold text-zinc-950">{title}</h3>
      <div className="mt-3 flex flex-wrap gap-2">
        {skillItems.length === 0 && <span className="text-sm text-zinc-500">None</span>}
        {skillItems.map((skill) => (
          <span key={skill} className={`rounded-full px-3 py-1 text-sm font-medium ${toneClass}`}>{skill}</span>
        ))}
      </div>
    </div>
  );
}
