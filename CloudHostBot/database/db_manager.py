"""
╔══════════════════════════════════════════════════════════════╗
║                  DATABASE MANAGER                            ║
║         SQLite (persistent) + JSON (fast cache)              ║
╚══════════════════════════════════════════════════════════════╝
"""

import sqlite3
import json
import os
import time
import threading
from typing import Optional, List, Dict, Any
from datetime import datetime

DB_PATH = "database/cloudhost.db"
CACHE_PATH = "database/cache.json"

_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════
#  DATABASE INITIALIZATION
# ══════════════════════════════════════════════════════════════

def get_conn() -> sqlite3.Connection:
    os.makedirs("database", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize all database tables."""
    with get_conn() as conn:
        conn.executescript("""
            -- ─────────────────────── USERS ───────────────────────
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT,
                full_name     TEXT,
                join_date     REAL    DEFAULT (unixepoch()),
                last_activity REAL    DEFAULT (unixepoch()),
                is_active     INTEGER DEFAULT 1,
                is_banned     INTEGER DEFAULT 0,
                role          TEXT    DEFAULT 'user',
                plan          TEXT    DEFAULT 'free',
                plan_expiry   REAL    DEFAULT 0
            );

            -- ─────────────────────── FILES ────────────────────────
            CREATE TABLE IF NOT EXISTS files (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                filename    TEXT    NOT NULL,
                filepath    TEXT    NOT NULL,
                size_bytes  INTEGER DEFAULT 0,
                uploaded_at REAL    DEFAULT (unixepoch()),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- ─────────────────────── PROCESSES ────────────────────
            CREATE TABLE IF NOT EXISTS processes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                pid         INTEGER,
                script_name TEXT    NOT NULL,
                script_path TEXT    NOT NULL,
                started_at  REAL    DEFAULT (unixepoch()),
                status      TEXT    DEFAULT 'running',
                log_file    TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- ─────────────────────── CRON JOBS ────────────────────
            CREATE TABLE IF NOT EXISTS cron_jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                script_name TEXT    NOT NULL,
                cron_expr   TEXT    NOT NULL,
                last_run    REAL    DEFAULT 0,
                next_run    REAL    DEFAULT 0,
                enabled     INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- ─────────────────────── SETTINGS ─────────────────────
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            -- ─────────────────────── ACTION LOGS ──────────────────
            CREATE TABLE IF NOT EXISTS action_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                action     TEXT,
                detail     TEXT,
                timestamp  REAL DEFAULT (unixepoch())
            );

            -- ─────────────────────── MARKETPLACE ──────────────────
            CREATE TABLE IF NOT EXISTS marketplace (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                title       TEXT    NOT NULL,
                description TEXT,
                filename    TEXT    NOT NULL,
                price       INTEGER DEFAULT 0,
                downloads   INTEGER DEFAULT 0,
                created_at  REAL    DEFAULT (unixepoch()),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- Default settings
            INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', '0');
            INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_start_time', CAST(unixepoch() AS TEXT));
        """)
        conn.commit()
    print("✅ Database initialized successfully.")


# ══════════════════════════════════════════════════════════════
#  USER OPERATIONS
# ══════════════════════════════════════════════════════════════

def upsert_user(user_id: int, username: str = "", full_name: str = "") -> Dict:
    """Register or update a user."""
    with _lock:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO users (user_id, username, full_name)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    full_name = excluded.full_name,
                    last_activity = unixepoch()
            """, (user_id, username, full_name))
            conn.commit()
    return get_user(user_id)


def get_user(user_id: int) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_all_users() -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY join_date DESC").fetchall()
        return [dict(r) for r in rows]


def update_user(user_id: int, **kwargs):
    if not kwargs:
        return
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [user_id]
    with _lock:
        with get_conn() as conn:
            conn.execute(f"UPDATE users SET {cols} WHERE user_id = ?", vals)
            conn.commit()


def ban_user(user_id: int):
    update_user(user_id, is_banned=1)


def unban_user(user_id: int):
    update_user(user_id, is_banned=0)


def set_plan(user_id: int, plan: str, days: int = 30):
    expiry = time.time() + (days * 86400) if plan != "free" else 0
    update_user(user_id, plan=plan, plan_expiry=expiry)


def check_plan_expiry(user_id: int):
    """Auto-downgrade expired plans."""
    user = get_user(user_id)
    if user and user["plan"] != "free" and user["plan_expiry"] > 0:
        if time.time() > user["plan_expiry"]:
            update_user(user_id, plan="free", plan_expiry=0)


# ══════════════════════════════════════════════════════════════
#  FILE OPERATIONS
# ══════════════════════════════════════════════════════════════

def add_file(user_id: int, filename: str, filepath: str, size_bytes: int) -> int:
    with _lock:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO files (user_id, filename, filepath, size_bytes) VALUES (?, ?, ?, ?)",
                (user_id, filename, filepath, size_bytes)
            )
            conn.commit()
            return cur.lastrowid


def get_files(user_id: int) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM files WHERE user_id = ? ORDER BY uploaded_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_file_record(file_id: int, user_id: int):
    with _lock:
        with get_conn() as conn:
            conn.execute("DELETE FROM files WHERE id = ? AND user_id = ?", (file_id, user_id))
            conn.commit()


def get_file_by_name(user_id: int, filename: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE user_id = ? AND filename = ?",
            (user_id, filename)
        ).fetchone()
        return dict(row) if row else None


def get_total_storage(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) as total FROM files WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        return row["total"]


# ══════════════════════════════════════════════════════════════
#  PROCESS OPERATIONS
# ══════════════════════════════════════════════════════════════

def add_process(user_id: int, pid: int, script_name: str, script_path: str, log_file: str) -> int:
    with _lock:
        with get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO processes (user_id, pid, script_name, script_path, log_file, status)
                VALUES (?, ?, ?, ?, ?, 'running')
            """, (user_id, pid, script_name, script_path, log_file))
            conn.commit()
            return cur.lastrowid


def get_processes(user_id: int, status: str = "running") -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM processes WHERE user_id = ? AND status = ? ORDER BY started_at DESC",
            (user_id, status)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_running_processes() -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM processes WHERE status = 'running'"
        ).fetchall()
        return [dict(r) for r in rows]


def update_process_status(proc_id: int, status: str):
    with _lock:
        with get_conn() as conn:
            conn.execute("UPDATE processes SET status = ? WHERE id = ?", (status, proc_id))
            conn.commit()


def get_process_by_id(proc_id: int, user_id: int) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM processes WHERE id = ? AND user_id = ?",
            (proc_id, user_id)
        ).fetchone()
        return dict(row) if row else None


# ══════════════════════════════════════════════════════════════
#  SETTINGS OPERATIONS
# ══════════════════════════════════════════════════════════════

def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with _lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
            conn.commit()


def is_maintenance() -> bool:
    return get_setting("maintenance", "0") == "1"


def set_maintenance(on: bool):
    set_setting("maintenance", "1" if on else "0")


# ══════════════════════════════════════════════════════════════
#  LOGGING OPERATIONS
# ══════════════════════════════════════════════════════════════

def log_action(user_id: int, action: str, detail: str = ""):
    with _lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO action_logs (user_id, action, detail) VALUES (?, ?, ?)",
                (user_id, action, detail)
            )
            conn.commit()


def get_recent_logs(limit: int = 50) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM action_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
#  STATS
# ══════════════════════════════════════════════════════════════

def get_global_stats() -> Dict:
    with get_conn() as conn:
        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        total_files = conn.execute("SELECT COUNT(*) as c FROM files").fetchone()["c"]
        total_procs = conn.execute("SELECT COUNT(*) as c FROM processes WHERE status='running'").fetchone()["c"]
        start_time = float(get_setting("bot_start_time", str(time.time())))
        uptime_sec = int(time.time() - start_time)
        return {
            "total_users": total_users,
            "total_files": total_files,
            "running_processes": total_procs,
            "uptime_seconds": uptime_sec,
        }


# ══════════════════════════════════════════════════════════════
#  JSON CACHE
# ══════════════════════════════════════════════════════════════

class JSONCache:
    def __init__(self, path: str = CACHE_PATH):
        self.path = path
        self._data: Dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self._save()

    def delete(self, key: str):
        self._data.pop(key, None)
        self._save()


# Global cache instance
cache = JSONCache()


# ══════════════════════════════════════════════════════════════
#  CRON JOBS
# ══════════════════════════════════════════════════════════════

def add_cron_job(user_id: int, script_name: str, cron_expr: str) -> int:
    with _lock:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO cron_jobs (user_id, script_name, cron_expr) VALUES (?, ?, ?)",
                (user_id, script_name, cron_expr)
            )
            conn.commit()
            return cur.lastrowid


def get_cron_jobs(user_id: int) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM cron_jobs WHERE user_id = ? AND enabled = 1",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_cron_job(job_id: int, user_id: int):
    with _lock:
        with get_conn() as conn:
            conn.execute("DELETE FROM cron_jobs WHERE id = ? AND user_id = ?", (job_id, user_id))
            conn.commit()


# ══════════════════════════════════════════════════════════════
#  MARKETPLACE
# ══════════════════════════════════════════════════════════════

def add_marketplace_item(user_id: int, title: str, description: str, filename: str, price: int = 0) -> int:
    with _lock:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO marketplace (user_id, title, description, filename, price) VALUES (?, ?, ?, ?, ?)",
                (user_id, title, description, filename, price)
            )
            conn.commit()
            return cur.lastrowid


def get_marketplace_items() -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT m.*, u.username FROM marketplace m JOIN users u ON m.user_id = u.user_id ORDER BY m.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
