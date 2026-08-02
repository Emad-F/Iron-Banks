"""
Database layer for the Iron Banks transaction system.

Single source of truth for the schema and for every operation that changes
a balance. Balance-changing operations take a row lock (SELECT ... FOR
UPDATE) on the affected account(s) inside a transaction, so concurrent
requests serialize safely instead of racing each other.

Postgres only -- this app is meant to run via docker-compose.yml, which
provides a Postgres instance alongside the Streamlit dashboard.
"""

import os
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "acid_demo")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# Counterparty label used in the ledger for deposits/withdrawals -- money
# entering or leaving the system rather than moving between two real
# accounts. It's deliberately not a row in `accounts`.
EXTERNAL = "EXTERNAL"


def get_conn():
    try:
        return psycopg.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            row_factory=dict_row,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Unable to connect to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}: {exc}"
        ) from exc


def init_db() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    balance NUMERIC(12, 2) NOT NULL DEFAULT 0.0 CHECK (balance >= 0),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id SERIAL PRIMARY KEY,
                    from_account TEXT NOT NULL,
                    to_account TEXT NOT NULL,
                    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
                    note TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        conn.commit()


def _log_entry(cur, from_account: str, to_account: str, amount: float, note: Optional[str]) -> int:
    cur.execute(
        """
        INSERT INTO ledger_entries (from_account, to_account, amount, note)
        VALUES (%s, %s, %s, %s) RETURNING id
        """,
        (from_account, to_account, amount, note),
    )
    return cur.fetchone()["id"]


def create_account(name: str, initial_balance: float = 0.0) -> Dict[str, Any]:
    initial_balance = float(initial_balance)
    if initial_balance < 0:
        raise ValueError("initial_balance cannot be negative")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO accounts (name, balance) VALUES (%s, %s)
                RETURNING id, name, balance, created_at
                """,
                (name, initial_balance),
            )
            account = dict(cur.fetchone())
            if initial_balance > 0:
                _log_entry(cur, EXTERNAL, name, initial_balance, "Initial balance")
        conn.commit()
    return account


def get_accounts() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, balance, created_at FROM accounts ORDER BY id")
            return [dict(row) for row in cur.fetchall()]


def get_account(name: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, balance, created_at FROM accounts WHERE name = %s",
                (name,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def deposit(amount: float, account_name: str, note: Optional[str] = None) -> Dict[str, Any]:
    """Credit an account. Row-locked so it can't race a concurrent withdrawal/transfer."""
    amount = float(amount)
    if amount <= 0:
        raise ValueError("amount must be positive")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM accounts WHERE name = %s FOR UPDATE", (account_name,))
            if not cur.fetchone():
                raise ValueError(f"account '{account_name}' does not exist")
            cur.execute("UPDATE accounts SET balance = balance + %s WHERE name = %s", (amount, account_name))
            entry_id = _log_entry(cur, EXTERNAL, account_name, amount, note)
        conn.commit()
    return {"account": get_account(account_name), "ledger_entry_id": entry_id}


def withdraw(amount: float, account_name: str, note: Optional[str] = None) -> Dict[str, Any]:
    """Debit an account. Row-locked, and checks funds before committing."""
    amount = float(amount)
    if amount <= 0:
        raise ValueError("amount must be positive")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM accounts WHERE name = %s FOR UPDATE", (account_name,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"account '{account_name}' does not exist")
            if row["balance"] < amount:
                raise ValueError("insufficient funds")
            cur.execute("UPDATE accounts SET balance = balance - %s WHERE name = %s", (amount, account_name))
            entry_id = _log_entry(cur, account_name, EXTERNAL, amount, note)
        conn.commit()
    return {"account": get_account(account_name), "ledger_entry_id": entry_id}


def transfer_with_lock(amount: float, from_name: str, to_name: str, note: Optional[str] = None) -> Dict[str, Any]:
    """
    Move money between two accounts.

    Locks both account rows -- in a stable, alphabetical order regardless of
    transfer direction -- before reading or writing balances. Locking in a
    consistent order is what prevents two opposite-direction transfers from
    deadlocking each other.
    """
    amount = float(amount)
    if amount <= 0:
        raise ValueError("amount must be positive")
    if from_name == to_name:
        raise ValueError("from and to accounts must be different")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, balance FROM accounts WHERE name IN (%s, %s) ORDER BY name FOR UPDATE",
                (from_name, to_name),
            )
            account_map = {row["name"]: row for row in cur.fetchall()}
            if from_name not in account_map or to_name not in account_map:
                raise ValueError("both accounts must exist")
            if account_map[from_name]["balance"] < amount:
                raise ValueError("insufficient funds")
            cur.execute("UPDATE accounts SET balance = balance - %s WHERE name = %s", (amount, from_name))
            cur.execute("UPDATE accounts SET balance = balance + %s WHERE name = %s", (amount, to_name))
            entry_id = _log_entry(cur, from_name, to_name, amount, note)
        conn.commit()
    return {"from": from_name, "to": to_name, "amount": amount, "ledger_entry_id": entry_id}


def get_ledger_entries(account_name: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if account_name:
                cur.execute(
                    """
                    SELECT id, from_account, to_account, amount, note, created_at
                    FROM ledger_entries
                    WHERE from_account = %s OR to_account = %s
                    ORDER BY id DESC LIMIT %s
                    """,
                    (account_name, account_name, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, from_account, to_account, amount, note, created_at
                    FROM ledger_entries ORDER BY id DESC LIMIT %s
                    """,
                    (limit,),
                )
            return [dict(row) for row in cur.fetchall()]
