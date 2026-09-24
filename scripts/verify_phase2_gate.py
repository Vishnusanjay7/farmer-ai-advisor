import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

print("=== 1. Mandi Prices API ===")
r1 = client.get("/api/v1/mandi/prices?state=Madhya Pradesh&commodity=Wheat")
print(f"Valid query status: {r1.status_code}, total: {r1.json().get('total')}")

r1_err = client.get("/api/v1/mandi/prices")
print(f"Missing state validation status: {r1_err.status_code}")

r1_empty = client.get("/api/v1/mandi/prices?state=NonExistentState&commodity=NonExistent")
print(f"Empty query status: {r1_empty.status_code}, records: {len(r1_empty.json().get('records', []))}")

print("\n=== 2. Schemes Search API ===")
r2 = client.get("/api/v1/schemes/search?page=1&page_size=2")
d2 = r2.json()
print(f"Status: {r2.status_code}, total: {d2.get('total')}, page_records: {len(d2.get('schemes', []))}")

r2_filter = client.get("/api/v1/schemes/search?q=insurance")
schemes_list = [s.get("scheme_code") for s in r2_filter.json().get("schemes", [])]
print(f"Keyword filter status: {r2_filter.status_code}, matches: {schemes_list}")

print("\n=== 3. Agriculture Sources API ===")
r3 = client.get("/api/v1/agriculture/sources?source_type=ICAR")
d3 = r3.json()
print(f"ICAR Sources filter status: {r3.status_code}, count: {len(d3.get('sources', []))}")
for s in d3.get("sources", []):
    print(f"  - {s.get('source_name')} ({s.get('total_chunks')} chunks, authority: {s.get('issuing_authority')})")

print("\n=== 4. Agriculture Topics API ===")
r4 = client.get("/api/v1/agriculture/topics?crop=Paddy")
d4 = r4.json()
print(f"Paddy Topics filter status: {r4.status_code}, total_topics: {d4.get('total_topics')}")
for t in d4.get("topics", []):
    print(f"  - Topic: {t.get('topic')} (Crop: {t.get('crop_name')}, Chunks: {t.get('chunk_count')})")
