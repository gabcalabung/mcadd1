# viewer.py — final, robust, uses st.query_params
import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Track Job", layout="centered")
st.title("📄 Track Your Print Job (viewer)")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "jobs.csv")

# 1) CSV exists?
if not os.path.exists(CSV_FILE):
    st.error("jobs.csv not found. Ask admin to create a job first.")
    st.stop()

# 2) Read CSV
try:
    df = pd.read_csv(CSV_FILE, dtype=str).fillna("")
except Exception as e:
    st.error(f"Failed to read jobs.csv: {e}")
    st.stop()

# 3) Get job_id from URL param exactly "job_id"
params = st.query_params
job_param = params.get("job_id", None)
if not job_param:
    st.info("No Job ID found in the link. Please scan your QR code or open the exact viewer link.")
    st.stop()

# Normalize (job_param may be list)
job_id = job_param[0] if isinstance(job_param, list) else job_param
job_id = str(job_id).strip()

# 4) Ensure column exists
if "job_id" not in [c.strip() for c in df.columns]:
    st.error("CSV missing required column 'job_id'. Ensure header is exactly: job_id,client_name,description,status,created_at,qr_path")
    st.stop()

# 5) Find the job
df_cols_normalized = df.copy()
df_cols_normalized.columns = [c.strip() for c in df_cols_normalized.columns]
match = df_cols_normalized[df_cols_normalized["job_id"].astype(str).str.strip() == job_id]

if match.empty:
    st.error("Invalid or unknown Job ID. The QR code may be wrong or the job does not exist.")
    # debug help for admin (only visible locally)
    st.write("Available Job IDs (admin debug):", ", ".join(df_cols_normalized["job_id"].astype(str).tolist()))
    st.stop()

row = match.iloc[0]

st.success("Job Found ✅")
st.write("*Job ID:*", row.get("job_id", ""))
st.write("*Client Name:*", row.get("client_name", ""))
st.write("*Description / File:*", row.get("description", ""))
st.write("*Status:*", row.get("status", ""))

# show QR if present and accessible
qr_path = row.get("qr_path", "")
if qr_path and os.path.exists(qr_path):
    st.write("QR used for this job:")
    st.image(qr_path, width=220)

# friendly status messages
msgs = {
    "Pending": "Your job is received — waiting to be checked.",
    "Checking Document": "We are reviewing your file.",
    "Printing": "Your job is printing now.",
    "Ready for Pick Up": "Your job is ready for pick up.",
    "Completed": "Your job is completed. Thank you!"
}
st.info(msgs.get(row.get("status",""), "Status info not available."))