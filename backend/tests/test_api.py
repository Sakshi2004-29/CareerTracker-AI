"""Smoke tests. Run inside backend/:  pip install -r requirements-dev.txt  then  pytest"""
import os
import tempfile

# Configure the app for an isolated demo database BEFORE importing it.
os.environ["DEMO_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
os.environ["GEMINI_API_KEY"] = ""
os.environ["BACKEND_API_KEY"] = ""
os.environ["ALLOW_DEMO_SEED"] = "true"
os.environ["DEMO_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

JD = ("Acme is hiring a Python Developer in Pune. Build APIs with FastAPI and PostgreSQL. "
      "Requirements: 2 years experience, Git, Docker.")


def test_full_flow():
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"

        # validation errors are readable
        r = c.post("/api/applications", json={"company_name": " ", "job_title": "Dev"})
        assert r.status_code == 422 and "Company name" in r.json()["detail"]
        r = c.post("/api/applications", json={"company_name": "A", "job_title": "B", "job_url": "nope"})
        assert r.status_code == 422

        # create / read / update / delete
        r = c.post("/api/applications", json={"company_name": "Acme", "job_title": "Dev", "job_description": JD,
                                              "status": "Applied", "application_date": "2026-01-01",
                                              "follow_up_date": "2026-01-05"})
        assert r.status_code == 201
        app_id = r.json()["id"]
        assert c.get(f"/api/applications/{app_id}").json()["company_name"] == "Acme"
        r = c.put(f"/api/applications/{app_id}", json={"status": "Interview", "notes": "hi"})
        assert r.status_code == 200 and r.json()["status"] == "Interview"
        r = c.put(f"/api/applications/{app_id}", json={"follow_up_date": "2025-12-01"})
        assert r.status_code == 422
        hist = c.get(f"/api/applications/{app_id}/history").json()
        assert [h["new_status"] for h in hist] == ["Interview", "Applied"]

        # filters
        assert len(c.get("/api/applications", params={"company": "acm"}).json()) == 1
        assert c.get("/api/applications", params={"status": "Offer"}).json() == []
        assert c.get("/api/applications", params={"company": "100%"}).json() == []

        # dashboard / follow-ups (follow-up date is long overdue)
        stats = c.get("/api/dashboard/stats").json()
        assert stats["total_applications"] == 1 and stats["interviews"] == 1 and stats["follow_ups_due"] == 1
        assert len(c.get("/api/followups").json()["overdue"]) == 1
        assert c.get("/api/analytics").json()["total_applications"] == 1

        # AI (demo templates)
        ex = c.post("/api/ai/extract-job", json={"job_description": JD}).json()
        assert "Python" in ex["extracted"]["skills"] and ex["source"] == "demo"
        assert c.post("/api/ai/follow-up-email", json={"application_id": app_id}).json()["subject"]
        qs = c.post("/api/ai/interview-questions", json={"application_id": app_id, "count": 5}).json()
        assert len(qs["questions"]) == 5

        # errors
        assert c.get("/api/applications/not-a-uuid").status_code == 422
        assert c.get("/api/applications/00000000-0000-0000-0000-000000000000").status_code == 404
        assert c.delete(f"/api/applications/{app_id}").status_code == 204
        assert c.delete(f"/api/applications/{app_id}").status_code == 404

        # demo seed
        assert c.post("/api/demo/seed").json()["inserted"] == 8
        assert c.post("/api/demo/seed").status_code == 409
