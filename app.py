import streamlit as st
import pandas as pd
import qrcode
import os
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# -----------------------------------------------------------
# GOOGLE SHEETS SETUP
# -----------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)

gc = gspread.authorize(credentials)
sheet = gc.open_by_key(st.secrets["SHEET_ID"]).sheet1   # first worksheet


# -----------------------------------------------------------
# LOAD / SAVE FUNCTIONS (GOOGLE SHEETS)
# -----------------------------------------------------------
def load_jobs():
    data = sheet.get_all_records()
    return pd.DataFrame(data)


def save_row(row_dict):
    """Append a new job to Sheets."""
    sheet.append_row(list(row_dict.values()))


def update_status(job_id, new_status):
    """Update the status column of the selected Job ID."""
    values = sheet.get_all_records()

    for i, row in enumerate(values, start=2):  # header = row 1
        if row["job_id"] == job_id:
            sheet.update_cell(i, 4, new_status)  # column 4 = status
            return True

    return False


# -----------------------------------------------------------
# QR CODE GENERATION
# -----------------------------------------------------------
QR_DIR = "qrcodes"

if not os.path.exists(QR_DIR):
    os.makedirs(QR_DIR)


def generate_qr(job_id):
    link = f"{st.secrets['PUBLIC_URL']}?job_id={job_id}"
    qr_path = f"{QR_DIR}/{job_id}.png"

    img = qrcode.make(link)
    img.save(qr_path)

    return qr_path, link


# -----------------------------------------------------------
# VIEWER PAGE
# -----------------------------------------------------------
def viewer_page():
    st.title("📄 Print Job Status Viewer")

    job_id = st.query_params.get("job_id", None)

    if job_id is None:
        st.warning("No job ID provided. Scan your QR code.")
        return

    df = load_jobs()

    if job_id not in df["job_id"].values:
        st.error("❌ Job ID not found.")
        return

    row = df[df["job_id"] == job_id].iloc[0]

    st.success(f"Job Found: *{job_id}*")
    st.write(f"**Client Name:** {row['client_name']}")
    st.write(f"**File Name:** {row['file_name']}")
    st.write(f"**Created At:** {row['created_at']}")
    st.subheader("📌 Current Status:")

    STATUS_STEPS = [
        "Pending",
        "Checking Document",
        "Printing",
        "Ready for Pickup",
        "Completed",
    ]

    current_status = row["status"]
    current_index = STATUS_STEPS.index(current_status)
    cols = st.columns(len(STATUS_STEPS))

    for i, step in enumerate(STATUS_STEPS):
        with cols[i]:
            if i < current_index:
                color = "#4CAF50"
            elif i == current_index:
                color = "#f7c843"
            else:
                color = "#d3d3d3"

            bold = "font-weight:bold;" if i == current_index else ""

            st.markdown(
                f"""
                <div style="text-align:center;">
                    <div style="
                        width:40px;
                        height:40px;
                        border-radius:50%;
                        background:{color};
                        border:2px solid black;
                        margin:auto;">
                    </div>
                    <div style="font-size:12px;margin-top:5px;{bold}">
                        {step}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )


# -----------------------------------------------------------
# ADMIN PAGE
# -----------------------------------------------------------
def admin_page():
    st.title("🛠 Admin Panel — Print Job Manager")

    password = st.text_input("Enter admin password:", type="password")
    if password != st.secrets["ADMIN_PASSWORD"]:
        st.stop()

    st.success("Logged in as Admin")

    df = load_jobs()

    # --- Add New Job ---
    st.subheader("➕ Add New Job")
    client = st.text_input("Client Name")
    file_name = st.text_input("File / Document Name")
    add_btn = st.button("Create Job")

    if add_btn and client and file_name:
        job_number = len(df) + 1
        job_id = f"MCADD_{str(job_number).zfill(3)}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        qr_path, link = generate_qr(job_id)

        new_row = {
            "job_id": job_id,
            "client_name": client,
            "file_name": file_name,
            "status": "Pending",
            "created_at": created_at,
            "qr_path": qr_path
        }

        save_row(new_row)

        st.success(f"Job Created! ID: {job_id}")
        st.image(qr_path, caption="Scan to Track")
        st.code(link)

    # --- Update Job Status ---
    st.subheader("🔧 Update Job Status")

    df = load_jobs()
    job_list = df["job_id"].tolist()

    update_id = st.selectbox("Select Job ID", job_list)
    new_status = st.selectbox("New Status", [
        "Pending", "Checking Document", "Printing",
        "Ready for Pickup", "Completed"
    ])
    update_btn = st.button("Update Status")

    if update_btn:
        if update_status(update_id, new_status):
            st.success(f"{update_id} updated to {new_status}")
        else:
            st.error("Failed to update status.")

    # --- Job Table ---
    st.subheader("📋 All Jobs")
    st.dataframe(load_jobs())


# -----------------------------------------------------------
# NAVIGATION
# -----------------------------------------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["Viewer", "Admin"])

if page == "Viewer":
    viewer_page()
else:
    admin_page()
