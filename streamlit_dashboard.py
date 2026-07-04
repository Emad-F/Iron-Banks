import streamlit as st
from db import init_db, get_accounts, create_account, get_transactions, create_transaction

# Initialize database
init_db()

st.set_page_config(page_title="Accounts Dashboard", layout="wide")
st.title("Accounts Dashboard")

# Create tabs for navigation - tabs are fast and don't require state management
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
        account_name = st.text_input("Account Name", placeholder="e.g., Checking", key="new_acc_name")
        initial_balance = st.number_input("Initial Balance", value=0.0, step=0.01, key="new_acc_bal")
    
    with col2:
        st.write("")  # spacing
        if st.button("Create Account", use_container_width=True, key="create_acc_btn"):
            if account_name.strip():
                try:
                    new_account = create_account(account_name, initial_balance)
                    st.success(f"✓ Account '{account_name}' created with ID {new_account['id']}")
                except Exception as e:
                    st.error(f"Error creating account: {e}")
            else:
                st.error("Account name cannot be empty")

# TAB 3: Create Transaction
with tab3:
    st.header("Create New Transaction")
    
    accounts = get_accounts()
    if not accounts:
        st.warning("No accounts available. Create one in the 'New Account' tab.")
    else:
        account_names = [acc["name"] for acc in accounts]
        account_map = {acc["name"]: acc["id"] for acc in accounts}
        
        col1, col2 = st.columns(2)
        
        with col1:
            selected_account = st.selectbox("Account", account_names, key="txn_account")
            amount = st.number_input("Amount", value=0.0, step=0.01, key="txn_amount")
        
        with col2:
            transaction_type = st.radio("Type", ["deposit", "withdrawal"], key="txn_type")
            note = st.text_input("Note (optional)", key="txn_note")
        
        if st.button("Create Transaction", use_container_width=True, key="create_txn_btn"):
            if amount > 0:
                try:
                    account_id = account_map[selected_account]
                    transaction = create_transaction(account_id, amount, transaction_type, note)
                    st.success(f"✓ {transaction_type.capitalize()} of ${amount:.2f} created")
                except Exception as e:
                    st.error(f"Error creating transaction: {e}")
            else:
                st.error("Amount must be greater than 0")

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
        
        # Display account info
        col1, col2, col3 = st.columns(3)
        col1.metric("Account ID", acc["id"])
        col2.metric("Balance", f"${acc['balance']:.2f}")
        col3.metric("Created", str(acc["created_at"]))
        
        # Display transactions
        st.write("### Transactions")
        transactions = get_transactions(acc["id"])
        
        if transactions:
            for txn in transactions:
                col1, col2, col3, col4 = st.columns(4)
                col1.write(f"**ID:** {txn['id']}")
                col2.write(f"**Type:** {txn['type']}")
                col3.write(f"**Amount:** ${txn['amount']:.2f}")
                col4.write(f"**Date:** {str(txn['created_at'])}")
                if txn.get('note'):
                    st.caption(f"Note: {txn['note']}")
        else:
            st.info("No transactions for this account")
