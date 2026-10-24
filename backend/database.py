"""All database access lives in this file.

Two interchangeable implementations share one interface (class Database):
  * SupabaseDatabase - the real, persistent PostgreSQL database (production).
  * SQLiteDatabase   - a local file used ONLY when DEMO_MODE=true, so beginners
                       can try the app without any account or credentials.
main.py never talks to Supabase/SQLite directly; it only calls get_database().
"""
import json
import logging
import sqlite3
import uuid
from abc import ABC, abstractmethod
from contextlib import closing
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger("careertrack.db")

# Only these columns may ever be written by the API (guards against unexpected keys).
WRITABLE_FIELDS = (
    "company_name", "job_title", "job_description", "job_url", "application_date",
    "status", "follow_up_date", "notes", "resume_version", "location", "extracted_info",
)


class DatabaseError(Exception):
    """Raised for any database problem; main.py turns it into an HTTP 503."""


def _only_writable(data: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in data.items() if k in WRITABLE_FIELDS}


def _escape_like(text: str) -> str:
    """Escape % and _ so user text is matched literally inside LIKE/ILIKE."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database(ABC):
    @abstractmethod
    def list_applications(
        self, *, company: Optional[str] = None, role: Optional[str] = None,
        status: Optional[str] = None, date_from: Optional[date] = None,
        date_to: Optional[date] = None, user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def get_application(self, app_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def create_application(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]: ...

    @abstractmethod
    def update_application(self, app_id: str, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def delete_application(self, app_id: str, user_id: Optional[str] = None) -> bool: ...

    @abstractmethod
    def list_history(self, app_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def list_recent_history(self, limit: int = 30, user_id: Optional[str] = None) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def count_applications(self, user_id: Optional[str] = None) -> int: ...


# ==========================================================================
# Supabase (PostgreSQL)
# ==========================================================================
def _friendly_supabase_error(exc: Exception) -> str:
    text = str(exc)
    low = text.lower()
    if "pgrst205" in low or "schema cache" in low or ("relation" in low and "does not exist" in low):
        return "Database tables not found. Run supabase/schema.sql in the Supabase SQL Editor first."
    if "invalid api key" in low or "jwt" in low or "401" in low:
        return "Supabase rejected the credentials. Check SUPABASE_URL and SUPABASE_SERVICE_KEY."
    if any(t in low for t in ("getaddrinfo", "connecterror", "timed out", "name or service not known", "connection refused", "errno")):
        return "Could not reach Supabase. Check SUPABASE_URL and your internet connection."
    return f"Database error: {text[:200]}"


class SupabaseDatabase(Database):
    APPS = "job_applications"
    HISTORY = "application_history"

    def __init__(self, url: str, key: str) -> None:
        try:
            from supabase import create_client
            self.client = create_client(url, key)
        except Exception as exc:  # bad URL/key format etc.
            raise DatabaseError(f"Could not create the Supabase client: {exc}") from exc

    def _run(self, query: Any) -> Any:
        try:
            return query.execute()
        except Exception as exc:
            logger.exception("Supabase request failed")
            raise DatabaseError(_friendly_supabase_error(exc)) from exc

    def _add_history(self, app_id: str, old: Optional[str], new: str, note: Optional[str]) -> None:
        row = {"application_id": app_id, "old_status": old, "new_status": new, "note": note}
        try:
            self._run(self.client.table(self.HISTORY).insert(row))
        except DatabaseError:
            # The application itself was saved; don't fail the whole request over history.
            logger.warning("Could not write history for application %s", app_id)

    def list_applications(self, *, company=None, role=None, status=None, date_from=None, date_to=None, user_id=None):
        q = self.client.table(self.APPS).select("*")
        if user_id:
            q = q.eq("user_id", user_id)
        if company:
            q = q.ilike("company_name", f"%{_escape_like(company)}%")
        if role:
            q = q.ilike("job_title", f"%{_escape_like(role)}%")
        if status:
            q = q.eq("status", status)
        if date_from:
            q = q.gte("application_date", date_from.isoformat())
        if date_to:
            q = q.lte("application_date", date_to.isoformat())
        q = q.order("created_at", desc=True)
        return self._run(q).data or []

    def get_application(self, app_id, user_id=None):
        q = self.client.table(self.APPS).select("*").eq("id", app_id)
        if user_id:
            q = q.eq("user_id", user_id)
        res = self._run(q.limit(1))
        return res.data[0] if res.data else None

    def create_application(self, data, user_id=None):
        payload = _only_writable(data)
        if user_id:
            payload["user_id"] = user_id
        res = self._run(self.client.table(self.APPS).insert(payload))
        if not res.data:
            raise DatabaseError("The database did not return the saved application.")
        row = res.data[0]
        self._add_history(row["id"], None, row["status"], "Application created")
        return row

    def update_application(self, app_id, data, user_id=None):
        existing = self.get_application(app_id, user_id)
        if existing is None:
            return None
        payload = _only_writable(data)
        q = self.client.table(self.APPS).update(payload).eq("id", app_id)
        if user_id:
            q = q.eq("user_id", user_id)
        res = self._run(q)
        if not res.data:
            return None
        row = res.data[0]
        if "status" in payload and payload["status"] != existing["status"]:
            self._add_history(app_id, existing["status"], payload["status"], None)
        return row

    def delete_application(self, app_id, user_id=None):
        q = self.client.table(self.APPS).delete().eq("id", app_id)
        if user_id:
            q = q.eq("user_id", user_id)
        res = self._run(q)
        return bool(res.data)  # history rows are removed by ON DELETE CASCADE

    def list_history(self, app_id, user_id=None):
        q = (self.client.table(self.HISTORY).select("*")
             .eq("application_id", app_id).order("changed_at", desc=True))
        if user_id:
            owned = self.get_application(app_id, user_id)
            if owned is None:
                return []
        return self._run(q).data or []

    def list_recent_history(self, limit=30, user_id=None):
        q = (self.client.table(self.HISTORY)
             .select("*, job_applications!inner(company_name, job_title, user_id)")
             .order("changed_at", desc=True).limit(limit))
        if user_id:
            q = q.eq("job_applications.user_id", user_id)
        rows = self._run(q).data or []
        for row in rows:  # flatten the joined table
            joined = row.pop("job_applications", None) or {}
            row["company_name"] = joined.get("company_name")
            row["job_title"] = joined.get("job_title")
        return rows

    def count_applications(self, user_id=None):
        q = self.client.table(self.APPS).select("id", count="exact")
        if user_id:
            q = q.eq("user_id", user_id)
        res = self._run(q.limit(1))
        return res.count or 0


# ==========================================================================
# SQLite (demo mode only)
# ==========================================================================
_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_applications (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    company_name TEXT NOT NULL,
    job_title TEXT NOT NULL,
    job_description TEXT,
    job_url TEXT,
    application_date TEXT,
    status TEXT NOT NULL DEFAULT 'Saved',
    follow_up_date TEXT,
    notes TEXT,
    resume_version TEXT,
    location TEXT,
    extracted_info TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS application_history (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES job_applications(id) ON DELETE CASCADE,
    old_status TEXT,
    new_status TEXT NOT NULL,
    note TEXT,
    changed_at TEXT NOT NULL
);
"""


class SQLiteDatabase(Database):
    def __init__(self, path: str) -> None:
        self.path = path
        try:
            with closing(self._connect()) as conn, conn:
                conn.executescript(_SQLITE_SCHEMA)
                columns = {row[1] for row in conn.execute("PRAGMA table_info(job_applications)").fetchall()}
                if "user_id" not in columns:
                    conn.execute("ALTER TABLE job_applications ADD COLUMN user_id TEXT")
        except sqlite3.Error as exc:
            raise DatabaseError(f"Could not open the demo database: {exc}") from exc

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        if d.get("extracted_info"):
            try:
                d["extracted_info"] = json.loads(d["extracted_info"])
            except ValueError:
                d["extracted_info"] = None
        return d

    def _run(self, fn):
        try:
            with closing(self._connect()) as conn, conn:  # `with conn` commits/rolls back
                return fn(conn)
        except sqlite3.Error as exc:
            logger.exception("SQLite error")
            raise DatabaseError(f"Demo database error: {exc}") from exc

    @staticmethod
    def _add_history(conn, app_id, old, new, note):
        conn.execute(
            "INSERT INTO application_history (id, application_id, old_status, new_status, note, changed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), app_id, old, new, note, _now_iso()),
        )

    def list_applications(self, *, company=None, role=None, status=None, date_from=None, date_to=None, user_id=None):
        sql, args = "SELECT * FROM job_applications WHERE 1=1", []
        if user_id:
            sql += " AND user_id = ?"
            args.append(user_id)
        if company:
            sql += " AND company_name LIKE ? ESCAPE '\\'"
            args.append(f"%{_escape_like(company)}%")
        if role:
            sql += " AND job_title LIKE ? ESCAPE '\\'"
            args.append(f"%{_escape_like(role)}%")
        if status:
            sql += " AND status = ?"
            args.append(status)
        if date_from:
            sql += " AND application_date >= ?"
            args.append(date_from.isoformat())
        if date_to:
            sql += " AND application_date <= ?"
            args.append(date_to.isoformat())
        sql += " ORDER BY created_at DESC"
        return self._run(lambda c: [self._to_dict(r) for r in c.execute(sql, args).fetchall()])

    def get_application(self, app_id, user_id=None):
        def op(conn):
            if user_id:
                row = conn.execute("SELECT * FROM job_applications WHERE id = ? AND user_id = ?", (app_id, user_id)).fetchone()
            else:
                row = conn.execute("SELECT * FROM job_applications WHERE id = ?", (app_id,)).fetchone()
            return self._to_dict(row) if row else None
        return self._run(op)

    def create_application(self, data, user_id=None):
        payload = _only_writable(data)
        if user_id:
            payload["user_id"] = user_id
        app_id, now = str(uuid.uuid4()), _now_iso()
        payload.setdefault("status", "Saved")
        if payload.get("extracted_info") is not None:
            payload["extracted_info"] = json.dumps(payload["extracted_info"])

        def op(conn):
            cols = ["id", *payload.keys(), "created_at", "updated_at"]
            vals = [app_id, *payload.values(), now, now]
            conn.execute(
                f"INSERT INTO job_applications ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals
            )
            self._add_history(conn, app_id, None, payload["status"], "Application created")
        self._run(op)
        return self.get_application(app_id)

    def update_application(self, app_id, data, user_id=None):
        payload = _only_writable(data)
        if payload.get("extracted_info") is not None:
            payload["extracted_info"] = json.dumps(payload["extracted_info"])

        def op(conn):
            if user_id:
                row = conn.execute("SELECT status FROM job_applications WHERE id = ? AND user_id = ?", (app_id, user_id)).fetchone()
            else:
                row = conn.execute("SELECT status FROM job_applications WHERE id = ?", (app_id,)).fetchone()
            if row is None:
                return False
            payload["updated_at"] = _now_iso()
            sets = ", ".join(f"{k} = ?" for k in payload)  # keys come from the whitelist
            if user_id:
                conn.execute(f"UPDATE job_applications SET {sets} WHERE id = ? AND user_id = ?", [*payload.values(), app_id, user_id])
            else:
                conn.execute(f"UPDATE job_applications SET {sets} WHERE id = ?", [*payload.values(), app_id])
            if "status" in payload and payload["status"] != row["status"]:
                self._add_history(conn, app_id, row["status"], payload["status"], None)
            return True
        return self.get_application(app_id, user_id) if self._run(op) else None

    def delete_application(self, app_id, user_id=None):
        if user_id:
            return self._run(lambda c: c.execute("DELETE FROM job_applications WHERE id = ? AND user_id = ?", (app_id, user_id)).rowcount > 0)
        return self._run(lambda c: c.execute("DELETE FROM job_applications WHERE id = ?", (app_id,)).rowcount > 0)

    def list_history(self, app_id, user_id=None):
        if user_id and self.get_application(app_id, user_id) is None:
            return []
        sql = "SELECT * FROM application_history WHERE application_id = ? ORDER BY changed_at DESC, rowid DESC"
        return self._run(lambda c: [dict(r) for r in c.execute(sql, (app_id,)).fetchall()])

    def list_recent_history(self, limit=30, user_id=None):
        sql = (
            "SELECT h.*, a.company_name, a.job_title FROM application_history h "
            "JOIN job_applications a ON a.id = h.application_id "
        )
        if user_id:
            sql += "WHERE a.user_id = ? ORDER BY h.changed_at DESC, h.rowid DESC LIMIT ?"
            args = (user_id, limit)
        else:
            sql += "ORDER BY h.changed_at DESC, h.rowid DESC LIMIT ?"
            args = (limit,)
        return self._run(lambda c: [dict(r) for r in c.execute(sql, args).fetchall()])

    def count_applications(self, user_id=None):
        if user_id:
            return self._run(lambda c: c.execute("SELECT COUNT(*) FROM job_applications WHERE user_id = ?", (user_id,)).fetchone()[0])
        return self._run(lambda c: c.execute("SELECT COUNT(*) FROM job_applications").fetchone()[0])


# ==========================================================================
@lru_cache(maxsize=1)
def get_database() -> Database:
    """Create the database object once and reuse it."""
    if settings.demo_mode:
        logger.info("DEMO_MODE: using local SQLite file %s", settings.demo_db_path)
        return SQLiteDatabase(settings.demo_db_path)
    return SupabaseDatabase(settings.supabase_url, settings.supabase_service_key)
