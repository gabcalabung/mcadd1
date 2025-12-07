import streamlit as st
import pandas as pd

CSV_FILE = "jobs.csv"

st.title("🔍 Job Order Status Viewer")

# Load CSV safely
try:
    df = pd.read_csv(CSV_FILE)
except:
    st.error("jobs.csv not found or corrupted.")
    st.stop()

# Read job ID from URL
query_params = st.query_params
job_id = query_params.get("job", None)

if job_id is None:
    st.info("Scan the QR code to view your job order.")
    st.stop()

# Filter job
job = df[df["job_id"].astype(str) == str(job_id)]

if job.empty:
    st.error("❌ Job not found. Please check your QR code.")
    st.stop()

# Extract row
job = job.iloc[0]

# Display Job Details
st.subheader(f"📄 Job ID: {job['job_id']}")
st.write(f"*Client Name:* {job['client_name']}")
st.write(f"*Description:* {job['description']}")
st.write(f"*Status:* 🟢 {job['status']}")