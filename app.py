import streamlit as st
import pandas as pd
import qrcode
import os
from datetime import datetime

# -----------------------------------------------------------
# INITIAL SETUP
# -----------------------------------------------------------
CSV_FILE = "jobs.csv"
QR_DIR = "qrcodes"

if not os.path.exists(QR_DIR):
    os.makedirs(QR_DIR)

# Create CSV if missing
if not os.path.exists(CSV_FILE):
    df = pd.DataFrame(columns=["job_id", "client_name", "file_name", "status", "created_at", "qr_path"])
    df.to_csv(CSV_FILE, index=False)


# -----------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------
def load_jobs():
    return pd.read_csv(CSV_FILE)


def save_jobs(df):
    df.to_csv(CSV_FILE, index=False)


def generate_qr(job_id):
    link = f"{st.secrets['PUBLIC_URL']}?job_id={job_id}"
    qr_path = f"{QR_DIR}/{job_id}.png"

    img = qrcode.make(link)
    img.save(qr_path)

    return qr_path, link


# -----------------------------------------------------------
# PAGE: VIEWER
# -----------------------------------------------------------
def viewer_page():
    st.title("📄 Print Job Status Viewer")

    query_params = st.query_params
    job_id = query_params.get("job_id", None)

    if job_id is None:
        st.warning("No job ID provided. Scan your QR code or click your tracking link.")
        return

    df = load_jobs()

    if job_id not in df["job_id"].values:
        st.error("❌ Job ID not found.")
        return

    row = df[df["job_id"] == job_id].iloc[0]

    st.success(f"Job Found: *{job_id}*")
    st.write(f"*Client Name:* {row['client_name']}")
    st.write(f"*File Name:* {row['file_name']}")
    st.write(f"*Created At:* {row['created_at']}")
    st.subheader("📌 Current Status:")

    STATUS_STEPS = [
        "Pending",
        "Checking Document",
        "Printing",
        "Ready for Pickup",
        "Completed",
    ]

    current_status = row["status"]

    # Build circle UI
    current_index = STATUS_STEPS.index(current_status)
    cols = st.columns(len(STATUS_STEPS))

    for i, step in enumerate(STATUS_STEPS):
        with cols[i]:
            if i < current_index:
                color = "#4CAF50"      # green
            elif i == current_index:
                color = "#f7c843"      # yellow
            else:
                color = "#d3d3d3"      # gray

            bold = "font-weight: bold;" if i == current_index else ""

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
# PAGE: ADMIN
# -----------------------------------------------------------
def admin_page():
    st.title("🛠 Admin Panel — Print Job Manager")

    # Admin security
    password = st.text_input("Enter admin password:", type="password")
    if password != st.secrets["ADMIN_PASSWORD"]:
        st.stop()

    st.success("Logged in as Admin")

    df = load_jobs()

    st.subheader("➕ Add New Job")
    client = st.text_input("Client Name")
    file_name = st.text_input("File / Document Name")
    add_btn = st.button("Create Job")

    if add_btn and client and file_name:
        job_id = f"MCADD_{str(len(df)+1).zfill(3)}"
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

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_jobs(df)

        st.success(f"Job created successfully! Job ID: *{job_id}*")
        st.image(qr_path, caption="Scan to track")

        st.write("Tracking Link:")
        st.code(link)

    # Update section
    st.subheader("🔧 Update Job Status")
    job_list = df["job_id"].tolist()
    update_id = st.selectbox("Select Job ID", job_list)
    new_status = st.selectbox("New Status", ["Pending", "Checking Document", "Printing", "Ready for Pickup", "Completed"])
    update_btn = st.button("Update Status")

    if update_btn:
        df.loc[df["job_id"] == update_id, "status"] = new_status
        save_jobs(df)
        st.success(f"{update_id} updated to: {new_status}")

    # Show table
    st.subheader("📋 All Jobs")
    st.dataframe(df)


# -----------------------------------------------------------
# MAIN NAVIGATION
# -----------------------------------------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["Viewer", "Admin"])

if page == "Viewer":
    viewer_page()
else:
    admin_page()
