from datetime import UTC, datetime

from docs_api.store import Document


def test_active_document_is_returned(client, seed):
    seed(Document("D-1", "Q3 report", datetime(2026, 11, 1, tzinfo=UTC)))
    resp = client.get("/documents/D-1")
    assert resp.status_code == 200
    assert resp.json["title"] == "Q3 report"
    assert resp.json["id"] == "D-1"
    assert resp.json["updated_at"] == "2026-11-01T00:00:00+00:00"


def test_unknown_document_returns_404(client):
    resp = client.get("/documents/D-404")
    assert resp.status_code == 404
    assert resp.json == {"error": "NOT_FOUND"}
