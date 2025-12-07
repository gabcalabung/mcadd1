# admin.py — final, debug-friendly
import streamlit as st
import pandas as pd
import qrcode
from io import BytesIO
import os
import uuid
from datetime import datetime

# --- Config: keep as-is. Change VIEWER_BASE_URL only if you change deployment domain later ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "jobs.csv")
QR_FOLDER = os.path.join(BASE_DIR, "qrcodes")
VIEWER_BASE_URL = "https://mcadd-gabcalabung.streamlit.app/"   # homepage viewer (Option B)
# final QR will be VIEWER_BASE_URL + "?job_id=<id>"

os.makedirs(QR_FOLDER, exist_ok=True)

# Ensure CSV exists with correct columns
required_cols = ["job_id", "client_name", "description", "status", "created_at", "qr_path"]
if not os.path.exists(CSV_FILE):
    pd.DataFrame(columns=required_cols).to_csv(CSV_FILE, index=False)

# load dataframe
df = pd.read_csv(CSV_FILE, dtype=str).fillna("")

st.set_page_config(page_title="Admin • Print Tracker", layout="wide")
st.title("🛠 Admin — Print Job Tracker (final)")

st.markdown("*Important:* QR links use parameter job_id. Viewer expects ?job_id=...")

with st.form("create_job", clear_on_submit=True):
    client = st.text_input("Client name")
    descr = st.text_input("File name / short description")
    status = st.selectbox("Initial status", ["Pending", "Checking Document", "Printing", "Ready for Pick Up", "Completed"])
    create = st.form_submit_button("Create job & generate QR")

if create:
    if not client or not descr:
        st.error("Client name and description are required.")
    else:
        new_id = uuid.uuid4().hex[:8].upper()
        created_at = datetime.now().isoformat(sep=" ", timespec="seconds")

        viewer_url = f"{VIEWER_BASE_URL}?job_id={new_id}"

        # Generate QR
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(viewer_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        qr_path = os.path.join(QR_FOLDER, f"{new_id}.png")
        img.save(qr_path)

        # Save to CSV
        new_row = {
            "job_id": new_id,
            "client_name": client,
            "description": descr,
            "status": status,
            "created_at": created_at,
            "qr_path": qr_path
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(CSV_FILE, index=False)

        # Display info & downloadable QR
        bio = BytesIO()
        img.save(bio, format="PNG")
        st.success(f"Job created: {new_id}")
        st.write("*Viewer URL (paste in browser to test):*")
        st.code(viewer_url)
        st.write("*QR (scan or download):*")
        st.image(bio.getvalue(), width=240)
        st.download_button("Download QR (PNG)", data=bio.getvalue(), file_name=f"qr_{new_id}.png", mime="image/png")

st.markdown("---")
st.subheader("Existing jobs (CSV)")
st.dataframe(pd.read_csv(CSV_FILE).astype(str), use_container_width=True)