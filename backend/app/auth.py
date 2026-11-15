from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from supabase import create_client

from .config import Settings, get_settings


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None = None


def get_auth_user(authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings)) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=503, detail="Supabase auth is not configured")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        response = client.auth.get_claims(token)
        claims = response.get("claims", {}) if isinstance(response, dict) else getattr(response, "claims", {})
        user_id = claims.get("sub")
        if not user_id:
            raise ValueError("missing sub")
        return AuthUser(id=user_id, email=claims.get("email"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
