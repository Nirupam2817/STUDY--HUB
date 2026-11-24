# Study Hub
Student resource-sharing website built with Python Flask, SQLite, HTML and CSS.

## Run locally
```bash
python -m venv venv
# Windows: venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000.

## Deploy
Push the files to GitHub. On Render, create a Blueprint from this repository (it reads render.yaml), or create a Web Service with build command `pip install -r requirements.txt` and start command `gunicorn app:app`.

The library starts empty. Uploaded files and SQLite data are stored locally; use persistent disk/database and object storage for production so uploads survive redeploys. Add login, moderation and malware scanning before public use.
