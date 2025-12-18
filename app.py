# app.py -- Print Tracker (ONE QR per client email)
# - CODE DEC9/2025 

import streamlit as st
import qrcode
import os
import requests
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import json
import smtplib
from email.message import EmailMessage
from PIL import Image, ImageDraw

# ---------------------------
# PAGE CONFIG
# ---------------------------
st.set_page_config(page_title="Print Tracker", layout="wide")

# ---------------------------
# CUSTOM UI STYLING (ROYAL BLUE + YELLOW)
# ---------------------------
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: 'Segoe UI', sans-serif;
}

/* App background */
.stApp {
    background-color: #F5F7FA;
}

/* Headings */
h1, h2, h3 {
    color: #0A3B99;
    font-weight: 700;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #0A3B99;
}

section[data-testid="stSidebar"] * {
    color: white !important;
    font-weight: 600;
}

/* Buttons */
.stButton > button {
    background-color: #FFD800;
    color: #052A66;
    border-radius: 8px;
    padding: 0.6rem 1.2rem;
    font-weight: 700;
    border: none;
}

.stButton > button:hover {
    background-color: #E6C200;
}

/* Inputs */
.stTextInput input, .stSelectbox select {
    border-radius: 6px;
    border: 1px solid #0A3B99;
}

/* Cards */
.card {
    background: white;
    padding: 1.5rem;
    border-radius: 14px;
    box-shadow: 0px 4px 12px rgba(0,0,0,0.08);
    margin-bottom: 1.5rem;
}

/* DataFrame */
[data-testid="stDataFrame"] {
    background: white;
    border-radius: 12px;
    padding: 10px;
}

/* Alerts */
.stSuccess {
    background-color: #FFF6CC;
    border-left: 6px solid #FFD800;
}

.stError {
    border-left: 6px solid #C62828;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Configuration
# ---------------------------
LOGO_FILENAME = "logo.png"
QR_DIR = "qrcodes"
os.makedirs(QR_DIR, exist_ok=True)

# ---------------------------
# Helper: read secrets safely
# ---------------------------
def get_secret(key):
    try:
        return st.secrets[key]
    except Exception:
        return None

ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD")
PUBLIC_URL = get_secret("PUBLIC_URL")
SHEET_ID = get_secret("SHEET_ID")
IMGBB_API_KEY = get_secret("IMGBB_API_KEY")

EMAIL_HOST = get_secret("EMAIL_HOST")
EMAIL_PORT = get_secret("EMAIL_PORT")
EMAIL_USER = get_secret("EMAIL_USER")
EMAIL_PASS = get_secret("EMAIL_PASS")

service_account_info = {
    "type": get_secret("type"),
    "project_id": get_secret("project_id"),
    "private_key_id": get_secret("private_key_id"),
    "private_key": get_secret("private_key"),
    "client_email": get_secret("client_email"),
    "client_id": get_secret("client_id"),
    "auth_uri": get_secret("auth_uri"),
    "token_uri": get_secret("token_uri"),
    "auth_provider_x509_cert_url": get_secret("auth_provider_x509_cert_url"),
    "client_x509_cert_url": get_secret("client_x509_cert_url"),
}

missing = [k for k, v in {
    "ADMIN_PASSWORD": ADMIN_PASSWORD,
    "PUBLIC_URL": PUBLIC_URL,
    "SHEET_ID": SHEET_ID,
    "IMGBB_API_KEY": IMGBB_API_KEY,
    "service_account_info.type": service_account_info.get("type"),
}.items() if not v]

if missing:
    st.error("Missing secrets: " + ", ".join(missing))
    st.stop()

# ---------------------------
# GOOGLE SHEETS AUTH
# ---------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
gc = gspread.authorize(credentials)
sh = gc.open_by_key(SHEET_ID)

try:
    ws = sh.worksheet("Jobs")
except Exception:
    ws = sh.add_worksheet(title="Jobs", rows="2000", cols="12")

expected_header = ["job_id", "client_name", "file_name", "client_email", "status", "created_at", "qr_path"]
if ws.row_values(1)[:7] != expected_header:
    ws.clear()
    ws.append_row(expected_header)

# ---------------------------
# UTILITIES
# ---------------------------
def load_jobs_df():
    return pd.DataFrame(ws.get_all_records())

def update_status_in_sheet(job_id, new_status):
    records = ws.get_all_records()
    for i, r in enumerate(records, start=2):
        if str(r.get("job_id")) == str(job_id):
            ws.update_cell(i, 5, new_status)
            return True
    return False

# ---------------------------
# VIEWER PAGE
# ---------------------------
def viewer_page():
    st.markdown("""
    <div class="card">
        <h1>📄 Print Job Status Viewer</h1>
        <p style="color:#555;">Track your print jobs using your registered email.</p>
    </div>
    """, unsafe_allow_html=True)

    email = st.text_input("Enter your email:")

    if not email:
        st.info("Please enter the email you used when submitting your print job.")
        return

    df = load_jobs_df()
    user_jobs = df[df["client_email"].str.lower() == email.lower()]

    if user_jobs.empty:
        st.error("No job orders found.")
        return

    st.success(f"Found {len(user_jobs)} job(s).")
    st.dataframe(user_jobs.reset_index(drop=True))

# ---------------------------
# ADMIN PAGE
# ---------------------------
def admin_page():
    st.markdown("""
    <div class="card">
        <h1>🛠 Admin Panel</h1>
        <p style="color:#555;">Authorized staff access only</p>
    </div>
    """, unsafe_allow_html=True)

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        pwd = st.text_input("Admin Password", type="password")
        if st.button("Login"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.success("Login successful")
                st.rerun()
            else:
                st.error("Incorrect password")
        return

    role = st.selectbox("Choose role:", ["Front Desk (create jobs)", "CAD Operator (update status)"])
    st.markdown(f"""
    <div class="card" style="border-left:8px solid #FFD800;">
        <h3>👤 Current Role: {role}</h3>
    </div>
    """, unsafe_allow_html=True)

    df = load_jobs_df()

    if role.startswith("CAD"):
        job = st.selectbox("Select job:", df["job_id"].tolist())
        status = st.selectbox("New status:", ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"])
        if st.button("Update Status"):
            update_status_in_sheet(job, status)
            st.success("Status updated")

    st.subheader("📋 All Jobs")
    st.dataframe(df)

# ---------------------------
# NAVIGATION
# ---------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["Viewer", "Admin"])

if page == "Viewer":
    viewer_page()
else:
    admin_page()

