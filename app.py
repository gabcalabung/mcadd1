# app.py -- Google Sheets + ImgBB + Streamlit (fully updated & working)
import streamlit as st
import qrcode
import os
import requests
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import json

st.set_page_config(page_title="Print Tracker", layout="wide")


# ---------------------------
# Helper: read secrets safely
# ---------------------------
def get_secret(key):
    try:
        return st.secrets[key]
    except Exception:
        return None


# Required secrets
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD")
PUBLIC_URL = get_secret("PUBLIC_URL")
SHEET_ID = get_secret("SHEET_ID")
IMGBB_API_KEY = get_secret("IMGBB_API_KEY")

# service account (flat layout)
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

# Check required secrets missing
missing = [k for k, v in {
    "ADMIN_PASSWORD": ADMIN_PASSWORD,
    "PUBLIC_URL": PUBLIC_URL,
    "SHEET_ID": SHEET_ID,
    "IMGBB_API_KEY": IMGBB_API_KEY,
    "service_account.type": service_account_info.get("type"),
}.items() if not v]

if missing:
    st.error("❌ Missing secrets: " + ", ".join(missing))
    st.info("Go to Streamlit → Your app → Settings → Secrets and paste the required keys exactly.")
    st.stop()


# ---------------------------
# Google Sheets Authorization
# ---------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

try:
    credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(SHEET_ID)
except Exception as e:
    st.error("❌ Failed to authenticate with Google Sheets.")
    st.exception(e)
    st.stop()


# ---------------------------
# Ensure Worksheet Exists
# ---------------------------
try:
    try:
        ws = sh.worksheet("Jobs")
    except Exception:
        ws = sh.add_worksheet(title="Jobs", rows="1000", cols="10")

    header = ["job_id", "client_name", "file_name", "status", "created_at", "qr_path"]
    first_row = ws.row_values(1)

    if not first_row or first_row[:6] != header:
        ws.clear()
        ws.append_row(header)

except Exception as e:
    st.error("❌ Failed to prepare worksheet.")
    st.exception(e)
    st.stop()


# ---------------------------
# Utilities
# ---------------------------
QR_DIR = "qrcodes"
os.makedirs(QR_DIR, exist_ok=True)


def upload_to_imgbb(image_path):
    """Uploads local QR image to ImgBB and returns public URL"""
    url = "https://api.imgbb.com/1/upload"
    with open(image_path, "rb") as f:
        resp = requests.post(url, data={"key": IMGBB_API_KEY}, files={"image": f})

    data = resp.json()
    if not data.get("success"):
        raise RuntimeError("ImgBB upload failed: " + str(data))

    return data["data"]["url"]


def generate_qr_and_upload(job_id):
    """Generate QR, save locally, upload to ImgBB, return (local_path, public_url)"""
    link = f"{PUBLIC_URL}?job_id={job_id}"
    local_path = os.path.join(QR_DIR, f"{job_id}.png")
    qrcode.make(link).save(local_path)
    public_url = upload_to_imgbb(local_path)
    return local_path, public_url


def load_jobs_df():
    rows = ws.get_all_records()
    return pd.DataFrame(rows)


def update_status_in_sheet(job_id, new_status):
    rows = ws.get_all_records()
    for i, row in enumerate(rows, start=2):
        if row.get("job_id") == job_id:
            ws.update_cell(i, 4, new_status)
            return True
    return False


# ---------------------------
# Viewer Page
# ---------------------------
def viewer_page():
    st.title("📄 Print Job Status Viewer")

    params = st.experimental_get_query_params()
    job_param = params.get("job_id", [None])[0]

    job_id = st.text_input("Enter Job ID:", value=job_param or "")

    if not job_id:
        st.info("Scan the QR code or enter your Job ID.")
        return

    df = load_jobs_df()
    if df.empty or job_id not in df["job_id"].astype(str).values:
        st.error("❌ Job ID not found.")
        return

    row = df[df["job_id"].astype(str) == job_id].iloc[0]

    st.markdown(f"*Client:* {row['client_name']}")
    st.markdown(f"*File:* {row['file_name']}")
    st.markdown(f"*Created:* {row['created_at']}")
    st.subheader("Status")

    STATUS_STEPS = ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"]
    current_status = row["status"]

    cols = st.columns(len(STATUS_STEPS))
    for i, step in enumerate(STATUS_STEPS):
        color = "#d3d3d3"
        if step == current_status:
            color = "#f7c843"
        elif STATUS_STEPS.index(step) < STATUS_STEPS.index(current_status):
            color = "#4CAF50"

        with cols[i]:
            st.markdown(
                f"""
                <div style="text-align:center;">
                    <div style="width:40px;height:40px;border-radius:50%;background:{color};border:1px solid #333;margin:auto;"></div>
                    <div style="font-size:12px;margin-top:6px">{step}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.subheader("QR Code")

    qr_cell = row["qr_path"]
    if qr_cell.startswith("=IMAGE("):
        url = qr_cell.split('"')[1]
        st.image(url)
    elif qr_cell.startswith("http"):
        st.image(qr_cell)
    else:
        st.write("No QR available.")


# ---------------------------
# Admin Page
# ---------------------------
def admin_page():
    st.title("🛠 Admin — Print Job Manager")

    password = st.text_input("Enter admin password:", type="password")
    if password != ADMIN_PASSWORD:
        st.warning("Enter password to proceed.")
        return

    st.success("Logged in as Admin")

    # Create job
    st.subheader("➕ Create New Job")
    client = st.text_input("Client Name")
    file_name = st.text_input("File / Document Name")
    create = st.button("Create Job")

    if create:
        if not client or not file_name:
            st.error("Please fill out all fields.")
        else:
            df = load_jobs_df()
            job_id = f"MCADD_{str(len(df) + 1).zfill(3)}"
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                local_path, img_url = generate_qr_and_upload(job_id)
                qr_formula = f'=IMAGE("{img_url}")'

                # Insert row WITHOUT formula
                ws.append_row([job_id, client, file_name, "Pending", created_at, ""], value_input_option="RAW")

                # Insert formula into last row column F
                last_row = len(ws.get_all_values())
                ws.update_acell(f"F{last_row}", qr_formula, value_input_option="USER_ENTERED")

                st.success(f"Job {job_id} created!")
                st.image(img_url, caption="QR Code")

            except Exception as e:
                st.error("Failed to create job.")
                st.exception(e)

    # Update status
    st.subheader("🔧 Update Status")
    df = load_jobs_df()
    if df.empty:
        st.info("No jobs found.")
    else:
        job_list = df["job_id"].tolist()
        selected = st.selectbox("Select Job", job_list)
        new_status = st.selectbox("New Status", ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"])

        if st.button("Update Status"):
            if update_status_in_sheet(selected, new_status):
                st.success("Status updated.")
            else:
                st.error("Update failed.")

    # Show table
    st.subheader("📋 All Jobs")
    st.dataframe(load_jobs_df())


# ---------------------------
# Navigation
# ---------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Page", ["Viewer", "Admin"])

if page == "Viewer":
    viewer_page()
else:
    admin_page()
