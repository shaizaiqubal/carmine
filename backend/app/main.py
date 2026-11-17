import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from .auth import AuthUser, get_auth_user
from .config import Settings, get_settings
from .db import Database, apply_migrations
from .llm.client import AllProvidersFailed, LLMClient
from .llm.privacy import wrap_untrusted_content


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class StartupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    idea: str = Field(min_length=1, max_length=20000)
    customer: str = Field(min_length=1, max_length=5000)
    model: str = Field(min_length=1, max_length=5000)
    market: str = Field(min_length=1, max_length=5000)


class AssumptionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    category: str | None = Field(default=None, max_length=100)


class AssumptionExtractRequest(BaseModel):
    text: str = Field(min_length=1)


class AssumptionPatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    category: str | None = Field(default=None, max_length=100)
    status: str | None = None

    @model_validator(mode="after")
    def has_change(self):
        if self.text is None and self.category is None and self.status is None:
            raise ValueError("at least one field is required")
        if self.status is not None and self.status not in {"proposed", "confirmed", "retired"}:
            raise ValueError("invalid assumption status")
        return self


class VerdictRequest(BaseModel):
    verdict: str
    reason: str | None = Field(default=None, max_length=10000)
    response_plan: str | None = Field(default=None, max_length=10000)
    time_spent_ms: int | None = Field(default=None, ge=0, le=86400000)


class TaskPatch(BaseModel):
    status: str = Field(min_length=1, max_length=50)


class SessionCreate(BaseModel):
    pass


class SessionPatch(BaseModel):
    active_ms: int | None = Field(default=None, ge=0, le=86400000)


VALID_EVENTS = {"card shown", "verdict start", "verdict end", "rebuttal start", "rebuttal end", "idle", "resumed"}


class Event(BaseModel):
    session_id: str
    event: str
    objection_id: str | None = None


class EventBatch(BaseModel):
    events: list[Event] = Field(min_length=1, max_length=100)


class AssumptionProposal(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    category: str | None = Field(default=None, max_length=100)


class AssumptionProposalResponse(BaseModel):
    assumptions: list[AssumptionProposal] = Field(max_length=10)


class CounterResponse(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    new_evidence_ids: list[str] = []


def make_app(settings: Settings | None = None, database: Database | None = None, llm_client=None) -> FastAPI:
    settings = settings or get_settings()
    db = database
    llm = llm_client
    rate_lock = Lock()
    llm_attempts = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal db
        db = db or Database(settings)
        apply_migrations(db, Path(__file__).parent / "migrations")
        yield
        if db:
            db.close()

    app = FastAPI(title="Carmine API", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(HTTPException)
    async def http_error(_, exc):
        detail = exc.detail if isinstance(exc.detail, dict) and "code" in exc.detail else {"code": "http_error", "message": str(exc.detail), "details": {}}
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "Request validation failed", "details": [{"loc": list(e["loc"]), "message": e["msg"]} for e in exc.errors()]}})

    def fail(status, code, message, details=None):
        raise HTTPException(status_code=status, detail={"code": code, "message": message, "details": details or {}})

    def current_user(user: AuthUser = Depends(get_auth_user)):
        row = db.execute("SELECT id, email FROM users WHERE id = ?", (user.id,)).fetchone()
        if row is None:
            db.execute("INSERT INTO users (id, email) VALUES (?, ?)", (user.id, user.email)); db.commit()
        elif user.email and row[1] != user.email:
            db.execute("UPDATE users SET email = ? WHERE id = ?", (user.email, user.id)); db.commit()
        return user

    def owned_startup(startup_id, user):
        row = db.execute("SELECT id, name, profile_json, created_at FROM startups WHERE id = ? AND owner_user_id = ?", (startup_id, user.id)).fetchone()
        if not row: fail(404, "not_found", "Startup not found")
        return row

    def owned_assumption(assumption_id, user):
        row = db.execute("SELECT a.* FROM assumptions a JOIN startups s ON s.id = a.startup_id WHERE a.id = ? AND s.owner_user_id = ?", (assumption_id, user.id)).fetchone()
        if not row: fail(404, "not_found", "Assumption not found")
        return row

    def owned_objection(objection_id, user):
        row = db.execute("SELECT o.* FROM objections o JOIN startups s ON s.id = o.startup_id WHERE o.id = ? AND s.owner_user_id = ?", (objection_id, user.id)).fetchone()
        if not row: fail(404, "not_found", "Objection not found")
        return row

    def owned_session(session_id, user):
        row = db.execute("SELECT * FROM sessions WHERE id = ? AND user_id = ?", (session_id, user.id)).fetchone()
        if not row: fail(404, "not_found", "Session not found")
        return row

    def get_llm():
        nonlocal llm
        if llm is None: llm = LLMClient(db)
        return llm

    def rate_limit(user_id, purpose, limit):
        if limit <= 0: return
        cutoff = datetime.now(timezone.utc).timestamp() - 60
        key = (user_id, purpose)
        with rate_lock:
            values = [value for value in llm_attempts.get(key, []) if value.timestamp() >= cutoff]
            if len(values) >= limit: fail(429, "rate_limited", "Too many requests; try again shortly")
            values.append(datetime.now(timezone.utc)); llm_attempts[key] = values

    @app.get("/health")
    def health(): return {"status": "ok"}

    @app.get("/me")
    def me(user: AuthUser = Depends(current_user)):
        return dict(db.execute("SELECT id, email, role, created_at FROM users WHERE id = ?", (user.id,)).fetchone())

    @app.post("/startups", status_code=201)
    def create_startup(payload: StartupCreate, user: AuthUser = Depends(current_user)):
        startup_id = str(uuid.uuid4()); profile = payload.model_dump()
        db.execute("INSERT INTO startups (id, owner_user_id, name, profile_json) VALUES (?, ?, ?, ?)", (startup_id, user.id, payload.name, json.dumps(profile))); db.commit()
        return {"id": startup_id, "owner_user_id": user.id, **profile}

    @app.get("/startups")
    def list_startups(user: AuthUser = Depends(current_user)):
        rows = db.execute("SELECT id, name, profile_json, created_at FROM startups WHERE owner_user_id = ? ORDER BY created_at DESC", (user.id,)).fetchall()
        return [{"id": row[0], "name": row[1], **json.loads(row[2]), "created_at": row[3]} for row in rows]

    @app.delete("/startups/{startup_id}", status_code=204)
    def delete_startup(startup_id: str, user: AuthUser = Depends(current_user)):
        owned_startup(startup_id, user)
        evidence_ids = [row[0] for row in db.execute("SELECT DISTINCT oe.evidence_id FROM objection_evidence oe JOIN objections o ON o.id = oe.objection_id WHERE o.startup_id = ?", (startup_id,)).fetchall()]
        db.execute("DELETE FROM ui_events WHERE objection_id IN (SELECT id FROM objections WHERE startup_id = ?)", (startup_id,))
        db.execute("DELETE FROM llm_calls WHERE run_id IN (SELECT id FROM runs WHERE startup_id = ?)", (startup_id,)); db.execute("DELETE FROM tool_calls WHERE run_id IN (SELECT id FROM runs WHERE startup_id = ?)", (startup_id,)); db.execute("DELETE FROM runs WHERE startup_id = ?", (startup_id,))
        db.execute("DELETE FROM llm_cache WHERE startup_id = ?", (startup_id,)); db.execute("DELETE FROM embeddings WHERE startup_id = ?", (startup_id,))
        if evidence_ids:
            source_ids = [row[0] for row in db.execute("SELECT source_id FROM evidence WHERE id IN ({})".format(",".join("?" for _ in evidence_ids)), tuple(evidence_ids)).fetchall()]
            db.execute("DELETE FROM evidence WHERE id IN ({})".format(",".join("?" for _ in evidence_ids)), tuple(evidence_ids))
            if source_ids:
                db.execute("DELETE FROM sources WHERE id IN ({}) AND id NOT IN (SELECT source_id FROM evidence)".format(",".join("?" for _ in source_ids)), tuple(source_ids))
        db.execute("DELETE FROM startups WHERE id = ? AND owner_user_id = ?", (startup_id, user.id)); db.commit()

    @app.post("/startups/{startup_id}/assumptions/extract")
    def extract_assumptions(startup_id: str, payload: AssumptionExtractRequest, user: AuthUser = Depends(current_user)):
        owned_startup(startup_id, user)
        if len(payload.text) > settings.assumption_extract_max_chars: fail(413, "request_too_large", "Pasted text exceeds the maximum length")
        rate_limit(user.id, "assumption_extract", settings.llm_interactive_rate_limit_per_minute)
        messages = [{"role": "system", "content": "Extract up to 10 concise, testable startup assumptions. Return only the schema."}, {"role": "user", "content": wrap_untrusted_content(payload.text, "pasted founder text")}]
        try: result = get_llm().complete("assumption_extract", messages, AssumptionProposalResponse, startup_id=startup_id)
        except AllProvidersFailed: fail(503, "llm_unavailable", "Assumption extraction models are unavailable")
        value = result.value; proposals = value.assumptions if hasattr(value, "assumptions") else value.get("assumptions", [])
        return {"assumptions": [item if isinstance(item, dict) else item.model_dump() for item in proposals[:10]]}

    @app.get("/startups/{startup_id}/assumptions")
    def list_assumptions(startup_id: str, user: AuthUser = Depends(current_user)):
        owned_startup(startup_id, user); return [dict(row) for row in db.execute("SELECT * FROM assumptions WHERE startup_id = ? ORDER BY created_at", (startup_id,)).fetchall()]

    @app.post("/startups/{startup_id}/assumptions", status_code=201)
    def create_assumption(startup_id: str, payload: AssumptionCreate, user: AuthUser = Depends(current_user)):
        owned_startup(startup_id, user); assumption_id = str(uuid.uuid4())
        db.execute("INSERT INTO assumptions (id, startup_id, text, category) VALUES (?, ?, ?, ?)", (assumption_id, startup_id, payload.text, payload.category)); db.commit()
        return dict(db.execute("SELECT * FROM assumptions WHERE id = ?", (assumption_id,)).fetchone())

    @app.patch("/assumptions/{assumption_id}")
    def patch_assumption(assumption_id: str, payload: AssumptionPatch, user: AuthUser = Depends(current_user)):
        row = owned_assumption(assumption_id, user); values = payload.model_dump(exclude_unset=True)
        if values.get("status") == "confirmed": values["confirmed_at"] = now_iso()
        if values.get("status") in {"proposed", "retired"}: values["confirmed_at"] = None
        db.execute(f"UPDATE assumptions SET {', '.join(f'{key} = ?' for key in values)} WHERE id = ?", (*values.values(), assumption_id)); db.commit()
        return dict(db.execute("SELECT * FROM assumptions WHERE id = ?", (row[0],)).fetchone())

    @app.post("/startups/{startup_id}/runs", status_code=201)
    def create_run(startup_id: str, user: AuthUser = Depends(current_user)):
        owned_startup(startup_id, user)
        if db.execute("SELECT 1 FROM assumptions WHERE startup_id = ? AND status = 'confirmed' LIMIT 1", (startup_id,)).fetchone() is None: fail(409, "assumption_checkpoint_required", "Confirm at least one assumption before starting a run")
        today = datetime.now(timezone.utc).date().isoformat(); count = db.execute("SELECT COUNT(*) FROM runs WHERE startup_id = ? AND date(started_at) = ?", (startup_id, today)).fetchone()[0]
        if count >= settings.runs_per_startup_per_day: fail(429, "rate_limited", "This startup has reached its daily run limit")
        run_id = str(uuid.uuid4()); started = now_iso(); db.execute("INSERT INTO runs (id, startup_id, started_at, new_sources, new_objections) VALUES (?, ?, ?, 0, 0)", (run_id, startup_id, started)); db.commit()
        return {"id": run_id, "startup_id": startup_id, "status": "queued", "started_at": started}

    @app.get("/startups/{startup_id}/runs")
    def list_runs(startup_id: str, user: AuthUser = Depends(current_user)):
        owned_startup(startup_id, user); return [{**dict(row), "status": "finished" if row[2] else "queued"} for row in db.execute("SELECT * FROM runs WHERE startup_id = ? ORDER BY started_at DESC", (startup_id,)).fetchall()]

    @app.get("/runs/{run_id}")
    def get_run(run_id: str, user: AuthUser = Depends(current_user)):
        row = db.execute("SELECT r.* FROM runs r JOIN startups s ON s.id = r.startup_id WHERE r.id = ? AND s.owner_user_id = ?", (run_id, user.id)).fetchone()
        if not row: fail(404, "not_found", "Run not found")
        return {**dict(row), "status": "finished" if row[2] else "queued"}

    @app.get("/startups/{startup_id}/objections")
    def list_objections(startup_id: str, user: AuthUser = Depends(current_user), status: str | None = None, module: str | None = None, assumption_id: str | None = None, severity: str | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        owned_startup(startup_id, user); where = ["o.startup_id = ?"]; params = [startup_id]
        for field, value in (("o.status", status), ("o.module", module), ("o.severity", severity)):
            if value: where.append(f"{field} = ?"); params.append(value)
        if assumption_id == "general": where.append("o.assumption_id IS NULL")
        elif assumption_id: where.append("o.assumption_id = ?"); params.append(assumption_id)
        params += [limit, offset]; rows = db.execute(f"SELECT o.* FROM objections o WHERE {' AND '.join(where)} ORDER BY o.created_at DESC LIMIT ? OFFSET ?", tuple(params)).fetchall()
        return [dict(row) for row in rows]

    @app.get("/objections/{objection_id}")
    def get_objection(objection_id: str, user: AuthUser = Depends(current_user)):
        objection = dict(owned_objection(objection_id, user))
        evidence = db.execute("SELECT e.*, s.url, s.domain, s.fetched_at, s.published_at FROM evidence e JOIN objection_evidence oe ON oe.evidence_id = e.id JOIN sources s ON s.id = e.source_id WHERE oe.objection_id = ?", (objection_id,)).fetchall()
        objection["evidence"] = [dict(row) for row in evidence]; objection["verdicts"] = [dict(row) for row in db.execute("SELECT * FROM verdicts WHERE objection_id = ? ORDER BY decided_at", (objection_id,)).fetchall()]
        return objection

    @app.post("/objections/{objection_id}/verdict", status_code=201)
    def verdict(objection_id: str, payload: VerdictRequest, user: AuthUser = Depends(current_user)):
        objection = owned_objection(objection_id, user)
        if payload.verdict not in {"accept", "rebut", "investigate", "dismiss"}: fail(422, "invalid_verdict", "Verdict must be accept, rebut, investigate, or dismiss")
        if payload.verdict in {"rebut", "dismiss"} and objection[5] in {"high", "critical"} and not (payload.reason and payload.reason.strip()): fail(422, "reason_required", "A written reason is required for high or critical rebuttals and dismissals")
        if objection[7] not in {"new", "surfaced", "reopened"}: fail(409, "invalid_transition", "This objection cannot receive another verdict in its current state")
        next_status = {"accept": "accepted", "rebut": "rebutted", "investigate": "investigating", "dismiss": "dismissed"}[payload.verdict]; verdict_id = str(uuid.uuid4())
        db.execute("INSERT INTO verdicts (id, objection_id, verdict, reason, response_plan, time_spent_ms) VALUES (?, ?, ?, ?, ?, ?)", (verdict_id, objection_id, payload.verdict, payload.reason.strip() if payload.reason else None, payload.response_plan, payload.time_spent_ms)); db.execute("UPDATE objections SET status = ? WHERE id = ?", (next_status, objection_id))
        if payload.verdict == "investigate": db.execute("INSERT INTO validation_tasks (id, objection_id, description, status) VALUES (?, ?, ?, 'open')", (str(uuid.uuid4()), objection_id, payload.reason.strip() if payload.reason else objection[4]))
        db.commit(); return {"id": verdict_id, "objection_id": objection_id, "verdict": payload.verdict, "status": next_status}

    @app.post("/objections/{objection_id}/counter", status_code=201)
    def counter(objection_id: str, user: AuthUser = Depends(current_user)):
        objection = owned_objection(objection_id, user); latest = db.execute("SELECT * FROM verdicts WHERE objection_id = ? ORDER BY decided_at DESC LIMIT 1", (objection_id,)).fetchone()
        if not latest or latest[2] != "rebut": fail(409, "counter_not_allowed", "A counter is allowed only after the latest verdict is rebut")
        if db.execute("SELECT 1 FROM counter_arguments WHERE verdict_id = ?", (latest[0],)).fetchone(): fail(409, "counter_already_used", "Only one counter is allowed per verdict")
        evidence = db.execute("SELECT e.quote, s.url FROM evidence e JOIN objection_evidence oe ON oe.evidence_id = e.id JOIN sources s ON s.id = e.source_id WHERE oe.objection_id = ?", (objection_id,)).fetchall(); evidence_text = "\n".join(f"Quote: {row[0]}\nSource URL: {row[1]}" for row in evidence)
        messages = [{"role": "system", "content": "Write one concise counter-argument using only the supplied evidence and founder reason. Do not invent sources, quotes, facts, or evidence. Return only the schema."}, {"role": "user", "content": wrap_untrusted_content(evidence_text, "stored objection evidence") + "\n" + wrap_untrusted_content(latest[3] or "", "founder rebuttal reason") + "\nObjection: " + wrap_untrusted_content(objection[4], "stored objection text")}]
        rate_limit(user.id, "counter", settings.llm_interactive_rate_limit_per_minute)
        try: result = get_llm().complete("counter", messages, CounterResponse, startup_id=objection[1])
        except AllProvidersFailed: fail(503, "llm_unavailable", "Counter-argument models are unavailable; try again later")
        value = result.value; text_value = value.text if hasattr(value, "text") else value["text"]; new_evidence_ids = value.new_evidence_ids if hasattr(value, "new_evidence_ids") else value.get("new_evidence_ids", [])
        counter_id = str(uuid.uuid4())
        try:
            db.execute("INSERT INTO counter_arguments (id, verdict_id, text, new_evidence_ids) VALUES (?, ?, ?, ?)", (counter_id, latest[0], text_value, json.dumps(new_evidence_ids))); db.commit()
        except Exception as exc:
            db.connection.rollback()
            if "UNIQUE" in str(exc).upper(): fail(409, "counter_already_used", "Only one counter is allowed per verdict")
            raise
        return {"id": counter_id, "verdict_id": latest[0], "text": text_value, "new_evidence_ids": new_evidence_ids}

    @app.get("/startups/{startup_id}/validation-tasks")
    def list_tasks(startup_id: str, user: AuthUser = Depends(current_user)):
        owned_startup(startup_id, user); return [dict(row) for row in db.execute("SELECT vt.* FROM validation_tasks vt JOIN objections o ON o.id = vt.objection_id WHERE o.startup_id = ? ORDER BY vt.created_at DESC", (startup_id,)).fetchall()]

    @app.patch("/validation-tasks/{task_id}")
    def patch_task(task_id: str, payload: TaskPatch, user: AuthUser = Depends(current_user)):
        row = db.execute("SELECT vt.* FROM validation_tasks vt JOIN objections o ON o.id = vt.objection_id JOIN startups s ON s.id = o.startup_id WHERE vt.id = ? AND s.owner_user_id = ?", (task_id, user.id)).fetchone()
        if not row: fail(404, "not_found", "Validation task not found")
        db.execute("UPDATE validation_tasks SET status = ? WHERE id = ?", (payload.status, task_id)); db.commit(); return dict(db.execute("SELECT * FROM validation_tasks WHERE id = ?", (task_id,)).fetchone())

    @app.post("/sessions", status_code=201)
    def create_session(user: AuthUser = Depends(current_user)):
        session_id = str(uuid.uuid4()); started = now_iso(); db.execute("INSERT INTO sessions (id, user_id, started_at) VALUES (?, ?, ?)", (session_id, user.id, started)); db.commit(); return {"id": session_id, "started_at": started}

    @app.patch("/sessions/{session_id}")
    def patch_session(session_id: str, payload: SessionPatch, user: AuthUser = Depends(current_user)):
        owned_session(session_id, user); ended = now_iso(); db.execute("UPDATE sessions SET ended_at = ?, active_ms = COALESCE(?, active_ms) WHERE id = ?", (ended, payload.active_ms, session_id)); db.commit(); return dict(db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())

    @app.post("/events", status_code=201)
    def create_events(payload: EventBatch, user: AuthUser = Depends(current_user)):
        for event in payload.events:
            owned_session(event.session_id, user)
            if event.event not in VALID_EVENTS: fail(422, "invalid_event", "Unsupported telemetry event type")
            if event.objection_id: owned_objection(event.objection_id, user)
            db.execute("INSERT INTO ui_events (id, session_id, event, objection_id, ts_ms) VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), event.session_id, event.event, event.objection_id, int(datetime.now(timezone.utc).timestamp() * 1000)))
        db.commit(); return {"accepted": len(payload.events)}

    return app


app = make_app()
