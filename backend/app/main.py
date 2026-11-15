import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .auth import AuthUser, get_auth_user
from .config import Settings, get_settings
from .db import Database, apply_migrations


class StartupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    idea: str = Field(min_length=1)
    customer: str = Field(min_length=1)
    model: str = Field(min_length=1)
    market: str = Field(min_length=1)


def make_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = database

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal db
        db = db or Database(settings)
        apply_migrations(db, Path(__file__).parent / "migrations")
        yield
        if db:
            db.close()

    app = FastAPI(title="Carmine API", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    def current_user(user: AuthUser = Depends(get_auth_user)) -> AuthUser:
        row = db.execute("SELECT id, email FROM users WHERE id = ?", (user.id,)).fetchone()
        if row is None:
            db.execute("INSERT INTO users (id, email) VALUES (?, ?)", (user.id, user.email))
            db.commit()
        elif user.email and row[1] != user.email:
            db.execute("UPDATE users SET email = ? WHERE id = ?", (user.email, user.id))
            db.commit()
        return user

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/me")
    def me(user: AuthUser = Depends(current_user)):
        row = db.execute("SELECT id, email, role, created_at FROM users WHERE id = ?", (user.id,)).fetchone()
        return {"id": row[0], "email": row[1], "role": row[2], "created_at": row[3]}

    @app.post("/startups", status_code=201)
    def create_startup(payload: StartupCreate, user: AuthUser = Depends(current_user)):
        startup_id = str(uuid.uuid4())
        profile = payload.model_dump()
        db.execute("INSERT INTO startups (id, owner_user_id, name, profile_json) VALUES (?, ?, ?, ?)",
                   (startup_id, user.id, payload.name, json.dumps(profile)))
        db.commit()
        return {"id": startup_id, "owner_user_id": user.id, **profile}

    @app.get("/startups")
    def list_startups(user: AuthUser = Depends(current_user)):
        rows = db.execute("SELECT id, name, profile_json, created_at FROM startups WHERE owner_user_id = ? ORDER BY created_at DESC", (user.id,)).fetchall()
        return [{"id": row[0], "name": row[1], **json.loads(row[2]), "created_at": row[3]} for row in rows]

    @app.delete("/startups/{startup_id}", status_code=204)
    def delete_startup(startup_id: str, user: AuthUser = Depends(current_user)):
        owned_startup(startup_id, user)
        db.execute("DELETE FROM llm_cache WHERE startup_id = ?", (startup_id,))
        db.execute("DELETE FROM embeddings WHERE startup_id = ?", (startup_id,))
        db.execute("DELETE FROM startups WHERE id = ? AND owner_user_id = ?", (startup_id, user.id))
        db.commit()

    def owned_startup(startup_id: str, user: AuthUser):
        row = db.execute("SELECT id, name, profile_json, created_at FROM startups WHERE id = ? AND owner_user_id = ?", (startup_id, user.id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Startup not found")
        return row

    @app.get("/startups/{startup_id}/objections")
    def list_objections(startup_id: str, user: AuthUser = Depends(current_user)):
        owned_startup(startup_id, user)
        return []

    return app


app = make_app()
