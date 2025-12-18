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

st.set_page_config(page_title="Print Tracker", layout="wide")

# ======================================================
# UI DESIGN (ROYAL BLUE + YELLOW) — VISUAL ONLY
# ======================================================
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: 'Segoe UI', sans-serif;
}

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
}

/* Buttons */
.stButton > button {
    background-color: #FFD800;
    color: #052A66;
    font-weight: 700;
    border-radius: 8px;
    border: none;
    padding: 0.6rem 1.2rem;
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

/* Tables */
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
# Google Sheets auth
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
# Utilities
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
# Viewer Page
# ---------------------------
def viewer_page():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.title("📄 Print Job Status Viewer")

    email = st.text_input("Enter your email to view all your job orders:")

    if not email:
        st.info("Enter the same email you used when submitting your print job.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    df = load_jobs_df()
    user_jobs = df[df["client_email"].astype(str).str.lower() == email.lower()]

    if user_jobs.empty:
        st.error("No job orders found.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    st.success(f"Found {len(user_jobs)} job order(s).")
    st.dataframe(user_jobs.reset_index(drop=True))
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Admin Page
# ---------------------------
def admin_page():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.title("🛠 Admin Panel — Restricted Access")

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        password = st.text_input("Enter admin password:", type="password")
        if st.button("Login"):
            if password == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    role = st.selectbox("Choose role:", ["Front Desk (create jobs)", "CAD Operator (update status)"])
    df = load_jobs_df()

    if role.startswith("CAD"):
        job = st.selectbox("Select job to update", df["job_id"].tolist())
        new_status = st.selectbox("New status", ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"])
        if st.button("Update Status"):
            if update_status_in_sheet(job, new_status):
                st.success("Status updated.")
            else:
                st.error("Failed to update status.")

    st.subheader("📋 All Jobs")
    st.dataframe(df)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Navigation
# ---------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["Viewer", "Admin"])

if page == "Viewer":
    viewer_page()
else:
    admin_page()
