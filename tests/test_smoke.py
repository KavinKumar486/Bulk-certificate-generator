from sqlalchemy import inspect


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_v1_route_requires_auth(client):
    # Without API key
    response = client.get("/v1/jobs/test")
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key"}

    # With invalid API key
    response = client.get("/v1/jobs/test", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key"}


def test_v1_route_with_valid_key(client, auth_headers):
    response = client.get("/v1/jobs/test", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_tables_exist(temp_db):
    inspector = inspect(temp_db)
    table_names = inspector.get_table_names()
    assert "jobs" in table_names
    assert "certificates" in table_names
