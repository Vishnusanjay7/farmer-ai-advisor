from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_schemes_search_api_pagination_and_filter():
    # 1. General search
    response = client.get("/api/v1/schemes/search?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5
    assert len(data["schemes"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2

    # 2. Filter by keyword
    response_kw = client.get("/api/v1/schemes/search?q=insurance")
    assert response_kw.status_code == 200
    kw_data = response_kw.json()
    assert any(s["scheme_code"] == "PMFBY" for s in kw_data["schemes"])

    # 3. Verify scheme fields
    scheme = kw_data["schemes"][0]
    assert "scheme_name" in scheme
    assert "official_portal_url" in scheme
    assert "eligibility_criteria" in scheme
    assert "required_documents" in scheme


def test_agriculture_sources_api():
    response = client.get("/api/v1/agriculture/sources")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 6
    assert len(data["sources"]) >= 6

    # Verify source fields
    src = data["sources"][0]
    assert "issuing_authority" in src
    assert "official_document_url" in src
    assert src["total_chunks"] > 0


def test_agriculture_topics_api():
    response = client.get("/api/v1/agriculture/topics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_topics"] > 0
    assert any("Pest" in t["topic"] or "Management" in t["topic"] for t in data["topics"])


def test_mandi_prices_api_validation_and_pagination():
    # State is required
    err_resp = client.get("/api/v1/mandi/prices")
    assert err_resp.status_code == 422  # Validation error

    # Valid state query
    ok_resp = client.get("/api/v1/mandi/prices?state=Uttar Pradesh&page=1&page_size=10")
    assert ok_resp.status_code == 200
    data = ok_resp.json()
    assert data["query_state"] == "Uttar Pradesh"
    assert "records" in data
