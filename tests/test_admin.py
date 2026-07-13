from fastapi.testclient import TestClient

from app.main import app


def test_admin_requires_login():
    with TestClient(app) as client:
        response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")
