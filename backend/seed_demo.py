"""Command-line helper:  python seed_demo.py   (run inside the backend folder)

Loads the sample applications into whichever database your .env points to.
"""
import sys

from config import settings, validate_settings
from database import get_database
from demo import load_sample_data

if __name__ == "__main__":
    validate_settings()
    db = get_database()
    if db.count_applications() > 0 and "--force" not in sys.argv:
        print("The database already contains applications. Re-run with --force to add the demo data anyway.")
        sys.exit(1)
    count = load_sample_data(db)
    mode = "local demo database" if settings.demo_mode else "Supabase"
    print(f"Inserted {count} demo applications into the {mode}.")
