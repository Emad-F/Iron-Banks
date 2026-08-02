# Iron Banks

A small ACID-safe ledger system with a Streamlit dashboard on top. Every deposit,
withdrawal, and transfer is written to a Postgres-backed ledger, and every
balance change is row-locked so concurrent requests can't corrupt balances.

## What it shows

- **Atomicity** — each deposit, withdrawal, or transfer commits as a single unit or rolls back entirely.
- **Isolation** — row-level locking (`SELECT ... FOR UPDATE`) prevents concurrent operations on the same account from racing.
- **Consistency** — account balances and ledger entries stay aligned after every operation.

## Files

- `db.py` — the schema (`accounts`, `ledger_entries`) and every balance-changing operation (`deposit`, `withdraw`, `transfer_with_lock`). Single source of truth; everything else imports from here.
- `streamlit_dashboard.py` — the UI: view accounts, create accounts, deposit/withdraw/transfer, and browse an account's ledger history.
- `app.py` — a standalone script that fires 5 concurrent transfers between two demo accounts to demonstrate the locking behavior under contention.
- `docker-compose.yml` / `Dockerfile` — runs Postgres and the dashboard together.

## Run it

```
docker compose up --build
```

Then open http://localhost:8501 for the dashboard.

To run the concurrency demo against the same database:

```
docker compose up -d postgres
python -m pip install -r requirements.txt
python app.py
```

## Notes

- Deposits and withdrawals are logged in the ledger against an `EXTERNAL` counterparty, so every balance change — funding an account, cashing out, or moving money between two accounts — is a ledger entry.
- Account balances can never go negative (enforced by a database check constraint and validated before every withdrawal/transfer).
- `transfer_with_lock` locks both accounts in a stable, alphabetical order regardless of transfer direction, which is what prevents two opposite-direction transfers from deadlocking each other.
