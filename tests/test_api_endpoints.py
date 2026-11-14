"""End-to-end integration tests for BOMX FastAPI backend."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from backend.main import app
from backend.storage import storage

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_dashboard_stats():
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    data = res.json()
    assert "total_drawings" in data
    assert "verified_drawings" in data
    assert "confidence_distribution" in data


def test_drawings_list():
    res = client.get("/api/drawings")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_upload_and_extract_flow():
    # Test upload with a small image
    from PIL import Image
    img = Image.new("RGB", (600, 400), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    res = client.post(
        "/api/upload",
        files={"files": ("test_sheet.png", buf.getvalue(), "image/png")},
        data={"auto_extract": "false"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 1
    uploaded_id = data["uploaded"][0]["id"]

    # Verify detail
    detail_res = client.get(f"/api/drawings/{uploaded_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["metadata"]["id"] == uploaded_id

    # Test patch
    patch_res = client.patch(
        f"/api/drawings/{uploaded_id}",
        json={"verified": True},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["metadata"]["verified"] is True

    # Test delete
    del_res = client.delete(f"/api/drawings/{uploaded_id}")
    assert del_res.status_code == 200


if __name__ == "__main__":
    print("Running integration tests...")
    test_health()
    print("Health OK")
    test_dashboard_stats()
    print("Dashboard Stats OK")
    test_drawings_list()
    print("Drawings List OK")
    test_upload_and_extract_flow()
    print("Upload & Extract Flow OK")
    print("ALL API TESTS PASSED!")
