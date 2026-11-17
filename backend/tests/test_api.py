def startup_payload(name="Carmine"):
    return {"name": name, "idea": "A founder red-team queue", "customer": "Founders", "model": "SaaS", "market": "India"}


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_first_login_creates_user_and_startup_is_listed(client):
    assert client.get("/me").json()["id"] == "user-a"
    created = client.post("/startups", json=startup_payload())
    assert created.status_code == 201
    assert client.get("/startups").json()[0]["name"] == "Carmine"
    assert client.get(f"/startups/{created.json()['id']}/objections").json() == []


def test_user_cannot_read_other_users_startup_or_objections(client):
    startup = client.post("/startups", json=startup_payload()).json()
    client.current_user["user"] = type(client.current_user["user"])("user-b", "b@example.com")
    assert client.get("/startups").json() == []
    assert client.get(f"/startups/{startup['id']}/objections").status_code == 404


def test_deleting_startup_purges_llm_cache_and_embeddings(client):
    startup = client.post("/startups", json=startup_payload()).json()
    startup_id = startup["id"]
    client.db.execute(
        "INSERT INTO llm_cache (id, cache_key, startup_id, purpose, provider, model, schema_version, temperature, response_text, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("cache-1", "key-1", startup_id, "other", "gemini", "model", "1", 0.0, "{}", "2099-01-01T00:00:00Z"),
    )
    client.db.execute(
        "INSERT INTO embeddings (id, startup_id, content_hash, model, revision, dim, vector_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("embedding-1", startup_id, "hash-1", "bge", "rev", 2, "[0.1, 0.2]"),
    )
    client.db.commit()

    response = client.delete(f"/startups/{startup_id}")

    assert response.status_code == 204
    assert client.db.execute("SELECT COUNT(*) FROM llm_cache WHERE startup_id = ?", (startup_id,)).fetchone()[0] == 0
    assert client.db.execute("SELECT COUNT(*) FROM embeddings WHERE startup_id = ?", (startup_id,)).fetchone()[0] == 0
    assert client.get(f"/startups/{startup_id}/objections").status_code == 404


def test_deleting_startup_purges_all_derived_api_rows(client):
    startup_id = client.post("/startups", json=startup_payload()).json()["id"]
    client.db.execute("INSERT INTO assumptions (id, startup_id, text) VALUES (?, ?, ?)", ("assumption-delete", startup_id, "Customers pay"))
    client.db.execute("INSERT INTO runs (id, startup_id, started_at) VALUES (?, ?, ?)", ("run-delete", startup_id, "2026-01-01T00:00:00+00:00"))
    client.db.execute("INSERT INTO sources (id, url) VALUES (?, ?)", ("source-delete", "https://example.com"))
    client.db.execute("INSERT INTO evidence (id, source_id, quote) VALUES (?, ?, ?)", ("evidence-delete", "source-delete", "quote"))
    client.db.execute("INSERT INTO objections (id, startup_id, module, text, severity) VALUES (?, ?, ?, ?, ?)", ("objection-delete", startup_id, "market", "risk", "low"))
    client.db.execute("INSERT INTO objection_evidence (objection_id, evidence_id) VALUES (?, ?)", ("objection-delete", "evidence-delete"))
    client.db.execute("INSERT INTO verdicts (id, objection_id, verdict) VALUES (?, ?, ?)", ("verdict-delete", "objection-delete", "investigate"))
    client.db.execute("INSERT INTO counter_arguments (id, verdict_id, text) VALUES (?, ?, ?)", ("counter-delete", "verdict-delete", "counter"))
    client.db.execute("INSERT INTO validation_tasks (id, objection_id, description, status) VALUES (?, ?, ?, ?)", ("task-delete", "objection-delete", "test", "open"))
    client.db.execute("INSERT INTO llm_calls (id, run_id) VALUES (?, ?)", ("llm-delete", "run-delete"))
    client.db.execute("INSERT INTO tool_calls (id, run_id) VALUES (?, ?)", ("tool-delete", "run-delete"))
    client.db.commit()

    assert client.delete(f"/startups/{startup_id}").status_code == 204
    for table in ("assumptions", "runs", "sources", "evidence", "objections", "verdicts", "counter_arguments", "validation_tasks", "llm_calls", "tool_calls"):
        assert client.db.execute(f"SELECT COUNT(*) FROM {table} WHERE id IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("assumption-delete", "run-delete", "source-delete", "evidence-delete", "objection-delete", "verdict-delete", "counter-delete", "task-delete", "llm-delete", "tool-delete")).fetchone()[0] == 0


def test_runs_require_confirmed_assumption_and_are_queued(client):
    startup = client.post("/startups", json=startup_payload()).json()
    startup_id = startup["id"]
    assert client.post(f"/startups/{startup_id}/runs").status_code == 409
    assumption = client.post(f"/startups/{startup_id}/assumptions", json={"text": "Customers will pay"}).json()
    confirmed = client.patch(f"/assumptions/{assumption['id']}", json={"status": "confirmed"})
    assert confirmed.status_code == 200
    run = client.post(f"/startups/{startup_id}/runs")
    assert run.status_code == 201
    assert run.json()["status"] == "queued"


def test_extract_returns_proposals_without_writing(client, monkeypatch):
    from types import SimpleNamespace
    import app.main as main_module

    startup_id = client.post("/startups", json=startup_payload()).json()["id"]
    calls = []

    class FakeLLM:
        def complete(self, purpose, messages, schema, **kwargs):
            calls.append((purpose, schema.__name__, messages))
            from app.main import AssumptionProposalResponse
            return SimpleNamespace(value=AssumptionProposalResponse(assumptions=[{"text": "People will buy", "category": "demand"}]))

    monkeypatch.setattr(main_module, "LLMClient", lambda db: FakeLLM())
    response = client.post(f"/startups/{startup_id}/assumptions/extract", json={"text": "A pasted pitch"})
    assert response.status_code == 200
    assert response.json()["assumptions"][0]["text"] == "People will buy"
    assert client.get(f"/startups/{startup_id}/assumptions").json() == []
    assert calls[0][0:2] == ("assumption_extract", "AssumptionProposalResponse")


def test_high_severity_reason_and_investigate_task(client):
    startup_id = client.post("/startups", json=startup_payload()).json()["id"]
    objection_id = "objection-1"
    client.db.execute("INSERT INTO objections (id, startup_id, module, text, severity) VALUES (?, ?, ?, ?, ?)", (objection_id, startup_id, "market", "Demand is weak", "high"))
    client.db.commit()
    assert client.post(f"/objections/{objection_id}/verdict", json={"verdict": "rebut"}).status_code == 422
    response = client.post(f"/objections/{objection_id}/verdict", json={"verdict": "investigate", "reason": "Need interviews", "time_spent_ms": 1200})
    assert response.status_code == 201
    assert client.get(f"/startups/{startup_id}/validation-tasks").json()[0]["status"] == "open"


def test_failed_counter_does_not_consume_counter(client, monkeypatch):
    from types import SimpleNamespace
    import app.main as main_module
    from app.llm.client import AllProvidersFailed

    startup_id = client.post("/startups", json=startup_payload()).json()["id"]
    objection_id = "objection-2"
    client.db.execute("INSERT INTO objections (id, startup_id, module, text, severity) VALUES (?, ?, ?, ?, ?)", (objection_id, startup_id, "market", "Demand is weak", "medium"))
    client.db.execute("INSERT INTO verdicts (id, objection_id, verdict, reason) VALUES (?, ?, ?, ?)", ("verdict-2", objection_id, "rebut", "Interview data disagrees"))
    client.db.commit()

    class FakeLLM:
        failed = True
        def complete(self, *args, **kwargs):
            if self.failed:
                raise AllProvidersFailed("failed")
            return SimpleNamespace(value=SimpleNamespace(text="The stored evidence still warrants a test.", new_evidence_ids=[]))

    fake = FakeLLM()
    monkeypatch.setattr(main_module, "LLMClient", lambda db: fake)
    assert client.post(f"/objections/{objection_id}/counter").status_code == 503
    assert client.db.execute("SELECT COUNT(*) FROM counter_arguments").fetchone()[0] == 0

    fake.failed = False
    assert client.post(f"/objections/{objection_id}/counter").status_code == 201
    assert client.post(f"/objections/{objection_id}/counter").status_code == 409


def test_ending_session_uses_last_server_stamped_event(client):
    from datetime import datetime, timezone

    session_id = client.post("/sessions").json()["id"]
    client.post("/events", json={"events": [{"session_id": session_id, "event": "card shown"}]})
    ended = client.patch(f"/sessions/{session_id}", json={"active_ms": 1000})
    assert ended.status_code == 200
    event_ts = client.db.execute("SELECT ts_ms FROM ui_events WHERE session_id = ?", (session_id,)).fetchone()[0]
    assert ended.json()["ended_at"] == datetime.fromtimestamp(event_ts / 1000, timezone.utc).isoformat()
