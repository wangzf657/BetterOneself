"""M1-01:项目创建后进入项目页;项目可列表、可归档、可删除。"""


def test_create_and_get_study(client):
    resp = client.post("/api/studies", json={"name": "学 Rust", "goal": "能写 CLI 工具"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "学 Rust"
    assert body["status"] == "active"

    detail = client.get(f"/api/studies/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["goal"] == "能写 CLI 工具"


def test_create_validation_error(client):
    assert client.post("/api/studies", json={"name": "", "goal": "x"}).status_code == 422


def test_list_excludes_archived(client):
    a = client.post("/api/studies", json={"name": "A", "goal": "a"}).json()
    b = client.post("/api/studies", json={"name": "B", "goal": "b"}).json()
    client.patch(f"/api/studies/{b['id']}", json={"status": "archived"})

    active = client.get("/api/studies").json()
    assert [s["id"] for s in active] == [a["id"]]

    all_ = client.get("/api/studies", params={"include_archived": True}).json()
    assert {s["id"] for s in all_} == {a["id"], b["id"]}


def test_archive_and_delete(client):
    study = client.post("/api/studies", json={"name": "A", "goal": "a"}).json()

    patched = client.patch(f"/api/studies/{study['id']}", json={"status": "archived"})
    assert patched.json()["status"] == "archived"

    assert client.delete(f"/api/studies/{study['id']}").status_code == 204
    assert client.get(f"/api/studies/{study['id']}").status_code == 404


def test_get_missing_returns_404(client):
    assert client.get("/api/studies/999").status_code == 404
