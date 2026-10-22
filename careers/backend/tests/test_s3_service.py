from app.core.config import get_settings
from app.services.s3_service import generate_presigned_url


def test_presigned_url_uses_regional_virtual_host(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    monkeypatch.setenv("S3_BUCKET", "fairenrol-careers")
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    get_settings.cache_clear()

    try:
        url = generate_presigned_url("users/demo-user/documents/test.pdf")
        assert url.startswith("https://fairenrol-careers.s3.ap-southeast-2.amazonaws.com/")
        assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
        assert "S3_PUBLIC_BASE_URL" not in url
    finally:
        get_settings.cache_clear()
