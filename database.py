"""
SQLite database layer for ReceiptAI.

Tables:
  receipts     — every scanned receipt (from Receipt AI)
  xray_scans   — every X-Ray Spending Vision analysis
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receiptai.db")


def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as con:
        con.executescript("""
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
