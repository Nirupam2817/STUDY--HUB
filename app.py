
import os
import sqlite3
import uuid
import hmac

from flask import (
    Flask, render_template, request, redirect,
    url_for, send_from_directory, abort
)
from werkzeug.utils import secure_filename


# ---------------- CONFIGURATION ----------------

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "uploads")
DB_PATH = os.path.join(BASE, "studyhub.db")

os.makedirs(UPLOADS, exist_ok=True)

ALLOWED = {"pdf", "doc", "docx", "ppt", "pptx", "txt"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "studyhub-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT,
            original_name TEXT NOT NULL,
            stored_name TEXT UNIQUE NOT NULL,
            uploaded_by TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------- HOME / SEARCH ----------------

@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    selected_subject = request.args.get("subject", "").strip()

    conn = get_db()

    query = "SELECT * FROM materials WHERE 1=1"
    params = []

    if q:
        query += """
            AND (
                title LIKE ?
                OR subject LIKE ?
                OR description LIKE ?
                OR original_name LIKE ?
            )
        """
        search = f"%{q}%"
        params.extend([search, search, search, search])

    if selected_subject:
        query += " AND subject = ?"
        params.append(selected_subject)

    query += " ORDER BY uploaded_at DESC"

    materials = conn.execute(query, params).fetchall()

    subjects = conn.execute("""
        SELECT DISTINCT subject
        FROM materials
        ORDER BY subject
    """).fetchall()

    count = conn.execute(
        "SELECT COUNT(*) FROM materials"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        materials=materials,
        subjects=subjects,
        count=count,
        q=q,
        selected_subject=selected_subject
    )


# ---------------- UPLOAD ----------------

@app.route("/upload", methods=["POST"])
def upload():
    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    uploaded_by = request.form.get("uploaded_by", "").strip()
    description = request.form.get("description", "").strip()
    file = request.files.get("file")

    if not title or not subject or not file:
        return "Please fill in the required fields.", 400

    if not file.filename:
        return "Please select a file.", 400

    original_name = secure_filename(file.filename)

    if not original_name or "." not in original_name:
        return "Invalid file name.", 400

    extension = original_name.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED:
        return "File type not allowed.", 400

    stored_name = str(uuid.uuid4()) + "." + extension
    file_path = os.path.join(UPLOADS, stored_name)

    file.save(file_path)

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO materials (
                title, subject, description,
                original_name, stored_name, uploaded_by
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            title,
            subject,
            description,
            original_name,
            stored_name,
            uploaded_by
        ))

        conn.commit()

    except Exception:
        conn.close()

        if os.path.exists(file_path):
            os.remove(file_path)

        return "Upload failed. Please try again.", 500

    conn.close()

    return redirect(url_for("home"))


# ---------------- DOWNLOAD ----------------

@app.route("/download/<int:item_id>")
def download(item_id):
    conn = get_db()

    item = conn.execute(
        "SELECT stored_name, original_name FROM materials WHERE id = ?",
        (item_id,)
    ).fetchone()

    conn.close()

    if item is None:
        abort(404)

    return send_from_directory(
        UPLOADS,
        item["stored_name"],
        as_attachment=True,
        download_name=item["original_name"]
    )


# ---------------- DELETE ----------------

@app.route("/delete/<int:item_id>", methods=["POST"])
def delete_material(item_id):
    password = request.form.get("password", "")
    correct_password = os.environ.get("DELETE_PASSWORD", "")

    if not correct_password:
        return "Delete password is not configured.", 500

    if not hmac.compare_digest(password, correct_password):
        return "Incorrect password. File was not deleted.", 403

    conn = get_db()

    item = conn.execute(
        "SELECT * FROM materials WHERE id = ?",
        (item_id,)
    ).fetchone()

    if item is None:
        conn.close()
        abort(404)

    stored_name = item["stored_name"]

    # Prevent accidental path traversal
    if stored_name != os.path.basename(stored_name):
        conn.close()
        abort(400)

    file_path = os.path.join(UPLOADS, stored_name)

    # Delete the physical file first.
    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError:
            conn.close()
            return "Could not delete the uploaded file.", 500

    # Delete the database record.
    conn.execute(
        "DELETE FROM materials WHERE id = ?",
        (item_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("home"))


# ---------------- ERROR HANDLERS ----------------

@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(413)
def file_too_large(error):
    return "File is too large. Maximum size is 20 MB.", 413


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)
