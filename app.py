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

# ---------------------------
# Configuration - change only logo filename if necessary
# ---------------------------
LOGO_FILENAME = "logo.png"   # place your logo file next to app.py
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

# required secrets
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD")
PUBLIC_URL = get_secret("PUBLIC_URL")
SHEET_ID = get_secret("SHEET_ID")
IMGBB_API_KEY = get_secret("IMGBB_API_KEY")

# SMTP email secrets
EMAIL_HOST = get_secret("EMAIL_HOST")
EMAIL_PORT = get_secret("EMAIL_PORT")
EMAIL_USER = get_secret("EMAIL_USER")
EMAIL_PASS = get_secret("EMAIL_PASS")

# google service account pieces
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

# Quick secrets check (not including optional EMAIL fields)
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

# Ensure worksheet exists and header
try:
    try:
        ws = sh.worksheet("Jobs")
    except Exception:
        ws = sh.add_worksheet(title="Jobs", rows="2000", cols="10")

    # expected header (this app assumes this exact order)
    expected_header = ["job_id", "client_name", "file_name", "client_email", "status", "created_at", "qr_path"]
    current_header = ws.row_values(1)
    if not current_header or current_header[:7] != expected_header:
        # If header mismatch, set header to expected (this will overwrite the sheet contents)
        # If you want to keep existing data in a different layout, adapt the sheet to match this header.
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

# QR generator (rounded modules, colored, center logo, border) - same as previous
def generate_colored_qr_image(link, save_path,
                              module_px=12,
                              outer_border_px=18,
                              dot_color=(0, 59, 142),    # DARK BLUE (#003B8E)
                              bg_color=(255, 235, 59)):  # YELLOW (#FFEB3B)
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

    finder_positions = [(0, 0), (size - 7, 0), (0, size - 7)]
    for fx, fy in finder_positions:
        draw.rectangle((fx * module_px, fy * module_px, (fx + 7) * module_px, (fy + 7) * module_px), fill=dot_color)
        draw.rectangle(((fx + 1) * module_px, (fy + 1) * module_px, (fx + 6) * module_px, (fy + 6) * module_px), fill=bg_color)
        draw.rectangle(((fx + 2) * module_px, (fy + 2) * module_px, (fx + 5) * module_px, (fy + 5) * module_px), fill=dot_color)

    radius = int(module_px * 0.35)
    for y in range(size):
        for x in range(size):
            in_finder = any((fx <= x < fx + 7 and fy <= y < fy + 7) for fx, fy in finder_positions)
            if in_finder:
                continue
            if matrix[y][x]:
                bbox = module_bbox(x, y)
                draw.rounded_rectangle(bbox, radius=radius, fill=dot_color)

    paste_pos = (outer_border_px, outer_border_px)
    canvas.paste(qr_bg, paste_pos)

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
            top_left = (cx - logo_bg_size[0] // 2, cy - logo_bg_size[1] // 2)
            canvas = canvas.convert("RGBA")
            canvas.paste(logo_bg, top_left, logo_bg)
            canvas = canvas.convert("RGB")
        except Exception:
            pass

    canvas.save(save_path, format="PNG", optimize=True)

def generate_qr_and_upload(job_id):
    link = f"{PUBLIC_URL}?job_id={job_id}"
    local_path = os.path.join(QR_DIR, f"{job_id}.png")
    generate_colored_qr_image(link, local_path)
    public_url = upload_to_imgbb(local_path)
    return local_path, public_url

def load_jobs_df():
    records = ws.get_all_records()
    return pd.DataFrame(records)

def append_job_to_sheet(row_values):
    ws.append_row(row_values)

def update_status_in_sheet(job_id, new_status):
    records = ws.get_all_records()
    for i, r in enumerate(records, start=2):
        if str(r.get("job_id")) == str(job_id):
            ws.update_cell(i, 5, new_status)  # column 5 (client_email is col 4, status col 5)
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
# Email sender (SMTP)
# ---------------------------
def send_qr_email_smtp(to_email, client_name, job_id, qr_url, local_qr_path):
    """Send email with attached QR PNG via SMTP. Uses EMAIL_* secrets."""
    if not (EMAIL_HOST and EMAIL_PORT and EMAIL_USER and EMAIL_PASS):
        st.warning("Email not sent: SMTP credentials are missing from secrets.")
        return False, "Missing SMTP secrets."

    try:
        msg = EmailMessage()
        msg["Subject"] = f"Your Microcadd Print Job QR Code ({job_id})"
        msg["From"] = EMAIL_USER
        msg["To"] = to_email

        body = f"""Hello {client_name},

Your print job {job_id} is created. Scan the attached QR code or use the link below to track status.

{PUBLIC_URL}?job_id={job_id}

Thanks,
Microcadd
"""
        msg.set_content(body)

        # attach PNG
        with open(local_qr_path, "rb") as f:
            img_data = f.read()
        msg.add_attachment(img_data, maintype="image", subtype="png", filename=f"{job_id}.png")

        # send
        server = smtplib.SMTP(EMAIL_HOST, int(EMAIL_PORT))
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)

# ---------------------------
# UI Pages
# ---------------------------
def viewer_page():
    st.title("📄 Print Job Status Viewer")

    qparams = st.experimental_get_query_params()
    job_param = qparams.get("job_id", [None])[0]

    job_id_input = st.text_input("Enter Job ID:", value=job_param or "")
    if not job_id_input:
        st.info("Scan QR or enter Job ID.")
        return

    df = load_jobs_df()
    if df.empty:
        st.warning("No jobs yet.")
        return

    if job_id_input not in df["job_id"].astype(str).values:
        st.error("Job ID not found.")
        return

    row = df[df["job_id"].astype(str) == str(job_id_input)].iloc[0]

    st.success(f"Job Found: {job_id_input}")

    st.write(f"**Client:** {row.get('client_name','')}")
    st.write(f"**File:** {row.get('file_name','')}")
    st.write(f"**Client Email:** {row.get('client_email','')}")
    st.write(f"**Created At:** {row.get('created_at','')}")

    # -----------------------------------------------------
    # STATUS PROGRESS UI (colored circles)
    # -----------------------------------------------------
    STATUS_STEPS = [
        "Pending",
        "Checking Document",
        "Printing",
        "Ready for Pickup",
        "Completed",
    ]

    current_status = row.get("status", "Pending")

    try:
        current_index = STATUS_STEPS.index(current_status)
    except:
        current_index = 0

    st.subheader("📌 Status Progress")

    cols = st.columns(len(STATUS_STEPS))
    for i, step in enumerate(STATUS_STEPS):
        with cols[i]:

            if i < current_index:
                color = "#0A3B99"     # completed (blue)
            elif i == current_index:
                color = "#FFD800"     # current (yellow)
            else:
                color = "#D3D3D3"     # future (gray)

            highlight = "font-weight:bold;" if i == current_index else ""

            st.markdown(
                f"""
                <div style="text-align:center;">
                    <div style="
                        width:40px;
                        height:40px;
                        border-radius:50%;
                        background:{color};
                        border:2px solid #052a66;
                        margin:auto;">
                    </div>
                    <div style="font-size:12px;margin-top:6px;{highlight}">
                        {step}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    # -----------------------------------------------------
    # QR DISPLAY
    # -----------------------------------------------------
    st.subheader("QR Code")

    qr_cell = row.get("qr_path", "")

    if isinstance(qr_cell, str) and qr_cell.startswith("=IMAGE("):
        try:
            url = qr_cell.split('"')[1]
            st.image(url)
        except:
            st.write(qr_cell)
    elif isinstance(qr_cell, str) and qr_cell.startswith("http"):
        st.image(qr_cell)
    else:
        st.info("No QR available.")

def admin_page():
    st.title("🛠 Admin Panel — Restricted Access")

    # ---------------------------
    # PASSWORD WALL
    # ---------------------------
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        password = st.text_input("Enter admin password:", type="password")
        if st.button("Login"):
            if password == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.success("Login successful!")
            else:
                st.error("Incorrect password.")
        st.stop()  # Stop here until password is correct

    # ---------------------------
    # ROLE SELECTION AFTER LOGIN
    # ---------------------------
    role = st.selectbox("Choose role:", [
        "Front Desk (create jobs)",
        "CAD Operator (update status)"
    ])

    df = load_jobs_df()

    # ---------------------------
    # FRONT DESK — CREATE JOBS
    # ---------------------------
    if role.startswith("Front Desk"):
        st.subheader("➕ Front Desk — Create Job")

        client = st.text_input("Client Name", key="fd_client")
        file_name = st.text_input("File / Document Name", key="fd_file")
        client_email = st.text_input("Client Email", key="fd_email")

        if st.button("Create Job"):
            if not client or not file_name:
                st.error("Please provide client name and file name.")
            else:
                job_no = len(df) + 1
                job_id = f"MCADD_{str(job_no).zfill(3)}"
                created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                try:
                    local_path, public_url = generate_qr_and_upload(job_id)
                    qr_formula = f'=IMAGE("{public_url}")'

                    ws.append_row([job_id, client, file_name, client_email or "",
                                   "Pending", created_at, ""])

                    last_row = len(ws.get_all_values())
                    ws.update(f"G{last_row}:G{last_row}", [[qr_formula]],
                              value_input_option="USER_ENTERED")
                    resize_row_height(ws, last_row, height=220)

                    if client_email:
                        ok, err = send_qr_email_smtp(
                            client_email, client, job_id, public_url, local_path
                        )
                        if ok:
                            st.success(f"Job {job_id} created and emailed to {client_email}")
                        else:
                            st.warning(f"Created but email failed: {err}")
                    else:
                        st.success(f"Job {job_id} created.")
                except Exception as e:
                    st.error("Error creating job: " + str(e))

    # ---------------------------
    # CAD OPERATORS — UPDATE STATUS
    # ---------------------------
    else:
        st.subheader("🔧 CAD Operator — Update Job Status")

        if df.empty:
            st.info("No jobs available.")
        else:
            job_list = df["job_id"].astype(str).tolist()
            chosen = st.selectbox("Select job to update", job_list)

            new_status = st.selectbox(
                "New Status",
                ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"]
            )

            if st.button("Update Status"):
                ok = update_status_in_sheet(chosen, new_status)
                if ok:
                    st.success("Status updated.")
                else:
                    st.error("Failed to update status.")

    # ---------------------------
    # JOB LIST — BOTH ROLES SEE THIS
    # ---------------------------
    st.subheader("📋 All Jobs")
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
