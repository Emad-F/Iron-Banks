# Accounts & Transactions Streamlit Dashboard

This small app provides a Streamlit dashboard to create accounts, post transactions, and view account details and transaction history. It uses a local SQLite database (`data.db`) in the project folder.

Run locally:

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_dashboard.py
```

Notes:
- The database file `data.db` will be created automatically in the project directory.
- Accounts have unique names.
- Transactions are simple `deposit` or `withdrawal` types and update the account balance.
# ACID Transaction Processing Engine

This project demonstrates ACID-style behavior in a small ledger/payments system using PostgreSQL and Python.

## What it shows
- Atomicity: each transfer is committed as a single unit or rolled back entirely.
- Isolation: row-level locking prevents concurrent transfers from corrupting balances.
- Consistency: account balances and ledger entries stay aligned after each transfer.

## Files
- app.py: creates schema, runs transfers, and demonstrates concurrent transfers.
- requirements.txt: Python dependencies.

## Run
1. Install Python dependencies:
   pip install -r requirements.txt
2. Start PostgreSQL and ensure a database named `acid_demo` exists.
3. Run the demo:
   python app.py

## Notes
- The demo uses `SELECT ... FOR UPDATE` so concurrent workers serialize on the same accounts.
- The implementation can be adapted to use `SERIALIZABLE` isolation if you want stronger guarantees for broader transaction patterns.
