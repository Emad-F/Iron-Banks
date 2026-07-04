import os
import socket
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "acid_demo")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "accounts.db"))
POSTGRES_CONNECT_TIMEOUT = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "1"))


def _postgres_is_available() -> bool:
    try:
        with socket.create_connection((DB_HOST, int(DB_PORT)), timeout=0.5):
            return True
    except OSError:
        return False


def _connect_postgres():
    try:
        conn = psycopg.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            row_factory=dict_row,
            connect_timeout=POSTGRES_CONNECT_TIMEOUT,
        )
        conn.backend = "postgres"
        return conn
    except Exception as exc:
        raise RuntimeError(f"Unable to connect to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}: {exc}") from exc


def _connect_sqlite():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.backend = "sqlite"
    return conn


def get_conn():
    if not _postgres_is_available():
        return _connect_sqlite()
    try:
        return _connect_postgres()
    except Exception:
        return _connect_sqlite()


def _now_value() -> Any:
    return datetime.now(timezone.utc)


def _format_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if getattr(conn, "backend", "postgres") == "sqlite":
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        balance REAL NOT NULL DEFAULT 0.0,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id INTEGER NOT NULL REFERENCES accounts(id),
                        amount REAL NOT NULL,
                        type TEXT NOT NULL,
                        note TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            else:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS accounts (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        balance NUMERIC(12, 2) NOT NULL DEFAULT 0.0
                    )
                    """
                )
                cur.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS transactions (
                        id SERIAL PRIMARY KEY,
                        account_id INTEGER NOT NULL REFERENCES accounts(id),
                        amount NUMERIC(12, 2) NOT NULL,
                        type TEXT NOT NULL,
                        note TEXT
                    )
                    """
                )
                cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
            conn.commit()


def create_account(name: str, initial_balance: float = 0.0) -> Dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if getattr(conn, "backend", "postgres") == "sqlite":
                now = _format_now()
                cur.execute(
                    "INSERT INTO accounts (name, created_at, balance) VALUES (?, ?, ?)",
                    (name, now, float(initial_balance)),
                )
                account_id = cur.lastrowid
                if float(initial_balance) != 0.0:
                    cur.execute(
                        "INSERT INTO transactions (account_id, amount, type, note, created_at) VALUES (?, ?, ?, ?, ?)",
                        (account_id, float(initial_balance), "deposit", "Initial balance", now),
                    )
                conn.commit()
                return {"id": account_id, "name": name, "created_at": now, "balance": float(initial_balance)}

            now = _now_value()
            cur.execute(
                "INSERT INTO accounts (name, created_at, balance) VALUES (%s, %s, %s) RETURNING id, name, created_at, balance",
                (name, now, float(initial_balance)),
            )
            row = cur.fetchone()
            account_id = row["id"]
            if float(initial_balance) != 0.0:
                cur.execute(
                    "INSERT INTO transactions (account_id, amount, type, note, created_at) VALUES (%s, %s, %s, %s, %s)",
                    (account_id, float(initial_balance), "deposit", "Initial balance", now),
                )
            conn.commit()
            return dict(row)


def get_accounts() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if getattr(conn, "backend", "postgres") == "sqlite":
                cur.execute("SELECT id, name, created_at, balance FROM accounts ORDER BY id")
            else:
                cur.execute("SELECT id, name, created_at, balance FROM accounts ORDER BY id")
            return [dict(row) for row in cur.fetchall()]


def get_account(account_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if getattr(conn, "backend", "postgres") == "sqlite":
                cur.execute("SELECT id, name, created_at, balance FROM accounts WHERE id = ?", (account_id,))
            else:
                cur.execute("SELECT id, name, created_at, balance FROM accounts WHERE id = %s", (account_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def create_transaction(account_id: int, amount: float, type: str = "deposit", note: Optional[str] = None) -> Dict[str, Any]:
    if type not in ("deposit", "withdrawal"):
        raise ValueError("type must be 'deposit' or 'withdrawal'")
    amt = float(amount)
    if type == "withdrawal":
        amt = -abs(amt)
    else:
        amt = abs(amt)

    with get_conn() as conn:
        with conn.cursor() as cur:
            if getattr(conn, "backend", "postgres") == "sqlite":
                now = _format_now()
                cur.execute("SELECT balance FROM accounts WHERE id = ?", (account_id,))
                row = cur.fetchone()
                if not row:
                    raise ValueError("account not found")
                new_balance = float(row["balance"]) + amt
                cur.execute(
                    "INSERT INTO transactions (account_id, amount, type, note, created_at) VALUES (?, ?, ?, ?, ?)",
                    (account_id, abs(amt), type, note or "", now),
                )
                transaction_id = cur.lastrowid
                cur.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, account_id))
                conn.commit()
                return {"account": get_account(account_id), "transaction_id": transaction_id}

            now = _now_value()
            cur.execute("SELECT balance FROM accounts WHERE id = %s", (account_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("account not found")
            new_balance = float(row["balance"]) + amt
            cur.execute(
                "INSERT INTO transactions (account_id, amount, type, note, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (account_id, abs(amt), type, note or "", now),
            )
            transaction_id = cur.fetchone()["id"]
            cur.execute("UPDATE accounts SET balance = %s WHERE id = %s", (new_balance, account_id))
            conn.commit()
            return {"account": get_account(account_id), "transaction_id": transaction_id}


def get_transactions(account_id: Optional[int] = None, limit: int = 200) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if getattr(conn, "backend", "postgres") == "sqlite":
                if account_id is not None:
                    cur.execute(
                        "SELECT id, account_id, amount, type, note, created_at FROM transactions WHERE account_id = ? ORDER BY id DESC LIMIT ?",
                        (account_id, limit),
                    )
                else:
                    cur.execute(
                        "SELECT id, account_id, amount, type, note, created_at FROM transactions ORDER BY id DESC LIMIT ?",
                        (limit,),
                    )
            else:
                if account_id:
                    cur.execute(
                        "SELECT id, account_id, amount, type, note, created_at FROM transactions WHERE account_id = %s ORDER BY id DESC LIMIT %s",
                        (account_id, limit),
                    )
                else:
                    cur.execute(
                        "SELECT id, account_id, amount, type, note, created_at FROM transactions ORDER BY id DESC LIMIT %s",
                        (limit,),
                    )
            return [dict(row) for row in cur.fetchall()]
