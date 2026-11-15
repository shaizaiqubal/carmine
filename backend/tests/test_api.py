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
