# app.py -- Print Tracker (ONE QR per client email)
# - Scanning QR opens PUBLIC_URL?email=<client_email>
# - When creating a job: re-use existing uploaded QR for that email if present
# - Viewer shows all jobs for an email (stacked)
# - Admin UI protected by ADMIN_PASSWORD (single password), roles selectable after login
# - Sends email with QR attachment if SMTP secrets present
# - Color QR generator with rounded modules, center logo, and large row in Sheets

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

# ---------------------------
# Configuration
# ---------------------------
LOGO_FILENAME = "logo.png"   # put your logo (optional) next to app.py
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

# SMTP email secrets (optional)
EMAIL_HOST = get_secret("EMAIL_HOST")
EMAIL_PORT = get_secret("EMAIL_PORT")
EMAIL_USER = get_secret("EMAIL_USER")
EMAIL_PASS = get_secret("EMAIL_PASS")

# service account pieces for gspread
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

# Quick secrets check
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

# Ensure Jobs sheet exists and header
try:
    try:
        ws = sh.worksheet("Jobs")
    except Exception:
        ws = sh.add_worksheet(title="Jobs", rows="2000", cols="12")

    expected_header = ["job_id", "client_name", "file_name", "client_email", "status", "created_at", "qr_path"]
    current_header = ws.row_values(1)
    if not current_header or current_header[:7] != expected_header:
        ws.clear()
        ws.append_row(expected_header)
except Exception as e:
    st.error("Failed to prepare worksheet 'Jobs'.")
    st.exception(e)
    st.stop()

# ---------------------------
# Utilities
# ---------------------------
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

# QR generator (rounded modules, colored, center logo)
def generate_colored_qr_image(link, save_path,
                              module_px=12,
                              outer_border_px=18,
                              dot_color=(0, 59, 142),
                              bg_color=(255, 235, 59)):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=1,
        border=4
    )
    qr.add_data(link)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    size = len(matrix)

    inner_px = size * module_px
    canvas_px = inner_px + 2 * outer_border_px

    canvas = Image.new("RGB", (canvas_px, canvas_px), dot_color)
    qr_bg = Image.new("RGB", (inner_px, inner_px), bg_color)
    draw = ImageDraw.Draw(qr_bg)

    def module_bbox(x, y):
        return (x * module_px, y * module_px, (x + 1) * module_px, (y + 1) * module_px)

    # Finder pattern drawing (classic)
    finder_positions = [(0, 0), (size - 7, 0), (0, size - 7)]
    for fx, fy in finder_positions:
        draw.rectangle((fx * module_px, fy * module_px, (fx + 7) * module_px, (fy + 7) * module_px), fill=dot_color)
        draw.rectangle(((fx + 1) * module_px, (fy + 1) * module_px, (fx + 6) * module_px, (fy + 6) * module_px), fill=bg_color)
        draw.rectangle(((fx + 2) * module_px, (fy + 2) * module_px, (fx + 5) * module_px, (fy + 5) * module_px), fill=dot_color)

    # Rounded modules for other modules
    radius = int(module_px * 0.35)
    for y in range(size):
        for x in range(size):
            in_finder = any((fx <= x < fx + 7 and fy <= y < fy + 7) for fx, fy in finder_positions)
            if in_finder:
                continue
            if matrix[y][x]:
                bbox = module_bbox(x, y)
                draw.rounded_rectangle(bbox, radius=radius, fill=dot_color)

    # Paste QR area onto blue canvas (outer border)
    canvas.paste(qr_bg, (outer_border_px, outer_border_px))

    # Center logo if provided
    if os.path.exists(LOGO_FILENAME):
        try:
            logo = Image.open(LOGO_FILENAME).convert("RGBA")
            max_logo_w = int(inner_px * 0.20)
            max_logo_h = int(inner_px * 0.20)
            logo.thumbnail((max_logo_w, max_logo_h), Image.LANCZOS)

            logo_bg_size = (logo.size[0] + 10, logo.size[1] + 10)
            logo_bg = Image.new("RGBA", logo_bg_size, (255, 255, 255, 255))
            mask = Image.new("L", logo_bg_size, 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([0, 0, logo_bg_size[0], logo_bg_size[1]], radius=int(min(logo_bg_size) / 4), fill=255)
            logo_bg.putalpha(mask)

            lx = (logo_bg_size[0] - logo.size[0]) // 2
            ly = (logo_bg_size[1] - logo.size[1]) // 2
            logo_bg.paste(logo, (lx, ly), logo)

            cx = canvas_px // 2
            cy = canvas_px // 2
            canvas = canvas.convert("RGBA")
            canvas.paste(logo_bg, (cx - logo_bg_size[0]//2, cy - logo_bg_size[1]//2), logo_bg)
            canvas = canvas.convert("RGB")
        except Exception:
            pass

    canvas.save(save_path, format="PNG", optimize=True)

# ---------------------------
# Core functions that implement one-QR-per-email logic
# ---------------------------
def find_existing_qr_for_email(email):
    """Search sheet for any row with matching client_email and a non-empty qr_path that includes a URL.
       Returns the public_url string or None."""
    try:
        records = ws.get_all_records()
        for r in records:
            cell_email = str(r.get("client_email") or "").strip().lower()
            if cell_email == str(email).strip().lower():
                qr_cell = r.get("qr_path", "") or ""
                # if cell contains =IMAGE("...") extract URL
                if isinstance(qr_cell, str):
                    if qr_cell.startswith('=IMAGE("') and '"' in qr_cell[8:]:
                        # safe extraction
                        try:
                            url = qr_cell.split('"')[1]
                            if url.startswith("http"):
                                return url
                        except Exception:
                            pass
                    # if cell already contains URL directly
                    if qr_cell.startswith("http"):
                        return qr_cell
        return None
    except Exception:
        return None

def generate_qr_and_upload_for_email(email):
    """Creates QR that links to PUBLIC_URL?email=<email>, uploads once, returns public_url and local_path."""
    link = f"{PUBLIC_URL}?email={requests.utils.requote_uri(email)}"
    safe_name = email.replace("@", "_at_").replace(".", "_")
    local_path = os.path.join(QR_DIR, f"{safe_name}.png")
    generate_colored_qr_image(link, local_path)
    public_url = upload_to_imgbb(local_path)
    return local_path, public_url

def generate_qr_and_upload(job_id):
    # kept for backward compatibility but not used directly in create flow
    link = f"{PUBLIC_URL}?job_id={job_id}"
    local_path = os.path.join(QR_DIR, f"{job_id}.png")
    generate_colored_qr_image(link, local_path)
    public_url = upload_to_imgbb(local_path)
    return local_path, public_url

def load_jobs_df():
    records = ws.get_all_records()
    return pd.DataFrame(records)

def append_job_row(values):
    ws.append_row(values)

def update_status_in_sheet(job_id, new_status):
    records = ws.get_all_records()
    for i, r in enumerate(records, start=2):
        if str(r.get("job_id")) == str(job_id):
            ws.update_cell(i, 5, new_status)  # status is column 5
            return True
    return False

def resize_row_height(ws_obj, row_number, height=220):
    body = {
        "requests": [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws_obj.id,
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
    ws_obj.spreadsheet.batch_update(body)

# ---------------------------
# Email sending (optional)
# ---------------------------
def send_qr_email_smtp(to_email, client_name, job_id, qr_url, local_qr_path):
    if not (EMAIL_HOST and EMAIL_PORT and EMAIL_USER and EMAIL_PASS):
        return False, "Missing SMTP secrets."
    try:
        msg = EmailMessage()
        msg["Subject"] = f"Microcadd — Print Job QR ({job_id})"
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        body = f"""Hello {client_name},

Your print job {job_id} has been created.

Track your jobs here:
{PUBLIC_URL}?email={to_email}

Thanks,
Microcadd
"""
        msg.set_content(body)
        with open(local_qr_path, "rb") as f:
            img_data = f.read()
        msg.add_attachment(img_data, maintype="image", subtype="png", filename=f"{job_id}.png")

        server = smtplib.SMTP(EMAIL_HOST, int(EMAIL_PORT))
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)

# ---------------------------
# Pages
# ---------------------------
def viewer_page():
    st.title("📄 Print Job Status Viewer")

    # Accept email via query param or manual input
    qparams = st.experimental_get_query_params()
    param_email = qparams.get("email", [None])[0]

    email_input = st.text_input("Enter your email to view all your job orders:", value=param_email or "")
    if not email_input:
        st.info("Enter the same email you used when submitting your print job or scan the client QR.")
        return

    df = load_jobs_df()
    if df.empty:
        st.warning("No jobs found.")
        return

    # filter by email (case-insensitive)
    user_jobs = df[df["client_email"].astype(str).str.lower() == email_input.strip().lower()]

    if user_jobs.empty:
        st.error("No job orders found for this email.")
        return

    st.success(f"Found {len(user_jobs)} job order(s) for: **{email_input}**")

    # show as table
    st.subheader("📋 Your Job Orders")
    st.dataframe(user_jobs.reset_index(drop=True))

    # allow selecting a job to show status & QR
    job_id = st.selectbox("Select a job to view its status:", user_jobs["job_id"].tolist())
    selected = user_jobs[user_jobs["job_id"] == job_id].iloc[0]

    st.markdown(f"### 🧾 Job ID: {selected['job_id']}")
    st.markdown(f"**Client:** {selected.get('client_name','')}")
    st.markdown(f"**File:** {selected.get('file_name','')}")
    st.markdown(f"**Created:** {selected.get('created_at','')}")
    st.subheader("📌 Status Progress")
    STATUS_STEPS = ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"]
    current_status = selected.get("status", "Pending")
    try:
        current_index = STATUS_STEPS.index(current_status)
    except Exception:
        current_index = 0

    cols = st.columns(len(STATUS_STEPS))
    for i, step in enumerate(STATUS_STEPS):
        with cols[i]:
            if i < current_index:
                color = "#0A3B99"
            elif i == current_index:
                color = "#FFD800"
            else:
                color = "#D3D3D3"
            st.markdown(
                f"""
                <div style="text-align:center;">
                    <div style="width:40px;height:40px;border-radius:50%;background:{color};border:2px solid #052a66;margin:auto;"></div>
                    <div style="font-size:12px;margin-top:6px">{step}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

    # show QR (we expect qr_path to be =IMAGE("...") or a http url)
    st.subheader("QR Code (Client)")
    qr_cell = selected.get("qr_path", "") or ""
    if isinstance(qr_cell, str) and qr_cell.startswith('=IMAGE("'):
        try:
            url = qr_cell.split('"')[1]
            st.image(url)
        except Exception:
            st.write(qr_cell)
    elif isinstance(qr_cell, str) and qr_cell.startswith("http"):
        st.image(qr_cell)
    else:
        # If selected row didn't contain a qr_path (possible if older rows), try to find other row for same email
        public_url = find_existing_qr_for_email(email_input)
        if public_url:
            st.image(public_url)
        else:
            st.info("No QR available for this email yet.")

def admin_page():
    st.title("🛠 Admin Panel — Restricted Access")

    # login wall
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        password = st.text_input("Enter admin password:", type="password")
        if st.button("Login"):
            if password == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.success("Login successful!")
                st.experimental_rerun()
            else:
                st.error("Incorrect password.")
        st.stop()

    # role selection
    role = st.selectbox("Choose role:", ["Front Desk (create jobs)", "CAD Operator (update status)"])
    df = load_jobs_df()

    # FRONT DESK: create jobs (uses one QR per email)
    if role.startswith("Front Desk"):
        st.subheader("➕ Front Desk — Create Job")
        client = st.text_input("Client Name", key="fd_client")
        file_name = st.text_input("File / Document Name", key="fd_file")
        client_email = st.text_input("Client Email (use client's email):", key="fd_email")

        if st.button("Create Job"):
            if not client or not file_name or not client_email:
                st.error("Please provide client name, file name and client email.")
            else:
                # create new job row
                job_no = len(df) + 1
                job_id = f"MCADD_{str(job_no).zfill(3)}"
                created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    # check for existing uploaded QR for this email
                    existing_url = find_existing_qr_for_email(client_email)
                    if existing_url:
                        public_url = existing_url
                        # reuse - we still write IMAGE(...) into new job row
                    else:
                        # generate one QR per email and upload it
                        local_path, public_url = generate_qr_and_upload_for_email(client_email)

                    qr_formula = f'=IMAGE("{public_url}")'

                    # append job row: job_id, client_name, file_name, client_email, status, created_at, qr_path
                    ws.append_row([job_id, client, file_name, client_email, "Pending", created_at, ""])
                    last_row = len(ws.get_all_values())

                    # update QR column for new row with IMAGE formula
                    ws.update(f"G{last_row}:G{last_row}", [[qr_formula]], value_input_option="USER_ENTERED")

                    # make the row tall so image shows bigger
                    resize_row_height(ws, last_row, height=220)

                    # show generated/used QR in admin UI
                    st.image(public_url, caption="Client QR (re-used if exists)", width=300)

                    # optionally email QR to client
                    if client_email and EMAIL_HOST and EMAIL_PORT and EMAIL_USER and EMAIL_PASS:
                        ok, err = send_qr_email_smtp(client_email, client, job_id, public_url, os.path.join(QR_DIR, client_email.replace("@", "_at_").replace(".", "_") + ".png"))
                        if ok:
                            st.success(f"Job {job_id} created and emailed to {client_email}")
                        else:
                            st.warning(f"Job {job_id} created but email failed: {err}")
                    else:
                        st.success(f"Job {job_id} created.")

                except Exception as e:
                    st.error("Error creating job: " + str(e))

    # CAD operator: update status
    else:
        st.subheader("🔧 CAD Operator — Update Job Status")
        if df.empty:
            st.info("No jobs available.")
        else:
            job_list = df["job_id"].astype(str).tolist()
            chosen = st.selectbox("Select job to update", job_list)
            new_status = st.selectbox("New status", ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"])
            if st.button("Update Status"):
                ok = update_status_in_sheet(chosen, new_status)
                if ok:
                    st.success("Status updated.")
                else:
                    st.error("Failed to update status.")

    # jobs table visible to both roles
    st.subheader("📋 All Jobs (live from sheet)")
    st.dataframe(load_jobs_df())

# ---------------------------
# Navigation
# ---------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["Viewer", "Admin"])
if page == "Viewer":
    viewer_page()
else:
    admin_page()
