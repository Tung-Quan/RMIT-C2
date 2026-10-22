"""Private request assertions issued only after FairEnrol verifies Tide + DPoP.

These are internal transport assertions, never browser login tokens. The copied
business services retain their owner, role, version and idempotency checks.
"""
import hashlib
import hmac
import os
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.db.models import GatewayAssertion

ISSUER = "fairenrol-careers-gateway"


def install_tide_gateway(app):
    @app.middleware("http")
    async def verify_private_request(request: Request, call_next):
        if request.url.path in {"/health", "/health/live", "/health/ready", "/metrics"}:
            return await call_next(request)
        secret = os.environ.get("FAIRENROL_GATEWAY_SECRET", "")
        if len(secret) < 32:
            return JSONResponse({"detail": "Tide gateway is not configured"}, status_code=503)
        try:
            authorization = request.headers.get("authorization", "")
            if not authorization.startswith("Bearer "):
                raise ValueError("Missing private assertion")
            claims = jwt.decode(authorization[7:], secret, algorithms=["HS256"],
                                audience="careers-api", issuer=ISSUER,
                                options={"require_exp": True, "require_iat": True, "require_sub": True, "require_jti": True})
            now = int(time.time())
            if claims["exp"] - claims["iat"] > 31 or claims["iat"] > now + 5:
                raise ValueError("Invalid assertion lifetime")
            if not all(isinstance(claims.get(k), str) and claims[k] for k in ("tide_issuer", "tide_subject", "person_id", "full_name")):
                raise ValueError("Invalid identity")
            if claims.get("role") not in {"hr", "candidate"}:
                raise ValueError("Invalid role")
            path = request.url.path + ("?" + request.url.query if request.url.query else "")
            if claims.get("method") != request.method or claims.get("path") != path:
                raise ValueError("Assertion request mismatch")
            body = await request.body()
            if len(body) > 26 * 1024 * 1024:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
            if not hmac.compare_digest(claims.get("body_sha256", ""), hashlib.sha256(body).hexdigest()):
                raise ValueError("Assertion body mismatch")
            with SessionLocal() as db:
                db.execute(delete(GatewayAssertion).where(GatewayAssertion.expires_at < now))
                db.add(GatewayAssertion(id=claims["jti"], expires_at=claims["exp"]))
                db.commit()
            request.state.tide_identity = claims
        except (JWTError, ValueError, TypeError, KeyError, IntegrityError):
            return JSONResponse({"detail": "Invalid or replayed Tide gateway assertion"}, status_code=401)
        return await call_next(request)
