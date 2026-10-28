import pytest
from datetime import datetime, timedelta, timezone

from app import ai, security
from app.brain import IntakeResult

C = {"email": "a@example.com", "password": "password123"}
IDEA = {"idea": "A marketplace for local photographers"}


@pytest.fixture
def authed(client):
    assert client.post("/api/auth/register", json=C).status_code == 201
    return client


def mk(c, name="P"):
    return c.post("/api/projects", json={"name": name}).json()["id"]


def test_register_login_me_logout(client):
    assert client.get("/api/auth/me").status_code == 401
    client.post("/api/auth/register", json=C)
    assert client.post("/api/auth/register", json=C).status_code == 409
    assert client.get("/api/auth/me").json()["email"] == C["email"]
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={**C, "password": "wrongwrong"}).status_code == 401
    assert client.post("/api/auth/login", json=C).status_code == 200


def test_cookies_are_httponly(client):
    r = client.post("/api/auth/register", json=C)
    assert all("httponly" in h.lower() for h in r.headers.get_list("set-cookie"))


def test_refresh_rotation_and_reuse(authed):
    old = authed.cookies.get("refresh_token", path="/api/auth")
    assert authed.post("/api/auth/refresh").status_code == 200
    new = authed.cookies.get("refresh_token", path="/api/auth")
    assert new != old
    authed.cookies.set("refresh_token", old, path="/api/auth")
    assert authed.post("/api/auth/refresh").status_code == 401  # reuse detected
    authed.cookies.set("refresh_token", new, path="/api/auth")
    assert authed.post("/api/auth/refresh").status_code == 401  # all tokens revoked


def test_project_crud_and_isolation(authed):
    pid = mk(authed)
    assert authed.patch(f"/api/projects/{pid}", json={"name": "R", "status": "archived"}).json()["status"] == "archived"
    assert len(authed.get("/api/projects").json()) == 1
    authed.post("/api/auth/logout")
    authed.post("/api/auth/register", json={"email": "b@example.com", "password": "password123"})
    assert authed.get(f"/api/projects/{pid}").status_code == 404
    authed.post("/api/auth/login", json=C)
    assert authed.delete(f"/api/projects/{pid}").status_code == 204
    assert authed.get(f"/api/projects/{pid}").status_code == 404


def test_brain_revisions_append_only(authed):
    pid = mk(authed)
    assert authed.get(f"/api/projects/{pid}/brain").json()["version"] == 1
    assert authed.put(f"/api/projects/{pid}/brain/goals", json={"value": ["g1"]}).json()["version"] == 2
    assert authed.put(f"/api/projects/{pid}/brain/goals", json={"value": ["g2"]}).json()["version"] == 3
    assert authed.put(f"/api/projects/{pid}/brain/nope", json={"value": {}}).status_code == 404
    assert authed.put(f"/api/projects/{pid}/brain/goals", json={"value": {"x": 1}}).status_code == 422
    revs = authed.get(f"/api/projects/{pid}/revisions").json()
    assert [r["version"] for r in revs] == [3, 2, 1]
    assert authed.get(f"/api/projects/{pid}/brain").json()["brain"]["goals"] == ["g2"]


def test_lifecycle_dependencies_and_overview(authed):
    pid = mk(authed)
    o = authed.get(f"/api/projects/{pid}/overview").json()
    assert o["progress"] == 0 and o["next_action"] == "research"
    assert authed.put(f"/api/projects/{pid}/stages/product", json={"status": "in_progress"}).status_code == 409
    assert authed.put(f"/api/projects/{pid}/stages/research", json={"status": "complete"}).status_code == 200
    assert authed.put(f"/api/projects/{pid}/stages/product", json={"status": "in_progress"}).status_code == 200
    o = authed.get(f"/api/projects/{pid}/overview").json()
    assert o["completed"] == ["research"] and o["in_progress"] == ["product"]
    assert o["next_action"] == "product" and o["progress"] == round(100 / 19)
    by = {x["stage"]: x for x in o["stages"]}
    assert by["api"]["depends_on"] == ["backend", "database"]
    assert by["api"]["unmet_dependencies"] == ["backend", "database"]
    assert by["product"]["unmet_dependencies"] == [] and o["needs_review"] == []
    authed.put(f"/api/projects/{pid}/stages/product", json={"status": "needs_review"})
    assert authed.get(f"/api/projects/{pid}/overview").json()["needs_review"] == ["product"]


def test_intake_without_provider_is_503_and_stores_nothing(authed):
    pid = mk(authed)
    assert authed.post(f"/api/projects/{pid}/intake", json=IDEA).status_code == 503
    assert authed.get(f"/api/projects/{pid}/brain").json()["version"] == 1


def test_intake_validates_and_persists(authed, monkeypatch):
    class Fake(ai.AIProvider):  # test double only; the app never fabricates AI output
        async def generate(self, prompt):
            return IntakeResult(product_name="Snapbook", product_type="marketplace", problem="Hard to find photographers",
                                target_users=["customers"], goals=["bookings"], questions=["Who pays?"]).model_dump_json()

    monkeypatch.setattr(ai, "get_provider", lambda: Fake())
    pid = mk(authed)
    assert authed.post(f"/api/projects/{pid}/intake", json=IDEA).status_code == 200
    b = authed.get(f"/api/projects/{pid}/brain").json()["brain"]
    assert b["idea"]["product_name"] == "Snapbook" and b["goals"] == ["bookings"]

    class Bad(ai.AIProvider):
        async def generate(self, prompt):
            return '{"product_name": 1}'

    monkeypatch.setattr(ai, "get_provider", lambda: Bad())
    assert authed.post(f"/api/projects/{pid}/intake", json=IDEA).status_code == 502


def test_as_utc_handles_naive_and_aware():
    naive = datetime(2026, 1, 1, 12, 0)
    assert security.as_utc(naive) == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    ist = datetime(2026, 1, 1, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert security.as_utc(ist) == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_ready_endpoint(client):
    assert client.get("/api/ready").json() == {"status": "ready"}
