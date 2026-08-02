"""
ACID concurrency demo for the Iron Banks ledger.

Fires 5 concurrent transfers between the same two accounts and shows that
the row-locking transfer function in db.py keeps every balance consistent
under contention, instead of letting the transfers race each other.

Run (with the Postgres service from docker-compose.yml up):
    python app.py
"""

import threading
import time

from db import create_account, get_accounts, get_ledger_entries, init_db, transfer_with_lock

DEMO_ACCOUNTS = [("alice", 1000.00), ("bob", 500.00)]


def _seed_demo_accounts() -> None:
    existing = {a["name"] for a in get_accounts()}
    for name, balance in DEMO_ACCOUNTS:
        if name not in existing:
            create_account(name, balance)


def run_concurrency_demo() -> None:
    init_db()
    _seed_demo_accounts()

    start = time.time()
    errors = []

    def worker(i: int) -> None:
        try:
            transfer_with_lock(100.0, "alice", "bob", note="concurrency demo")
        except Exception as exc:
            errors.append((i, str(exc)))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("Balances after concurrent transfers:")
    for row in get_accounts():
        print(f"  {row['name']}: {row['balance']}")
    print("Ledger entries:", len(get_ledger_entries(limit=1000)))
    print("Errors:", errors)
    print("Elapsed seconds:", round(time.time() - start, 3))


if __name__ == "__main__":
    try:
        run_concurrency_demo()
    except Exception as exc:
        print(f"Execution failed: {exc}")
        raise
