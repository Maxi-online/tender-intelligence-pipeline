# Runtime and configuration

The backend uses `backend/requirements.txt`, PostgreSQL and RabbitMQ/Celery; the interface uses `frontend/requirements.txt`. Review local configuration and Docker Compose before starting the full stack. The configured backend port is 8001 and Streamlit port is 8501. Pure utility checks do not require those services or access to specialized provider APIs.

Use the component navigation and validation boundaries in the root [README](../README.md). Runtime services and external providers are not started by the offline replay.
