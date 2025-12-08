import streamlit as st
import qrcode
import os
import requests
from google.oauth2.service_account import Credentials
import gspread

# ---------------------------
# LOAD SECRETS
# ---------------------------

ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]
PUBLIC_URL = st.secrets["PUBLIC_URL"]
SHEET_ID = st.secrets["SHEET_ID"]
IMGBB_API_KEY = st.secrets["IMGBB_API_KEY"]

# Build the service account dictionary from INDIVIDUAL secret keys
service_account_info = {
    "type": st.secrets["type"],
    "project_id": st.secrets["project_id"],
    "private_key_id": st.secrets["private_key_id"],
    "private_key": st.secrets["private_key"],
    "client_email": st.secrets["client_email"],
    "client_id": st.secrets["client_id"],
    "auth_uri": st.secrets["auth_uri"],
    "token_uri": st.secrets["token_uri"],
    "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
    "client_x509_cert_url": st.secrets["client_x509_cert_url"],
}

# Authenticate Google Sheets
credentials = Credentials.from_service_account_info(service_account_info)
gc = gspread.authorize(credentials)
sheet = gc.open_by_key(SHEET_ID).sheet1


# ---------------------------
# QR UPLOAD TO IMGBB
# ---------------------------
def upload_to_imgbb(image_path):
    with open(image_path, "rb") as file:
        url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": IMGBB_API_KEY,
        }
        response = requests.post(url, payload, files={"image": file})

    data = response.json()
    return data["data"]["url"]  # Direct link to image


# ---------------------------
# QR GENERATOR
# ---------------------------
def generate_qr(job_id):
    filename = f"qr_{job_id}.png"
    img = qrcode.make(f"{PUBLIC_URL}?job={job_id}")

    img.save(filename)
    image_url = upload_to_imgbb(filename)
    os.remove(filename)  # keep storage empty

    return image_url


# ---------------------------
# ADMIN PAGE
# ---------------------------
def admin_page():
    st.title("Admin - Create Print Job")

    file_name = st.text_input("File / Document Name")
    if st.button("Create Job"):
        if not file_name:
            st.error("Please enter a document name.")
            return

        # Generate job ID
        import uuid
        job_id = str(uuid.uuid4())[:8]

        # Generate QR & upload to ImgBB
        qr_link = generate_qr(job_id)

        # Save to Google Sheets
        sheet.append_row([job_id, file_name, "Pending", qr_link])

        st.success("Job Created Successfully!")
        st.image(qr_link, caption="Generated QR Code")
        st.write("Share this QR with the customer:")
        st.write(qr_link)


# ---------------------------
# VIEWER PAGE
# ---------------------------
def viewer_page():
    st.title("Print Job Status Checker")

    job_id = st.text_input("Enter Job ID:")
    if st.button("Check Status"):
        data = sheet.get_all_records()

        for row in data:
            if row["job_id"] == job_id:
                st.success(f"Document: {row['file_name']}")
                st.write(f"Status: {row['status']}")
                st.image(row["qr_link"])
                return

        st.error("Job not found!")


# ---------------------------
# ROUTER
# ---------------------------
mode = st.sidebar.selectbox("Select Mode", ["Viewer", "Admin"])

if mode == "Admin":
    password = st.sidebar.text_input("Enter admin password:", type="password")
    if password == ADMIN_PASSWORD:
        admin_page()
    else:
        st.error("Incorrect password.")
else:
    viewer_page()
