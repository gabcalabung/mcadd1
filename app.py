# app.py -- Google Sheets + ImgBB + Streamlit (with BIG QR + Gradient Blue→Yellow)
import streamlit as st
import qrcode
import os
import requests
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import json
from PIL import Image, ImageDraw

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

# service account assembled from top-level secrets
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

    values = ws.row_values(1)
    expected_header = ["job_id", "client_name", "file_name", "status", "created_at", "qr_path"]
    if not values or values[:6] != expected_header:
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

# Gradient QR generator (Blue → Yellow)
def generate_gradient_qr(link, save_path):
    qr = qrcode.QRCode(
        version=2,
        box_size=12,
        border=4,
        error_correction=qrcode.constants.ERROR_CORRECT_H
    )
    qr.add_data(link)
    qr.make(fit=True)

    matrix = qr.get_matrix()
    size = len(matrix)

    blue = (0, 87, 255)
    yellow = (255, 235, 59)

    img_size = size * 12
    img = Image.new("RGB", (img_size, img_size), "white")
    draw = ImageDraw.Draw(img)

    for y in range(size):
        for x in range(size):
            if matrix[y][x]:
                t = ((x + y) / (size * 2))
                r = int(blue[0] * (1 - t) + yellow[0] * t)
                g = int(blue[1] * (1 - t) + yellow[1] * t)
                b = int(blue[2] * (1 - t) + yellow[2] * t)
                color = (r, g, b)
                draw.rectangle(
                    [x * 12, y * 12, (x + 1) * 12, (y + 1) * 12],
                    fill=color
                )
    img.save(save_path)


def upload_to_imgbb(image_path):
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
    link = f"{PUBLIC_URL}?job_id={job_id}"
    local_path = os.path.join(QR_DIR, f"{job_id}.png")

    generate_gradient_qr(link, local_path)
    public_url = upload_to_imgbb(local_path)

    return local_path, public_url


def load_jobs_df():
    return pd.DataFrame(ws.get_all_records())


def update_status_in_sheet(job_id, new_status):
    records = ws.get_all_records()
    for i, r in enumerate(records, start=2):
        if str(r.get("job_id")) == str(job_id):
            ws.update_cell(i, 4, new_status)
            return True
    return False


# Resize row height
def resize_row_height(ws, row_number, height=200):
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
                    "fields": "pixelSize"
                }
            }
        ]
    }
    ws.spreadsheet.batch_update(body)


# ---------------------------
# Viewer Page
# ---------------------------
def viewer_page():
    st.title("📄 Print Job Status Viewer")
    df = load_jobs_df()

    qparams = st.experimental_get_query_params()
    job_param = qparams.get("job_id", [None])[0]
    job_id_input = st.text_input("Enter Job ID:", value=job_param or "")

    if not job_id_input:
        return st.info("Scan the QR code or enter Job ID.")

    if job_id_input not in df["job_id"].astype(str).values:
        return st.error("Job ID not found.")

    row = df[df["job_id"] == job_id_input].iloc[0]

    st.write(f"*Client:* {row['client_name']}")
    st.write(f"*File:* {row['file_name']}")
    st.write(f"*Created:* {row['created_at']}")
    st.write(f"*Status:* {row['status']}")

    qr_cell = row.get("qr_path", "")
    st.subheader("QR Code")

    if qr_cell.startswith("=IMAGE("):
        try:
            url = qr_cell.split('"')[1]
            st.image(url)
        except:
            st.write(qr_cell)
    elif qr_cell.startswith("http"):
        st.image(qr_cell)


# ---------------------------
# Admin Page
# ---------------------------
def admin_page():
    st.title("🛠 Admin — Print Job Manager")
    password = st.text_input("Enter admin password:", type="password")

    if password != ADMIN_PASSWORD:
        return st.warning("Enter correct admin password.")

    st.success("Logged in as Admin")

    st.subheader("➕ Create new job")
    client = st.text_input("Client Name")
    file_name = st.text_input("File / Document Name")

    if st.button("Create Job"):
        df = load_jobs_df()
        job_no = len(df) + 1
        job_id = f"MCADD_{str(job_no).zfill(3)}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        local_path, public_url = generate_qr_and_upload(job_id)
        qr_formula = f'=IMAGE("{public_url}")'

        ws.append_row([job_id, client, file_name, "Pending", created_at, ""])
        last_row = len(ws.get_all_values())

        ws.update(f"F{last_row}:F{last_row}", [[qr_formula]], value_input_option="USER_ENTERED")
        resize_row_height(ws, last_row, 200)

        st.success(f"Created job {job_id}")
        st.image(public_url, caption="QR Code")

    # Update status
    df = load_jobs_df()

    st.subheader("🔧 Update Status")
    if df.empty:
        st.info("No jobs yet.")
        return

    chosen = st.selectbox("Select job:", df["job_id"].tolist())
    new_status = st.selectbox("New status:", ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"])

    if st.button("Update Status"):
        if update_status_in_sheet(chosen, new_status):
            st.success("Status updated.")
        else:
            st.error("Update failed.")

    st.subheader("📋 All Jobs (Live)")
    st.dataframe(df)


# ---------------------------
# Navigation
# ---------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Page", ["Viewer", "Admin"])

if page == "Viewer":
    viewer_page()
else:
    admin_page()

