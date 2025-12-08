# app.py -- Google Sheets + ImgBB + Streamlit + Big QR Rows
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

# required secrets
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD")
PUBLIC_URL = get_secret("PUBLIC_URL")
SHEET_ID = get_secret("SHEET_ID")
IMGBB_API_KEY = get_secret("IMGBB_API_KEY")

# service account assembled from individual top-level fields
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

# quick secrets check
missing = [k for k, v in {
    "ADMIN_PASSWORD": ADMIN_PASSWORD,
    "PUBLIC_URL": PUBLIC_URL,
    "SHEET_ID": SHEET_ID,
    "IMGBB_API_KEY": IMGBB_API_KEY,
    "service_account_info.type": service_account_info.get("type"),
}.items() if not v]

if missing:
    st.error("Missing secrets: " + ", ".join(missing))
    st.info("Check Streamlit Cloud → App → Settings → Secrets")
    st.stop()

# ---------------------------
# Google Sheets Authentication
# ---------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

try:
    credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(SHEET_ID)
except Exception as e:
    st.error("Google Sheets Authentication failed.")
    st.exception(e)
    st.stop()

# ensure worksheet exists
try:
    try:
        ws = sh.worksheet("Jobs")
    except Exception:
        ws = sh.add_worksheet(title="Jobs", rows="1000", cols="10")

    expected_header = ["job_id", "client_name", "file_name", "status", "created_at", "qr_path"]

    values = ws.row_values(1)
    if not values or values[:6] != expected_header:
        ws.clear()
        ws.append_row(expected_header)

except Exception as e:
    st.error("Failed preparing worksheet.")
    st.exception(e)
    st.stop()

# ---------------------------
# Utilities
# ---------------------------
QR_DIR = "qrcodes"
os.makedirs(QR_DIR, exist_ok=True)


def upload_to_imgbb(image_path):
    url = "https://api.imgbb.com/1/upload"
    with open(image_path, "rb") as f:
        files = {"image": f}
        data = {"key": IMGBB_API_KEY}
        resp = requests.post(url, data=data, files=files)
    resp.raise_for_status()
    j = resp.json()
    if not j.get("success"):
        raise RuntimeError("ImgBB upload failed: " + json.dumps(j))
    return j["data"]["url"]


def generate_qr_and_upload(job_id):
    link = f"{PUBLIC_URL}?job_id={job_id}"
    local_path = os.path.join(QR_DIR, f"{job_id}.png")

    img = qrcode.make(link)
    img.save(local_path)

    public_url = upload_to_imgbb(local_path)
    return local_path, public_url


def load_jobs_df():
    records = ws.get_all_records()
    return pd.DataFrame(records)


def append_job_to_sheet(row_values):
    ws.append_row(row_values)


def update_status_in_sheet(job_id, new_status):
    records = ws.get_all_records()
    for i, row in enumerate(records, start=2):
        if str(row.get("job_id")) == str(job_id):
            ws.update_cell(i, 4, new_status)
            return True
    return False


def resize_row_height(ws, row_number, height=180):
    """Makes QR bigger in the Google Sheet."""
    body = {
        "requests": [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "ROWS",
                        "startIndex": row_number - 1,
                        "endIndex": row_number,
                    },
                    "properties": {"pixelSize": height},
                    "fields": "pixelSize",
                }
            }
        ]
    }

    ws.spreadsheet.batch_update(body)


# ---------------------------
# VIEWER PAGE
# ---------------------------
def viewer_page():
    st.title("📄 Print Job Status Viewer")

    qparams = st.experimental_get_query_params()
    job_param = qparams.get("job_id", [None])[0]

    job_id_input = st.text_input("Enter Job ID:", value=job_param or "")
    if not job_id_input:
        return

    df = load_jobs_df()
    if df.empty:
        st.warning("No jobs yet.")
        return

    if job_id_input not in df["job_id"].astype(str).values:
        st.error("Job not found.")
        return

    row = df[df["job_id"] == job_id_input].iloc[0]

    st.write(f"*Client:* {row['client_name']}")
    st.write(f"*File:* {row['file_name']}")
    st.write(f"*Created:* {row['created_at']}")

    st.subheader("Status")
    steps = ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"]

    current_status = row["status"]
    try:
        idx = steps.index(current_status)
    except:
        idx = 0

    cols = st.columns(len(steps))

    for i, step in enumerate(steps):
        with cols[i]:
            color = "#4CAF50" if i < idx else "#f7c843" if i == idx else "#d3d3d3"
            st.markdown(
                f"""
                <div style="text-align:center;">
                  <div style="width:40px;height:40px;border-radius:50%;background:{color};margin:auto;"></div>
                  <div style="font-size:12px;margin-top:4px">{step}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.subheader("QR Code")
    qr_cell = row["qr_path"]

    if qr_cell.startswith("=IMAGE("):
        url = qr_cell.split('"')[1]
        st.image(url)
    else:
        st.write("No QR available.")


# ---------------------------
# ADMIN PAGE
# ---------------------------
def admin_page():
    st.title("🛠 Admin Panel")

    password = st.text_input("Password:", type="password")
    if password != ADMIN_PASSWORD:
        return

    st.success("Logged in!")

    st.subheader("➕ Create New Job")
    client = st.text_input("Client Name")
    file_name = st.text_input("File Name")

    if st.button("Create Job"):
        if not client or not file_name:
            st.error("Fill all fields.")
        else:
            df = load_jobs_df()
            job_id = f"MCADD_{str(len(df) + 1).zfill(3)}"
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                local_path, public_url = generate_qr_and_upload(job_id)

                qr_formula = f'=IMAGE("{public_url}")'

                row = [job_id, client, file_name, "Pending", created_at, qr_formula]
                append_job_to_sheet(row)

                # Resize last row for large QR display
                last_row = len(df) + 2  # header + new row
                resize_row_height(ws, last_row, height=180)

                st.success(f"Created {job_id}")
                st.image(public_url)
            except Exception as e:
                st.error(str(e))

    st.subheader("🔧 Update Status")
    df = load_jobs_df()
    if df.empty:
        st.info("No jobs found.")
    else:
        job = st.selectbox("Pick job", df["job_id"])
        new_status = st.selectbox("New status", ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"])

        if st.button("Update"):
            if update_status_in_sheet(job, new_status):
                st.success("Updated!")
            else:
                st.error("Failed.")


# ---------------------------
# Navigation
# ---------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["Viewer", "Admin"])

if page == "Viewer":
    viewer_page()
else:
    admin_page()
