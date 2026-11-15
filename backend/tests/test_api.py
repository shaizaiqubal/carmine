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
