
import os
import sqlite3
import hmac
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "studyhub-secret-key")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DATABASE = os.path.join(BASE_DIR, "studyhub.db")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB per upload

ALLOWED_EXTENSIONS = {"pdf"}


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT,
            original_name TEXT NOT NULL,
            filename TEXT NOT NULL,
            uploaded_by TEXT,
            uploaded_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_db()


@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    selected_subject = request.args.get("subject", "").strip()

    conn = get_db()

    # Get all subjects for the filter
    subjects = [
        row["subject"]
        for row in conn.execute(
            "SELECT DISTINCT subject FROM materials ORDER BY subject"
        ).fetchall()
    ]

    # Build search conditions
    conditions = []
    params = []

    if q:
        conditions.append("""
            (
                title LIKE ?
                OR subject LIKE ?
                OR description LIKE ?
                OR original_name LIKE ?
            )
        """)
        search_term = f"%{q}%"
        params.extend([search_term] * 4)

    if selected_subject:
        conditions.append("subject = ?")
        params.append(selected_subject)

    sql = "SELECT * FROM materials"

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY id DESC"

    materials = conn.execute(sql, params).fetchall()

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


@app.route("/upload", methods=["POST"])
def upload():
    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    uploaded_by = request.form.get("uploaded_by", "").strip()
    description = request.form.get("description", "").strip()
    file = request.files.get("file")

    if not title or not subject or not file or not file.filename:
        flash("Please fill in the required fields and select a PDF.")
        return redirect(url_for("home"))

    if not allowed_file(file.filename):
        flash("Only PDF files are allowed.")
        return redirect(url_for("home"))

    original_name = secure_filename(file.filename)

    # Unique filename to avoid overwriting existing uploads
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original_name}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    file.save(filepath)

    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO materials
            (title, subject, description, original_name,
             filename, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            title,
            subject,
            description,
            original_name,
            filename,
            uploaded_by,
            datetime.now().strftime("%d-%m-%Y %H:%M")
        ))

        conn.commit()
        conn.close()

        flash("Study material uploaded successfully!")

    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        flash(f"Upload failed: {e}")

    return redirect(url_for("home"))


@app.route("/download/<int:item_id>")
def download(item_id):
    conn = get_db()
    material = conn.execute(
        "SELECT filename, original_name FROM materials WHERE id = ?",
        (item_id,)
    ).fetchone()
    conn.close()

    if material is None:
        return "File not found", 404

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        material["filename"],
        as_attachment=True,
        download_name=material["original_name"]
    )


@app.route("/delete/<int:item_id>", methods=["POST"])
def delete_material(item_id):
    password = request.form.get("password", "")
    delete_password = os.environ.get("DELETE_PASSWORD", "")

    if not delete_password:
        flash("Delete password has not been configured.")
        return redirect(url_for("home"))

    if not hmac.compare_digest(password, delete_password):
        flash("Incorrect delete password.")
        return redirect(url_for("home"))

    conn = get_db()

    material = conn.execute(
        "SELECT filename FROM materials WHERE id = ?",
        (item_id,)
    ).fetchone()

    if material is None:
        conn.close()
        flash("Material not found.")
        return redirect(url_for("home"))

    filepath = os.path.join(UPLOAD_FOLDER, material["filename"])

    conn.execute("DELETE FROM materials WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

    if os.path.exists(filepath):
        os.remove(filepath)

    flash("Material deleted successfully.")
    return redirect(url_for("home"))


@app.errorhandler(413)
def too_large(e):
    flash("The PDF is too large. Maximum upload size is 25 MB.")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
