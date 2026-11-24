import os, sqlite3, uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from werkzeug.utils import secure_filename

BASE = os.path.abspath(os.path.dirname(__file__))
UPLOADS = os.path.join(BASE, "uploads")
DB_PATH = os.path.join(BASE, "studyhub.db")
ALLOWED = {"pdf", "doc", "docx", "ppt", "pptx", "txt"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "replace-this-before-production")
app.config["UPLOAD_FOLDER"] = UPLOADS
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
os.makedirs(UPLOADS, exist_ok=True)

def connect():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def initialize():
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            subject TEXT NOT NULL, description TEXT, original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE, uploaded_by TEXT NOT NULL,
            uploaded_at TEXT NOT NULL)""")

@app.get("/")
def home():
    q = request.args.get("q", "").strip()
    subject = request.args.get("subject", "").strip()
    sql, args = "SELECT * FROM materials WHERE 1=1", []
    if q:
        sql += " AND (title LIKE ? OR subject LIKE ? OR description LIKE ? OR uploaded_by LIKE ?)"
        term = f"%{q}%"
        args.extend([term, term, term, term])
    if subject:
        sql += " AND subject = ?"
        args.append(subject)
    sql += " ORDER BY id DESC"
    with connect() as c:
        materials = c.execute(sql, args).fetchall()
        subjects = [r["subject"] for r in c.execute("SELECT DISTINCT subject FROM materials ORDER BY subject").fetchall()]
        count = c.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    return render_template("index.html", materials=materials, subjects=subjects, count=count, q=q, selected_subject=subject)

@app.post("/upload")
def upload():
    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    author = request.form.get("uploaded_by", "").strip()
    description = request.form.get("description", "").strip()
    file = request.files.get("file")
    if not title or not subject or not author or not file or not file.filename:
        flash("Please complete the required fields and select a file.", "error")
        return redirect(url_for("home") + "#upload")
    if "." not in file.filename or file.filename.rsplit(".", 1)[1].lower() not in ALLOWED:
        flash("Use PDF, DOC, DOCX, PPT, PPTX or TXT files.", "error")
        return redirect(url_for("home") + "#upload")
    original = secure_filename(file.filename)
    ext = original.rsplit(".", 1)[1].lower()
    stored = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(UPLOADS, stored))
    with connect() as c:
        c.execute("""INSERT INTO materials (title,subject,description,original_name,stored_name,uploaded_by,uploaded_at)
                     VALUES (?,?,?,?,?,?,?)""",
                  (title, subject, description, original, stored, author, datetime.now().strftime("%d %b %Y")))
    flash("Your resource has been added to Study Hub!", "success")
    return redirect(url_for("home") + "#library")

@app.get("/download/<int:item_id>")
def download(item_id):
    with connect() as c:
        item = c.execute("SELECT * FROM materials WHERE id=?", (item_id,)).fetchone()
    if item is None:
        abort(404)
    return send_from_directory(UPLOADS, item["stored_name"], as_attachment=True, download_name=item["original_name"])

@app.errorhandler(413)
def too_large(_):
    flash("File is too large. Maximum size is 20 MB.", "error")
    return redirect(url_for("home") + "#upload")

initialize()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
