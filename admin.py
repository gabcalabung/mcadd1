import streamlit as st
import pandas as pd
import qrcode
import os

# -------------------------
# Setup
# -------------------------
CSV_FILE = "jobs.csv"
QR_FOLDER = "qrcodes"
VIEWER_URL = "https://mcadd-gabcalabung.streamlit.app/?job="

os.makedirs(QR_FOLDER, exist_ok=True)

# Load or create CSV
if os.path.exists(CSV_FILE):
    df = pd.read_csv(CSV_FILE)
else:
    df = pd.DataFrame(columns=["job_id", "client_name", "description", "status"])
    df.to_csv(CSV_FILE, index=False)

st.title("📋 Admin Panel - Create Job Order & Generate QR Code")

# -------------------------
# Job Order Form
# -------------------------
job_id = st.text_input("Job ID (ex: MCADD-001)")
client_name = st.text_input("Client Name")
description = st.text_area("Description")
status = st.selectbox("Status", ["Pending", "Processing", "Ready for Pickup", "Completed"])

if st.button("Create Job Order"):
    if job_id == "":
        st.error("Job ID is required.")
    elif job_id in df["job_id"].astype(str).values:
        st.error("Job ID already exists.")
    else:
        # Add new row
        new_row = {
            "job_id": job_id,
            "client_name": client_name,
            "description": description,
            "status": status
        }
        df.loc[len(df)] = new_row
        df.to_csv(CSV_FILE, index=False)

        # Generate QR Code
        qr_data = f"{VIEWER_URL}{job_id}"
        img = qrcode.make(qr_data)
        qr_path = f"{QR_FOLDER}/{job_id}.png"
        img.save(qr_path)

        st.success("Job order created successfully!")
        st.image(qr_path, caption="QR Code", use_column_width=False)
        st.write("🔗 QR URL:")
        st.code(qr_data)