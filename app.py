# app.py -- Google Sheets + ImgBB + Streamlit (robust)
import streamlit as st
import qrcode
import os
import requests
import tempfile
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import json
import time

st.set_page_config(page_title="Print Tracker", layout="wide")

# ---------------------------
# Helper: read secrets safely
# ---------------------------
def get_secret(key):
    try:
        return st.secrets[key]
    except Exception:
        return None

# required secrets
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD")
PUBLIC_URL = get_secret("PUBLIC_URL")
SHEET_ID = get_secret("SHEET_ID")
IMGBB_API_KEY = get_secret("IMGBB_API_KEY")

# service account assembled from top-level secrets (your current secrets file layout)
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

# quick secrets check - show a friendly message if missing
missing = [k for k, v in {
    "ADMIN_PASSWORD": ADMIN_PASSWORD,
    "PUBLIC_URL": PUBLIC_URL,
    "SHEET_ID": SHEET_ID,
    "IMGBB_API_KEY": IMGBB_API_KEY,
    "service_account_info.type": service_account_info.get("type"),
}.items() if not v]
if missing:
    st.error("Missing secrets: " + ", ".join(missing))
    st.info("Open Streamlit → Your app → Settings → Secrets and paste the required keys (exact names).")
    st.stop()

# ---------------------------
# Google Sheets auth
# ---------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

try:
    credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(SHEET_ID)
except Exception as e:
    st.error("Failed to authenticate with Google Sheets.")
    st.exception(e)
    st.stop()

# ensure worksheet exists and header is present
try:
    try:
        ws = sh.worksheet("Jobs")
    except Exception:
        ws = sh.add_worksheet(title="Jobs", rows="1000", cols="10")
    # read header
    values = ws.row_values(1)
    expected_header = ["job_id", "client_name", "file_name", "status", "created_at", "qr_path"]
    if not values or values[:6] != expected_header:
        # clear and set header
        ws.clear()
        ws.append_row(expected_header)
except Exception as e:
    st.error("Failed to prepare worksheet 'Jobs'.")
    st.exception(e)
    st.stop()

# ---------------------------
# Utilities
# ---------------------------
QR_DIR = "qrcodes"
os.makedirs(QR_DIR, exist_ok=True)

def upload_to_imgbb(image_path):
    """Uploads local image to ImgBB; returns direct image URL"""
    if not IMGBB_API_KEY:
        raise RuntimeError("IMGBB_API_KEY missing from secrets.")
    url = "https://api.imgbb.com/1/upload"
    with open(image_path, "rb") as f:
        files = {"image": f}
        data = {"key": IMGBB_API_KEY}
        resp = requests.post(url, data=data, files=files, timeout=30)
    resp.raise_for_status()
    j = resp.json()
    if not j.get("success"):
        raise RuntimeError("ImgBB upload failed: " + json.dumps(j))
    return j["data"]["url"]

def generate_qr_and_upload(job_id):
    """Generate QR, upload to imgbb, return public url and local path."""
    link = f"{PUBLIC_URL}?job_id={job_id}"
    local_path = os.path.join(QR_DIR, f"{job_id}.png")
    img = qrcode.make(link)
    img.save(local_path)
    # upload
    public_url = upload_to_imgbb(local_path)
    return local_path, public_url

def load_jobs_df():
    records = ws.get_all_records()
    return pd.DataFrame(records)

def append_job_to_sheet(row_values):
    """row_values: list in same order as header"""
    ws.append_row(row_values)

def update_status_in_sheet(job_id, new_status):
    records = ws.get_all_records()
    for i, r in enumerate(records, start=2):  # header is row 1
        if str(r.get("job_id")) == str(job_id):
            ws.update_cell(i, 4, new_status)  # status column index 4
            return True
    return False

# ---------------------------
# Pages
# ---------------------------
def viewer_page():
    st.title("📄 Print Job Status Viewer")
    # support job_id via query param and manual input
    qparams = st.experimental_get_query_params()
    job_param = qparams.get("job_id", [None])[0]
    job_id_input = st.text_input("Enter Job ID (or scan QR to open link):", value=job_param or "")
    if not job_id_input:
        st.info("Scan the QR code or enter your Job ID.")
        return

    df = load_jobs_df()
    if df.empty:
        st.warning("No jobs yet.")
        return

    if job_id_input not in df["job_id"].astype(str).values:
        st.error("Job ID not found.")
        return

    row = df[df["job_id"].astype(str) == str(job_id_input)].iloc[0]
    st.markdown(f"*Job ID:* {row['job_id']}")
    st.markdown(f"*Client Name:* {row.get('client_name','')}")
    st.markdown(f"*File Name:* {row.get('file_name','')}")
    st.markdown(f"*Created At:* {row.get('created_at','')}")
    st.subheader("Current status")
    STATUS_STEPS = ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"]
    current_status = row.get("status", "Pending")
    try:
        idx = STATUS_STEPS.index(current_status)
    except ValueError:
        idx = 0
    cols = st.columns(len(STATUS_STEPS))
    for i, s in enumerate(STATUS_STEPS):
        with cols[i]:
            if i < idx:
                color = "#4CAF50"
            elif i == idx:
                color = "#f7c843"
            else:
                color = "#d3d3d3"
            st.markdown(f"""
                <div style="text-align:center;">
                  <div style="width:40px;height:40px;border-radius:50%;background:{color};margin:auto;border:1px solid #333"></div>
                  <div style="font-size:12px;margin-top:6px">{s}</div>
                </div>""", unsafe_allow_html=True)
    # show QR if sheet stored formula (=IMAGE...) or plain url
    qr_cell = row.get("qr_path", "")
    if isinstance(qr_cell, str) and qr_cell.startswith("=IMAGE("):
        st.markdown("*QR code (from sheet):*")
        # extract URL inside formula
        try:
            url = qr_cell.split('"')[1]
            st.image(url)
        except Exception:
            st.write(qr_cell)
    elif isinstance(qr_cell, str) and qr_cell.startswith("http"):
        st.image(qr_cell)
    else:
        st.write("No QR available for this job.")

def admin_page():
    st.title("🛠 Admin — Print Job Manager")
    password = st.text_input("Enter admin password:", type="password")
    if password != ADMIN_PASSWORD:
        st.warning("Enter admin password to access the admin panel.")
        return

    st.success("Logged in as Admin")
    st.subheader("➕ Create new job")
    client = st.text_input("Client Name")
    file_name = st.text_input("File / Document Name")
    create = st.button("Create Job")
    if create:
        if not client or not file_name:
            st.error("Please provide client name and file name.")
        else:
            df = load_jobs_df()
            job_no = len(df) + 1
            job_id = f"MCADD_{str(job_no).zfill(3)}"
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                local_path, public_url = generate_qr_and_upload(job_id)
                # insert IMAGE formula so sheet displays the picture
                qr_formula = f'=IMAGE("{public_url}")'
                row = [job_id, client, file_name, "Pending", created_at, qr_formula]
                append_job_to_sheet(row)
                st.success(f"Created job {job_id}")
                st.image(public_url, caption="QR (uploaded)")
            except Exception as e:
                st.error("Failed to generate/upload QR: " + str(e))

    st.subheader("🔧 Update status")
    df = load_jobs_df()
    if df.empty:
        st.info("No jobs to update.")
    else:
        job_list = df["job_id"].astype(str).tolist()
        chosen = st.selectbox("Select job", job_list)
        new_status = st.selectbox("New status", ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"])
        if st.button("Update Status"):
            ok = update_status_in_sheet(chosen, new_status)
            if ok:
                st.success("Status updated.")
            else:
                st.error("Failed to update — make sure the job exists.")

    st.subheader("📋 All jobs (live from sheet)")
    try:
        st.dataframe(load_jobs_df())
    except Exception as e:
        st.error("Failed to load jobs:")
        st.exception(e)

# ---------------------------
# Navigation
# ---------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Page", ["Viewer", "Admin"])

if page == "Viewer":
    viewer_page()
else:
    admin_page()
