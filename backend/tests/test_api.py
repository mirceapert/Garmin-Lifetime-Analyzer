import importlib

from fastapi.testclient import TestClient

from gla.importer.export import ExportImporter


def test_api_health_and_library(settings, sessions, export_zip, monkeypatch):
    ExportImporter(settings, sessions).run(export_zip)
    monkeypatch.setenv("GLA_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("GLA_DATABASE_URL", settings.database_url)
    import gla.api
    api = importlib.reload(gla.api)
    client = TestClient(api.app)
    assert client.get("/api/health").json()["status"] == "ok"
    body = client.get("/api/library").json()
    assert body["library"]["activities"] == 7
    assert body["runs"][0]["status"] == "ok"
