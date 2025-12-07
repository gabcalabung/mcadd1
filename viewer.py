import streamlit as st
import pandas as pd

st.title("Print Job Status Viewer")

# Load CSV safely
try:
    df = pd.read_csv("jobs.csv")
except:
    st.error("jobs.csv not found.")
    st.stop()

# Try to read job_id from URL
query_params = st.query_params
job_id = query_params.get("job_id", None)

if job_id:
    job_id = str(job_id)
    
    # Find the job in CSV
    job = df[df["job_id"] == job_id]

    if len(job) == 0:
        st.error("Job ID not found.")
    else:
        job = job.iloc[0]

        st.subheader(f"Job ID: {job['job_id']}")
        st.write(f"*Client Name:* {job['client_name']}")
        st.write(f"*Document:* {job['document_name']}")
        st.write(f"*Status:* {job['status']}")
else:
    st.info("Please scan a QR code to view your job status.")
    st.write("No job ID detected in the URL.")
