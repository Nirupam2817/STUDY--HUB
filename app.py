
import os
import sqlite3
import uuid
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, send_from_directory, abort
)
from werkzeug.utils import secure_filename

# ---------------- CONFIGURATION ----------------

BASE = os.path.abspath(os.path.dirname(__file__))
TEMPLATE_DIR = os.path.join(BASE, "templates")
UPLOADS = os.path.join(BASE, "uploads")
DB_PATH = os.path.join(BASE, "studyhub.db")

ALLOWED = {"pdf", "doc", "docx", "ppt", "pptx", "txt"}

app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR
)

app.secret_key = os.environ.get("SECRET_KEY", "study-hub-demo-key")

app.config["UPLOAD_FOLDER"] = UPLOADS
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(TEMPLATE_DIR, exist_ok=True)


# ---------------- DATABASE ----------------

def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize():
    with connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL UNIQUE,
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            )
        """)


# ---------------- HOME PAGE ----------------

@app.route("/", methods=["GET"])
def home():
    search = request.args.get("q", "").strip()
    subject_filter = request.args.get("subject", "").strip()

    sql = "SELECT * FROM materials WHERE 1=1"
    parameters = []

    if search:
        sql += """
            AND (
                title LIKE ?
                OR subject LIKE ?
                OR description LIKE ?
                OR uploaded_by LIKE ?
            )
        """
        term = f"%{search}%"
        parameters.extend([term, term, term, term])

    if subject_filter:
        sql += " AND subject = ?"
        parameters.append(subject_filter)

    sql += " ORDER BY id DESC"

    with connect() as connection:
        materials = connection.execute(
            sql, parameters
        ).fetchall()

        subjects = [
            row["subject"]
            for row in connection.execute(
                "SELECT DISTINCT subject FROM materials ORDER BY subject"
            ).fetchall()
        ]

        count = connection.execute(
            "SELECT COUNT(*) FROM materials"
        ).fetchone()[0]

    # Verify that the template is available
    if not os.path.isfile(os.path.join(TEMPLATE_DIR, "index.html")):
        return (
            "Study Hub error: templates/index.html is missing from the deployed project.",
            500
        )

    return render_template(
        "index.html",
        materials=materials,
        subjects=subjects,
        count=count,
        q=search,
        selected_subject=subject_filter
    )


# ---------------- UPLOAD ----------------

@app.route("/upload", methods=["POST"])
def upload():
    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    author = request.form.get("uploaded_by", "").strip()
    description = request.form.get("description", "").strip()
    file = request.files.get("file")

    if not title or not subject or not author or not file or not file.filename:
        flash("Please complete all required fields.", "error")
        return redirect(url_for("home") + "#upload")

    extension = file.filename.rsplit(".", 1)[-1].lower()

    if "." not in file.filename or extension not in ALLOWED:
        flash("Only PDF, DOC, DOCX, PPT, PPTX and TXT files are allowed.", "error")
        return redirect(url_for("home") + "#upload")

    original_name = secure_filename(file.filename)

    if not original_name:
        flash("Invalid file name.", "error")
        return redirect(url_for("home") + "#upload")

    stored_name = f"{uuid.uuid4().hex}.{extension}"
    file_path = os.path.join(UPLOADS, stored_name)

    try:
        file.save(file_path)

        with connect() as connection:
            connection.execute("""
                INSERT INTO materials (
                    title, subject, description,
                    original_name, stored_name,
                    uploaded_by, uploaded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                subject,
                description,
                original_name,
                stored_name,
                author,
                datetime.now().strftime("%d %b %Y")
            ))

        flash("Your material has been uploaded to Study Hub!", "success")

    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)

        flash("Upload failed. Please try again.", "error")

    return redirect(url_for("home") + "#library")


# ---------------- DOWNLOAD ----------------

@app.route("/download/<int:item_id>", methods=["GET"])
def download(item_id):
    with connect() as connection:
        item = connection.execute(
            "SELECT * FROM materials WHERE id = ?",
            (item_id,)
        ).fetchone()

    if item is None:
        abort(404)

    file_path = os.path.join(UPLOADS, item["stored_name"])

    if not os.path.isfile(file_path):
        return "The uploaded file is no longer available.", 404

    return send_from_directory(
        UPLOADS,
        item["stored_name"],
        as_attachment=True,
        download_name=item["original_name"]
    )


# ---------------- ERROR HANDLERS ----------------

@app.errorhandler(404)
def page_not_found(error):
    return "Page not found.", 404


@app.errorhandler(413)
def file_too_large(error):
    return "File too large. Maximum upload size is 20 MB.", 413


@app.errorhandler(500)
def internal_error(error):
    return "An internal error occurred. Please try again.", 500


# ---------------- STARTUP ----------------

initialize()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
