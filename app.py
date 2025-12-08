# app.py -- Print Tracker with colored QR (blue dots, yellow background),
# rounded modules, central logo, sheet IMAGE formula and big QR rows.
import streamlit as st
import qrcode
import os
import requests
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
import json
from PIL import Image, ImageDraw, ImageOps

st.set_page_config(page_title="Print Tracker", layout="wide")

# ---------------------------
# Configuration - change only filename if necessary
# ---------------------------
LOGO_FILENAME = "logo.png"   # put your Microcadd logo file here (same folder)
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

# ---------------------------
# QR Generator: rounded modules, colored, center logo, border
# ---------------------------
def generate_colored_qr_image(link, save_path,
                              module_px=12,
                              outer_border_px=18,
                              dot_color=(0, 60, 170),    # darker blue
                              bg_color=(255, 235, 59)):  # yellow
    """
    Draw QR with:
      - rounded modules (drawn as rounded rectangles)
      - finder patterns as solid squares (keeps scannable)
      - small external border (same color as dots) while preserving a quiet zone
      - center logo if available (LOGO_FILENAME)
    """
    # Build QR matrix using qrcode lib
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=1,
        border=4  # keep internal quiet zone (4 modules)
    )
    qr.add_data(link)
    qr.make(fit=True)
    matrix = qr.get_matrix()  # list of lists booleans
    size = len(matrix)  # modules across

    # Pixel size of inner QR area (including quiet zone)
    inner_px = size * module_px

    # final canvas: add an outer border (blue) outside the quiet zone
    canvas_px = inner_px + 2 * outer_border_px

    # Start with blue border canvas
    canvas = Image.new("RGB", (canvas_px, canvas_px), dot_color)

    # QR area (yellow background) will be pasted centered, leaving blue outer border
    qr_bg = Image.new("RGB", (inner_px, inner_px), bg_color)
    draw = ImageDraw.Draw(qr_bg)

    # Helper to convert module (x,y) to pixel coords inside qr_bg
    def module_bbox(x, y):
        return (x * module_px, y * module_px, (x + 1) * module_px, (y + 1) * module_px)

    # Draw finder patterns (top-left, top-right, bottom-left) using classic 7x7 pattern:
    # Outer dark 7x7, inner white 5x5, center dark 3x3 to keep standard structure.
    finder_positions = [(0, 0), (size - 7, 0), (0, size - 7)]
    for fx, fy in finder_positions:
        # outer 7x7 dark
        x0, y0 = fx, fy
        draw.rectangle((x0 * module_px, y0 * module_px, (x0 + 7) * module_px, (y0 + 7) * module_px), fill=dot_color)
        # inner 5x5 white
        draw.rectangle(((x0 + 1) * module_px, (y0 + 1) * module_px, (x0 + 6) * module_px, (y0 + 6) * module_px), fill=bg_color)
        # center 3x3 dark
        draw.rectangle(((x0 + 2) * module_px, (y0 + 2) * module_px, (x0 + 5) * module_px, (y0 + 5) * module_px), fill=dot_color)

    # Draw other modules as rounded rectangles / dots
    radius = int(module_px * 0.35)  # rounding radius
    for y in range(size):
        for x in range(size):
            # skip finder area (already drawn)
            in_finder = any((fx <= x < fx + 7 and fy <= y < fy + 7) for fx, fy in finder_positions)
            if in_finder:
                continue
            if matrix[y][x]:
                bbox = module_bbox(x, y)
                # draw rounded rectangle (rounded square) for "dot" look
                draw.rounded_rectangle(bbox, radius=radius, fill=dot_color)

    # paste QR background (with modules) onto canvas (centered)
    paste_pos = (outer_border_px, outer_border_px)
    canvas.paste(qr_bg, paste_pos)

    # Add a subtle inner quiet zone (ensure the area around finder centers remains clear)
    # [We purposely preserved 4-module quiet zone from qrcode library]

    # Center logo: if available, paste with mask & automatic resizing
    if os.path.exists(LOGO_FILENAME):
        try:
            logo = Image.open(LOGO_FILENAME).convert("RGBA")
            # target logo size = ~20% of inner QR width (so it doesn't break scanning)
            max_logo_w = int(inner_px * 0.20)
            max_logo_h = int(inner_px * 0.20)
            logo.thumbnail((max_logo_w, max_logo_h), Image.LANCZOS)

            # create white-ish circular background for logo so it stands out
            logo_bg_size = (logo.size[0] + 10, logo.size[1] + 10)
            logo_bg = Image.new("RGBA", logo_bg_size, (255, 255, 255, 255))  # white box
            # make it slightly rounded
            mask = Image.new("L", logo_bg_size, 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([0, 0, logo_bg_size[0], logo_bg_size[1]], radius=int(min(logo_bg_size) / 4), fill=255)
            logo_bg.putalpha(mask)

            # composite logo over logo_bg centered
            lx = (logo_bg_size[0] - logo.size[0]) // 2
            ly = (logo_bg_size[1] - logo.size[1]) // 2
            logo_bg.paste(logo, (lx, ly), logo)

            # paste into center of final canvas
            cx = canvas_px // 2
            cy = canvas_px // 2
            top_left = (cx - logo_bg_size[0] // 2, cy - logo_bg_size[1] // 2)
            canvas = canvas.convert("RGBA")
            canvas.paste(logo_bg, top_left, logo_bg)
            canvas = canvas.convert("RGB")
        except Exception:
            # if anything fails with logo, continue without it
            pass

    # Save resulting PNG
    canvas.save(save_path, format="PNG", optimize=True)

# ------------------------------------------------
# Replace older generate function with new one
# ------------------------------------------------
def generate_qr_and_upload(job_id):
    link = f"{PUBLIC_URL}?job_id={job_id}"
    local_path = os.path.join(QR_DIR, f"{job_id}.png")
    generate_colored_qr_image(link, local_path)
    public_url = upload_to_imgbb(local_path)
    return local_path, public_url

# ---------------------------
# Sheet helpers
# ---------------------------
def load_jobs_df():
    records = ws.get_all_records()
    return pd.DataFrame(records)

def append_job_to_sheet(row_values):
    ws.append_row(row_values)

def update_status_in_sheet(job_id, new_status):
    records = ws.get_all_records()
    for i, r in enumerate(records, start=2):  # header is row 1
        if str(r.get("job_id")) == str(job_id):
            ws.update_cell(i, 4, new_status)  # status column index 4
            return True
    return False

def resize_row_height(ws_obj, row_number, height=220):
    """Set row height (pixels) for the Google sheet row. Uses batch_update."""
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
# Pages
# ---------------------------
def viewer_page():
    st.title("📄 Print Job Status Viewer")

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
        st.error("❌ Job ID not found.")
        return

    row = df[df["job_id"].astype(str) == str(job_id_input)].iloc[0]

    st.success(f"Job Found: {job_id_input}")
    st.write(f"Client Name: {row.get('client_name','')}")
    st.write(f"File Name: {row.get('file_name','')}")
    st.write(f"Created At: {row.get('created_at','')}")
    st.subheader("📌 Current Status:")

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
    except ValueError:
        current_index = 0

    cols = st.columns(len(STATUS_STEPS))
    for i, step in enumerate(STATUS_STEPS):
        with cols[i]:
            if i < current_index:
                color = "#0A3B99"  # darker blue for completed steps
            elif i == current_index:
                color = "#FFD800"  # yellow for current
            else:
                color = "#D3D3D3"  # gray for future steps
            bold = "font-weight:bold;" if i == current_index else ""
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
                    <div style="font-size:12px;margin-top:6px;{bold}">{step}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.subheader("QR Code")
    qr_cell = row.get("qr_path", "")
    if isinstance(qr_cell, str) and qr_cell.startswith("=IMAGE("):
        try:
            url = qr_cell.split('"')[1]
            st.image(url, use_column_width=False)
        except Exception:
            st.write(qr_cell)
    elif isinstance(qr_cell, str) and qr_cell.startswith("http"):
        st.image(qr_cell)
    else:
        st.info("No QR available for this job.")

def admin_page():
    st.title("🛠 Admin Panel — Print Job Manager")

    # Admin security
    password = st.text_input("Enter admin password:", type="password")
    if password != ADMIN_PASSWORD:
        st.stop()

    st.success("Logged in as Admin")

    df = load_jobs_df()

    st.subheader("➕ Add New Job")
    client = st.text_input("Client Name")
    file_name = st.text_input("File / Document Name")
    add_btn = st.button("Create Job")

    if add_btn and client and file_name:
        job_id = f"MCADD_{str(len(df)+1).zfill(3)}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            local_path, public_url = generate_qr_and_upload(job_id)

            # insert IMAGE formula so sheet displays the picture
            qr_formula = f'=IMAGE("{public_url}")'

            # Append row with blank qr_path first to ensure proper last-row index
            ws.append_row([job_id, client, file_name, "Pending", created_at, ""])
            last_row = len(ws.get_all_values())

            # Write the IMAGE formula into the QR column as a formula (USER_ENTERED)
            ws.update(f"F{last_row}:F{last_row}", [[qr_formula]], value_input_option="USER_ENTERED")

            # Increase row height so the picture appears large
            resize_row_height(ws, last_row, height=220)

            st.success(f"Job created successfully! Job ID: {job_id}")
            st.image(public_url, caption="QR (uploaded)")

            st.write("Tracking Link:")
            st.code(f"{PUBLIC_URL}?job_id={job_id}")

        except Exception as e:
            st.error("Failed to generate/upload QR: " + str(e))

    # Update section
    st.subheader("🔧 Update Job Status")
    df = load_jobs_df()
    if df.empty:
        st.info("No jobs to update.")
    else:
        job_list = df["job_id"].tolist()
        update_id = st.selectbox("Select Job ID", job_list)
        new_status = st.selectbox("New Status", STATUS_STEPS := ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"])
        update_btn = st.button("Update Status")

        if update_btn:
            df.loc[df["job_id"] == update_id, "status"] = new_status
            ok = update_status_in_sheet(update_id, new_status)
            if ok:
                st.success(f"{update_id} updated to: {new_status}")
            else:
                st.error("Failed to update status in sheet.")

    # Show table
    st.subheader("📋 All Jobs")
    st.dataframe(load_jobs_df())

# ---------------------------
# MAIN NAVIGATION
# ---------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["Viewer", "Admin"])

if page == "Viewer":
    viewer_page()
else:
    admin_page()
