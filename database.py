"""
SQLite database layer for ReceiptAI.

Tables:
  users        — registered app users (username + bcrypt password hash)
  receipts     — every scanned receipt (from Receipt AI)
  xray_scans   — every X-Ray Spending Vision analysis
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receiptai.db")


def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                username     TEXT    NOT NULL UNIQUE,
                email        TEXT    NOT NULL UNIQUE,
                password_hash TEXT   NOT NULL,
                created_at   TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS receipts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant        TEXT    NOT NULL,
                amount          REAL    NOT NULL,
                currency        TEXT    NOT NULL DEFAULT 'EUR',
                category        TEXT    NOT NULL DEFAULT 'OTHER',
                receipt_date    TEXT,
                description     TEXT,
                bunq_request_id TEXT,
                items_json      TEXT,
                created_at      TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS xray_scans (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name        TEXT    NOT NULL,
                estimated_price  REAL    NOT NULL,
                currency         TEXT    NOT NULL DEFAULT 'EUR',
                hours_of_work    REAL,
                sp500_10yr       REAL,
                monthly_pct      REAL,
                ai_description   TEXT,
                created_at       TEXT    NOT NULL
            );
        """)


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ── Receipts ──────────────────────────────────────────────────────────────────

def save_receipt(
    merchant: str,
    amount: float,
    currency: str,
    category: str,
    receipt_date: str | None,
    description: str,
    bunq_request_id: str | None,
    items_json: str | None,
) -> int:
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO receipts
               (merchant, amount, currency, category, receipt_date, description,
                bunq_request_id, items_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (merchant, amount, currency, category, receipt_date, description,
             bunq_request_id, items_json, _now()),
        )
        return cur.lastrowid


def list_receipts(limit: int = 50) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM receipts ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def count_receipts() -> int:
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]


# ── X-Ray scans ───────────────────────────────────────────────────────────────

def save_xray(
    item_name: str,
    estimated_price: float,
    currency: str,
    hours_of_work: float,
    sp500_10yr: float,
    monthly_pct: float,
    ai_description: str,
) -> int:
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO xray_scans
               (item_name, estimated_price, currency, hours_of_work, sp500_10yr,
                monthly_pct, ai_description, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (item_name, estimated_price, currency, hours_of_work, sp500_10yr,
             monthly_pct, ai_description, _now()),
        )
        return cur.lastrowid


def list_xray_scans(limit: int = 20) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM xray_scans ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Users ─────────────────────────────────────────────────────────────────────

def create_user(username: str, email: str, password: str) -> int:
    """Hash password and insert a new user. Returns the new user's id."""
    password_hash = generate_password_hash(password)
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?,?,?,?)",
            (username.strip(), email.strip().lower(), password_hash, _now()),
        )
        return cur.lastrowid


def get_user_by_username(username: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def verify_user(username: str, password: str) -> dict | None:
    """Return user dict if credentials are valid, else None."""
    user = get_user_by_username(username)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def list_users() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, username, email, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def count_users() -> int:
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ── DB viewer helpers ─────────────────────────────────────────────────────────

def db_stats() -> dict:
    """Summary counts for the DB viewer page."""
    with _conn() as con:
        return {
            "users":      con.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "receipts":   con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0],
            "xray_scans": con.execute("SELECT COUNT(*) FROM xray_scans").fetchone()[0],
        }

