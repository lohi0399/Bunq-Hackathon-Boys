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

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receiptai.db")


def init_db() -> None:
    """Create tables if they don't exist, migrating the users table if needed."""
    with _conn() as con:
        # Migrate users table to add savings_iban / current_iban if missing
        cols = [row[1] for row in con.execute("PRAGMA table_info(users)").fetchall()]
        if "iban" not in cols or "savings_iban" not in cols:
            con.execute("DROP TABLE IF EXISTS users")
            con.execute("""
                CREATE TABLE users (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    username      TEXT    NOT NULL UNIQUE,
                    iban          TEXT    NOT NULL UNIQUE,
                    savings_iban  TEXT,
                    current_iban  TEXT,
                    bunq_api_key  TEXT    NOT NULL,
                    bunq_user_id  INTEGER NOT NULL,
                    created_at    TEXT    NOT NULL
                )
            """)
        # Check if receipts/xray_scans need user_id migration
        rcols = [row[1] for row in con.execute("PRAGMA table_info(receipts)").fetchall()]
        if rcols and "user_id" not in rcols:
            con.execute("DROP TABLE IF EXISTS receipts")
            con.execute("DROP TABLE IF EXISTS xray_scans")

        con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE,
                iban          TEXT    NOT NULL UNIQUE,
                savings_iban  TEXT,
                current_iban  TEXT,
                bunq_api_key  TEXT    NOT NULL,
                bunq_user_id  INTEGER NOT NULL,
                created_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS receipts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                merchant        TEXT    NOT NULL,
                amount          REAL    NOT NULL,
                currency        TEXT    NOT NULL DEFAULT 'EUR',
                category        TEXT    NOT NULL DEFAULT 'OTHER',
                receipt_date    TEXT,
                description     TEXT,
                bunq_request_id TEXT,
                items_json      TEXT,
                created_at      TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS xray_scans (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                item_name        TEXT    NOT NULL,
                estimated_price  REAL    NOT NULL,
                currency         TEXT    NOT NULL DEFAULT 'EUR',
                hours_of_work    REAL,
                sp500_10yr       REAL,
                monthly_pct      REAL,
                ai_description   TEXT,
                created_at       TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
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
    user_id: int,
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
               (user_id, merchant, amount, currency, category, receipt_date, description,
                bunq_request_id, items_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (user_id, merchant, amount, currency, category, receipt_date, description,
             bunq_request_id, items_json, _now()),
        )
        return cur.lastrowid


def list_receipts(user_id: int, limit: int = 50) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM receipts WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def count_receipts(user_id: int) -> int:
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM receipts WHERE user_id = ?", (user_id,)).fetchone()[0]


# ── X-Ray scans ───────────────────────────────────────────────────────────────

def save_xray(
    user_id: int,
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
               (user_id, item_name, estimated_price, currency, hours_of_work, sp500_10yr,
                monthly_pct, ai_description, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (user_id, item_name, estimated_price, currency, hours_of_work, sp500_10yr,
             monthly_pct, ai_description, _now()),
        )
        return cur.lastrowid


def list_xray_scans(user_id: int, limit: int = 20) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM xray_scans WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def clear_receipts(user_id: int) -> int:
    """Delete all receipts for a user. Returns number of rows deleted."""
    with _conn() as con:
        cur = con.execute("DELETE FROM receipts WHERE user_id = ?", (user_id,))
        return cur.rowcount


def clear_xray_scans(user_id: int) -> int:
    """Delete all X-Ray scans for a user. Returns number of rows deleted."""
    with _conn() as con:
        cur = con.execute("DELETE FROM xray_scans WHERE user_id = ?", (user_id,))
        return cur.rowcount


# ── Users (IBAN-based, no password) ──────────────────────────────────────────

def create_user(username: str, iban: str, bunq_api_key: str, bunq_user_id: int,
                savings_iban: str | None = None, current_iban: str | None = None) -> int:
    """Insert a new user with dual IBANs. Returns the new user's id."""
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO users (username, iban, savings_iban, current_iban, bunq_api_key, bunq_user_id, created_at) VALUES (?,?,?,?,?,?,?)",
            (username.strip(), iban.strip().upper(),
             savings_iban.strip().upper() if savings_iban else None,
             current_iban.strip().upper() if current_iban else None,
             bunq_api_key, bunq_user_id, _now()),
        )
        return cur.lastrowid


def get_user_by_username(username: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_iban(iban: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE iban = ?", (iban.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def list_users() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, username, iban, savings_iban, current_iban, bunq_user_id, created_at FROM users ORDER BY created_at DESC"
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

