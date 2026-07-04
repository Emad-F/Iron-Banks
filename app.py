import os
import threading
import time
import psycopg
from psycopg.rows import dict_row

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "acid_demo")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")


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
        raise RuntimeError(f"Unable to connect to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}: {exc}") from exc


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    balance NUMERIC(12, 2) NOT NULL CHECK (balance >= 0)
                );

                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id SERIAL PRIMARY KEY,
                    from_account TEXT NOT NULL,
                    to_account TEXT NOT NULL,
                    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute("INSERT INTO accounts(name, balance) VALUES ('alice', 1000.00), ('bob', 500.00) ON CONFLICT (name) DO NOTHING")
            conn.commit()


def transfer(amount: float, from_name: str, to_name: str, isolation_level: str = "SERIALIZABLE") -> dict:
    with get_conn() as conn:
        conn.isolation_level = isolation_level
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, balance FROM accounts WHERE name IN (%s, %s) ORDER BY name", (from_name, to_name))
            rows = cur.fetchall()
            account_map = {row["name"]: row for row in rows}
            if from_name not in account_map or to_name not in account_map:
                raise ValueError("Both accounts must exist")
            from_account = account_map[from_name]
            to_account = account_map[to_name]
            if from_account["balance"] < amount:
                raise ValueError("Insufficient funds")

            cur.execute("SELECT pg_backend_pid()")
            pid = cur.fetchone()["pg_backend_pid"]

            cur.execute(
                "UPDATE accounts SET balance = balance - %s WHERE name = %s",
                (amount, from_name),
            )
            cur.execute(
                "UPDATE accounts SET balance = balance + %s WHERE name = %s",
                (amount, to_name),
            )
            cur.execute(
                "INSERT INTO ledger_entries(from_account, to_account, amount) VALUES (%s, %s, %s)",
                (from_name, to_name, amount),
            )
            conn.commit()
            return {
                "status": "committed",
                "pid": pid,
                "from": from_account["name"],
                "to": to_account["name"],
                "amount": amount,
            }


def transfer_with_lock(amount: float, from_name: str, to_name: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, balance FROM accounts WHERE name IN (%s, %s) ORDER BY name FOR UPDATE", (from_name, to_name))
            rows = cur.fetchall()
            account_map = {row["name"]: row for row in rows}
            if from_name not in account_map or to_name not in account_map:
                raise ValueError("Both accounts must exist")
            from_account = account_map[from_name]
            to_account = account_map[to_name]
            if from_account["balance"] < amount:
                raise ValueError("Insufficient funds")
            cur.execute("UPDATE accounts SET balance = balance - %s WHERE name = %s", (amount, from_name))
            cur.execute("UPDATE accounts SET balance = balance + %s WHERE name = %s", (amount, to_name))
            cur.execute("INSERT INTO ledger_entries(from_account, to_account, amount) VALUES (%s, %s, %s)", (from_name, to_name, amount))
            conn.commit()
            return {"status": "committed", "from": from_account["name"], "to": to_account["name"], "amount": amount}


def run_concurrency_demo():
    init_db()
    start = time.time()
    errors = []

    def worker(i: int):
        try:
            transfer_with_lock(100.0, "alice", "bob")
        except Exception as exc:
            errors.append((i, str(exc)))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name, balance FROM accounts ORDER BY name")
            balances = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS count FROM ledger_entries")
            entries_count = cur.fetchone()["count"]

    print("Balances after concurrent transfers:")
    for row in balances:
        print(row)
    print("Ledger entries:", entries_count)
    print("Errors:", errors)
    print("Elapsed seconds:", round(time.time() - start, 3))


if __name__ == "__main__":
    try:
        run_concurrency_demo()
    except Exception as exc:
        print(f"Execution failed: {exc}")
        raise
