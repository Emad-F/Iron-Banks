import streamlit as st

from db import (
    create_account,
    deposit,
    get_accounts,
    get_ledger_entries,
    init_db,
    transfer_with_lock,
    withdraw,
)

init_db()

st.set_page_config(page_title="Iron Banks", layout="wide")
st.title("Iron Banks — Accounts Dashboard")

tab1, tab2, tab3, tab4 = st.tabs(["Overview", "New Account", "New Transaction", "Account Details"])

# TAB 1: Overview
with tab1:
    st.header("Accounts Overview")
    accounts = get_accounts()
    if accounts:
        st.write("### All Accounts")
        for acc in accounts:
            col1, col2, col3, col4 = st.columns(4)
            col1.write(f"**ID:** {acc['id']}")
            col2.write(f"**Name:** {acc['name']}")
            col3.write(f"**Balance:** ${acc['balance']:.2f}")
            col4.write(f"**Created:** {str(acc['created_at'])}")
    else:
        st.info("No accounts yet. Create one in the 'New Account' tab.")

# TAB 2: Create Account
with tab2:
    st.header("Create New Account")
    col1, col2 = st.columns(2)
    with col1:
        account_name = st.text_input("Account Name", placeholder="e.g., checking", key="new_acc_name")
        initial_balance = st.number_input(
            "Initial Balance", min_value=0.0, value=0.0, step=0.01, key="new_acc_bal"
        )
    with col2:
        st.write("")  # spacing
        if st.button("Create Account", use_container_width=True, key="create_acc_btn"):
            if account_name.strip():
                try:
                    new_account = create_account(account_name.strip(), initial_balance)
                    st.success(f"✓ Account '{new_account['name']}' created with ID {new_account['id']}")
                except Exception as e:
                    st.error(f"Error creating account: {e}")
            else:
                st.error("Account name cannot be empty")

# TAB 3: New Transaction (deposit / withdrawal / transfer, all ACID-safe)
with tab3:
    st.header("New Transaction")
    accounts = get_accounts()
    if not accounts:
        st.warning("No accounts available. Create one in the 'New Account' tab.")
    else:
        account_names = [acc["name"] for acc in accounts]
        transaction_type = st.radio(
            "Type", ["Deposit", "Withdrawal", "Transfer"], key="txn_type", horizontal=True
        )

        col1, col2 = st.columns(2)
        with col1:
            to_account = None
            if transaction_type == "Transfer":
                from_account = st.selectbox("From Account", account_names, key="txn_from")
                to_options = [n for n in account_names if n != from_account]
                if to_options:
                    to_account = st.selectbox("To Account", to_options, key="txn_to")
                else:
                    st.info("Need at least two accounts to transfer between.")
            else:
                selected_account = st.selectbox("Account", account_names, key="txn_account")
            amount = st.number_input("Amount", min_value=0.0, value=0.0, step=0.01, key="txn_amount")
        with col2:
            note = st.text_input("Note (optional)", key="txn_note")

        if st.button("Submit", use_container_width=True, key="submit_txn_btn"):
            try:
                if amount <= 0:
                    st.error("Amount must be greater than 0")
                elif transaction_type == "Deposit":
                    deposit(amount, selected_account, note or None)
                    st.success(f"✓ Deposited ${amount:.2f} to {selected_account}")
                elif transaction_type == "Withdrawal":
                    withdraw(amount, selected_account, note or None)
                    st.success(f"✓ Withdrew ${amount:.2f} from {selected_account}")
                elif transaction_type == "Transfer":
                    if not to_account:
                        st.error("Need at least two accounts to transfer between")
                    else:
                        transfer_with_lock(amount, from_account, to_account, note or None)
                        st.success(f"✓ Transferred ${amount:.2f} from {from_account} to {to_account}")
            except Exception as e:
                st.error(f"Error: {e}")

# TAB 4: Account Details
with tab4:
    st.header("Account Details")
    accounts = get_accounts()
    if not accounts:
        st.warning("No accounts available. Create one in the 'New Account' tab.")
    else:
        account_names = [acc["name"] for acc in accounts]
        account_map = {acc["name"]: acc for acc in accounts}
        selected_account = st.selectbox("Select Account", account_names, key="detail_account")
        acc = account_map[selected_account]

        col1, col2, col3 = st.columns(3)
        col1.metric("Account ID", acc["id"])
        col2.metric("Balance", f"${acc['balance']:.2f}")
        col3.metric("Created", str(acc["created_at"]))

        st.write("### Ledger History")
        entries = get_ledger_entries(selected_account)
        if entries:
            for e in entries:
                received = e["to_account"] == selected_account
                counterparty = e["from_account"] if received else e["to_account"]
                col1, col2, col3, col4 = st.columns(4)
                col1.write("**↓ received**" if received else "**↑ sent**")
                col2.write(f"**Amount:** ${e['amount']:.2f}")
                col3.write(f"**{'From' if received else 'To'}:** {counterparty}")
                col4.write(f"**Date:** {str(e['created_at'])}")
                if e.get("note"):
                    st.caption(f"Note: {e['note']}")
        else:
            st.info("No ledger entries for this account")
