import streamlit as st
import pandas as pd
import qrcode
import os

st.title("Admin Panel - Add / Update Print Jobs")

# ---------------------------
# Paths
# ---------------------------
CSV_PATH = "jobs.csv"
QR_FOLDER = "qrcodes"

os.makedirs(QR_FOLDER, exist_ok=True)

# ---------------------------
# Load or create CSV
# ---------------------------
if os.path.exists(CSV_PATH):
    df = pd.read_csv(CSV_PATH)
else:
    df = pd.DataFrame(columns=["job_id", "client_name", "document_name", "status"])
    df.to_csv(CSV_PATH, index=False)

# ---------------------------
# Deployment URL (IMPORTANT)
# ---------------------------
VIEWER_URL = "https://mcadd1-kgumujrvbhewoeq8z6udea.streamlit.app/?job_id="

# ---------------------------
# Admin Inputs
# ---------------------------
st.subheader("Create / Update a Job Order")

job_id = st.text_input("Job ID (Example: MCADD-001)").strip()
client_name = st.text_input("Client Name")
document_name = st.text_input("Document Name")

status = st.selectbox(
    "Update Status",
    ["Pending", "Checking Document", "Printing", "Ready for Pick Up", "Completed"]
)

if st.button("Save Job"):
    if job_id == "":
        st.error("Job ID is required.")
        st.stop()

    # Check if job already exists
    if job_id in df["job_id"].astype(str).values:
        df.loc[df["job_id"] == job_id, ["client_name", "document_name", "status"]] = [
            client_name,
            document_name,
            status,
        ]
        st.success(f"Updated job {job_id}")
    else:
        new_row = {
            "job_id": job_id,
            "client_name": client_name,
            "document_name": document_name,
            "status": status,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        st.success(f"Added new job {job_id}")

    # Save CSV
    df.to_csv(CSV_PATH, index=False)

    # ---------------------------
    # Generate QR Code
    # ---------------------------
    qr_link = VIEWER_URL + job_id
    qr_path = os.path.join(QR_FOLDER, f"{job_id}.png")

    qr_img = qrcode.make(qr_link)
    qr_img.save(qr_path)

    st.subheader("QR Code Generated")
    st.write("Scan this QR code to track the job:")
    st.image(qr_path)
    st.write("URL:", qr_link)

st.divider()

# Show table
