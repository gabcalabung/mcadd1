# app.py -- Print Tracker with email (SMTP Gmail App Password), roles (Front Desk / CAD),
# colored rounded QR + center logo, Google Sheets IMAGE(), and big QR rows.

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
from PIL import Image, ImageDraw, ImageOps

st.set_page_config(page_title="Print Tracker", layout="wide")

# =========================================================
# 🎨 GLOBAL THEME (UI ONLY — NO LOGIC CHANGED)
# =========================================================
st.markdown("""
<style>
:root {
    --royal-blue: #0A3B99;
    --royal-blue-dark: #052a66;
    --yellow: #FFD800;
    --bg: #f4f6fb;
}

.stApp {
    background-color: var(--bg);
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: var(--royal-blue);
}
section[data-testid="stSidebar"] * {
    color: white !important;
}

/* Headings */
h1, h2, h3 {
    color: var(--royal-blue);
    font-weight: 700;
}

/* Cards */
.card {
    background: white;
    padding: 26px;
    border-radius: 18px;
    box-shadow: 0 8px 20px rgba(0,0,0,0.08);
    margin-bottom: 26px;
}

/* Buttons */
.stButton > button {
    background-color: var(--royal-blue);
    color: white;
    border-radius: 30px;
    padding: 10px 26px;
    font-weight: 600;
    border: none;
}
.stButton > button:hover {
    background-color: var(--yellow);
    color: var(--royal-blue-dark);
}

/* Inputs */
input {
    border-radius: 12px !important;
}

/* Tables */
[data-testid="stDataFrame"] {
    border-radius: 14px;
    overflow: hidden;
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
except:
    ws = sh.add_worksheet(title="Jobs", rows="2000", cols="10")

expected_header = ["job_id", "client_name", "file_name", "client_email", "status", "created_at", "qr_path"]
if not ws.row_values(1) or ws.row_values(1)[:7] != expected_header:
    ws.clear()
    ws.append_row(expected_header)

# ---------------------------
# Utilities (UNCHANGED)
# ---------------------------
def upload_to_imgbb(image_path):
    url = "https://api.imgbb.com/1/upload"
    with open(image_path, "rb") as f:
        resp = requests.post(url, data={"key": IMGBB_API_KEY}, files={"image": f})
    return resp.json()["data"]["url"]

def generate_qr_and_upload(job_id):
    link = f"{PUBLIC_URL}?job_id={job_id}"
    local_path = os.path.join(QR_DIR, f"{job_id}.png")
    qrcode.make(link).save(local_path)
    public_url = upload_to_imgbb(local_path)
    return local_path, public_url

def load_jobs_df():
    return pd.DataFrame(ws.get_all_records())

def update_status_in_sheet(job_id, new_status):
    records = ws.get_all_records()
    for i, r in enumerate(records, start=2):
        if r["job_id"] == job_id:
            ws.update_cell(i, 5, new_status)
            return True
    return False

# ---------------------------
# Viewer Page
# ---------------------------
def viewer_page():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.title("📄 Print Job Status Viewer")
    email_input = st.text_input("Enter your email to view all your job orders:")
    st.markdown('</div>', unsafe_allow_html=True)

    if not email_input:
        return

    df = load_jobs_df()
    user_jobs = df[df["client_email"].str.lower() == email_input.lower()]

    if user_jobs.empty:
        st.error("No job orders found.")
        return

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("📋 Your Job Orders")
    st.dataframe(user_jobs)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Admin Page
# ---------------------------
def admin_page():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.title("🛠 Admin Panel — Restricted Access")
    st.markdown('</div>', unsafe_allow_html=True)

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        password = st.text_input("Enter admin password:", type="password")
        if st.button("Login"):
            if password == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    role = st.selectbox("Choose role:", [
        "Front Desk (create jobs)",
        "CAD Operator (update status)"
    ])

    df = load_jobs_df()

    if role.startswith("Front Desk"):
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("➕ Front Desk — Create Job")

        client = st.text_input("Client Name")
        file_name = st.text_input("File Name")
        client_email = st.text_input("Client Email")

        if st.button("Create Job"):
            job_id = f"MCADD_{len(df)+1:03}"
            local, public = generate_qr_and_upload(job_id)
            ws.append_row([job_id, client, file_name, client_email,
                           "Pending", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), public])
            st.success(f"Job {job_id} created.")
        st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("🔧 CAD Operator — Update Status")
        chosen = st.selectbox("Select job", df["job_id"].tolist())
        new_status = st.selectbox("New Status", ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"])
        if st.button("Update Status"):
            update_status_in_sheet(chosen, new_status)
            st.success("Status updated.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("📋 All Jobs")
    st.dataframe(load_jobs_df())
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Navigation
# ---------------------------
st.sidebar.title("🖨 Microcadd Print Tracker")
page = st.sidebar.radio("Navigation", ["Viewer", "Admin"])

if page == "Viewer":
    viewer_page()
else:
    admin_page()
