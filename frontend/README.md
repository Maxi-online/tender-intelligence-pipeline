# Tender Pipeline Interface

Streamlit interface for the tender/project ingestion and analysis workflow. It uses the backend API rather than embedding a separate extraction pipeline in the UI. See the [root README](../README.md) for source adapters, data flow and validation limits.

Use a separate virtual environment with this directory's `requirements.txt`, then configure the backend URL through the local settings/environment expected by `streamlit_app/utils.py`. The root Docker Compose exposes Streamlit on host port 8501 and the backend on 8001; container-to-container calls use the Compose service address.

The public demonstration uses generated data. Real source exports, account credentials and private project documents are excluded. The root offline tests do not start the interface or establish full UI-to-queue integration; validate that separately against a dedicated local backend.
