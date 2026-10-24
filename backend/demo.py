"""Loads the fictional sample applications from sample_data.json.

Used by POST /api/demo/seed (the "Load demo data" button) and by
`python seed_demo.py`. Works with both Supabase and the local demo database.
"""
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from database import Database

SAMPLE_FILE = Path(__file__).resolve().parent / "sample_data.json"


def load_sample_data(db: Database, today: Optional[date] = None) -> int:
    today = today or date.today()
    samples = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    for item in samples:
        path = item["status_path"]
        applied = item["applied_days_ago"]
        follow = item["follow_up_in_days"]
        data = {
            "company_name": item["company_name"],
            "job_title": item["job_title"],
            "job_description": item["job_description"],
            "job_url": item["job_url"],
            "location": item["location"],
            "notes": item["notes"],
            "resume_version": item["resume_version"],
            "application_date": (today - timedelta(days=applied)).isoformat() if applied is not None else None,
            "follow_up_date": (today + timedelta(days=follow)).isoformat() if follow is not None else None,
            "status": "Saved",
        }
        created = db.create_application(data)
        # Walk through the statuses so the history table gets realistic entries.
        for status in path:
            db.update_application(created["id"], {"status": status})
    return len(samples)
