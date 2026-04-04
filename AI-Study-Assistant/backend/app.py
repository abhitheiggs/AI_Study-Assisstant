import os
import re
import sys
import traceback
import uuid
from pathlib import Path
from typing import Optional

from flask import (
    Flask,
    jsonify,
    redirect,
    Response,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Allow running `python backend/app.py` from project root too.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ai_utils import (  # noqa: E402
    extract_text_from_pdf,
    normalize_text,
    options_to_json,
)
from db import execute, init_db, query_all, query_one  # noqa: E402
from ai_service import generate_flashcards, generate_quiz, generate_summary  # noqa: E402
from chatbot import answer_question  # noqa: E402

ALLOWED_EXTENSIONS = {"pdf", "txt"}


app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "templates"),
    static_folder=str(PROJECT_ROOT / "static"),
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")
# Max upload size: 16 MB (change if needed)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def is_valid_email(email: str) -> bool:
    # Simple email validation (good enough for minor projects)
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def wants_json() -> bool:
    best = request.accept_mimetypes.best or ""
    return "application/json" in best or request.path in ("/summarize", "/flashcards", "/quiz")


def error_response(message: str, status: int = 400):
    if wants_json():
        return jsonify({"error": message}), status
    return redirect(url_for("dashboard", error=message))


def require_auth_api():
    user = current_user()
    if not user:
        return jsonify({"error": "Login required."}), 401
    return None


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return query_one("SELECT id, name, email FROM users WHERE id = ?", (uid,))


def login_required():
    user = current_user()
    if user is None:
        return redirect(url_for("login"))
    return None


def _get_note_for_user(user_id: int, note_id: Optional[int]):
    if note_id:
        note = query_one(
            "SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id)
        )
        return note
    return query_one(
        "SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
    )


@app.before_request
def _ensure_db():
    # Safe to call repeatedly; tables are created once.
    init_db()

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_e):
    return error_response("File too large. Please upload a file under 16 MB.", 413)


@app.get("/")
def home():
    user = current_user()
    if user:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.get("/login")
def login():
    return render_template("login.html")


@app.post("/login")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not email or not password:
        return render_template("login.html", error="Email and password are required.")
    if not is_valid_email(email):
        return render_template("login.html", error="Please enter a valid email.")

    user = query_one("SELECT * FROM users WHERE email = ?", (email,))
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.")

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("dashboard"))


@app.get("/register")
def register():
    return render_template("register.html")


@app.post("/register")
def register_post():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    if not name or not email or not password:
        return render_template("register.html", error="All fields are required.")
    if len(name) < 2 or len(name) > 50:
        return render_template("register.html", error="Name must be 2 to 50 characters.")
    if not is_valid_email(email):
        return render_template("register.html", error="Please enter a valid email.")
    if len(password) < 6:
        return render_template("register.html", error="Password must be at least 6 characters.")

    existing = query_one("SELECT id FROM users WHERE email = ?", (email,))
    if existing:
        return render_template("register.html", error="Email already registered.")

    execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    return redirect(url_for("login"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/dashboard")
def dashboard():
    guard = login_required()
    if guard:
        return guard
    user = current_user()
    notes = query_all(
        "SELECT id, filename, created_at FROM notes WHERE user_id = ? ORDER BY id DESC",
        (user["id"],),
    )
    selected_note_id = request.args.get("note_id", type=int)
    error = request.args.get("error")
    success = request.args.get("success")
    return render_template(
        "dashboard.html",
        user_name=user["name"],
        notes=notes,
        selected_note_id=selected_note_id,
        error=error,
        success=success,
    )


@app.post("/upload")
def upload():
    guard = login_required()
    if guard:
        return guard
    user = current_user()

    if "file" not in request.files:
        return redirect(url_for("dashboard", error="No file part in request."))
    file = request.files["file"]
    if not file or file.filename == "":
        return redirect(url_for("dashboard", error="No file selected."))
    if not allowed_file(file.filename):
        return redirect(url_for("dashboard", error="Only PDF and TXT are supported."))

    original_name = secure_filename(file.filename)
    ext = original_name.rsplit(".", 1)[1].lower()
    # Unique filename to avoid overwriting existing uploads
    filename = f"{uuid.uuid4().hex}_{original_name}"
    save_path = str(UPLOAD_DIR / filename)
    file.save(save_path)

    if ext == "pdf":
        try:
            text = extract_text_from_pdf(save_path)
        except Exception:
            return redirect(url_for("dashboard", error="Could not read the PDF file."))
    else:
        try:
            text = Path(save_path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return redirect(url_for("dashboard", error="Could not read the text file."))

    text = normalize_text(text)
    if len(text) < 50:
        return redirect(
            url_for("dashboard", error="Not enough readable text found in the file.")
        )
    if len(text) > 250_000:
        return redirect(
            url_for(
                "dashboard",
                error="File text is too large. Please upload shorter notes (or split the PDF).",
            )
        )

    note_id = execute(
        "INSERT INTO notes (user_id, filename, original_text) VALUES (?, ?, ?)",
        (user["id"], original_name, text),
    )

# Clear derived data for this note (fresh upload).
    execute("DELETE FROM flashcards WHERE note_id = ?", (note_id,))
    execute("DELETE FROM quiz WHERE note_id = ?", (note_id,))

    # REMOVE THIS ENTIRE BLOCK:
    # RAG indexing (best-effort; upload should still succeed if embeddings fail)
    # try:
    #     store_document_embeddings(text=text, doc_id=note_id, user_id=user["id"])
    # except Exception:
    #     pass

    return redirect(url_for("dashboard", note_id=note_id, success="Upload successful."))


@app.get("/summarize")
def summarize_route():
    auth = require_auth_api()
    if auth:
        return auth
    user = current_user()
    note_id = request.args.get("note_id", type=int)
    if note_id is not None and note_id <= 0:
        return jsonify({"error": "Invalid note_id."}), 400
    note = _get_note_for_user(user["id"], note_id)
    if not note:
        return jsonify({"error": "No note found. Upload a file first."}), 404

    if note["summary"]:
        return jsonify({"note_id": note["id"], "summary": note["summary"]})

    try:
        summary = generate_summary(note["original_text"])
    except Exception:
        return jsonify({"error": "Summary generation failed. Try again."}), 500
    if not summary:
        return jsonify({"error": "Could not generate a summary from this text."}), 422
    execute("UPDATE notes SET summary = ? WHERE id = ?", (summary, note["id"]))
    return jsonify({"note_id": note["id"], "summary": summary})


@app.get("/flashcards")
def flashcards_route():
    auth = require_auth_api()
    if auth:
        return auth
    user = current_user()
    note_id = request.args.get("note_id", type=int)
    if note_id is not None and note_id <= 0:
        return jsonify({"error": "Invalid note_id."}), 400
    note = _get_note_for_user(user["id"], note_id)
    if not note:
        return jsonify({"error": "No note found. Upload a file first."}), 404

    existing = query_all(
        "SELECT question, answer FROM flashcards WHERE note_id = ? ORDER BY id ASC",
        (note["id"],),
    )
    if existing:
        return jsonify(
            {
                "note_id": note["id"],
                # Compatibility: provide both Q/A and Front/Back keys.
                "flashcards": [
                    {
                        "question": r["question"],
                        "answer": r["answer"],
                        "front": r["question"],
                        "back": r["answer"],
                    }
                    for r in existing
                ],
            }
        )

    try:
        cards = generate_flashcards(note["original_text"], limit=10)
    except Exception:
        return jsonify({"error": "Flashcard generation failed. Try again."}), 500
    if not cards:
        return jsonify({"error": "Could not generate flashcards from this text."}), 422
    for c in cards:
        execute(
            "INSERT INTO flashcards (note_id, question, answer) VALUES (?, ?, ?)",
            (note["id"], c["question"], c["answer"]),
        )
    # Compatibility: include front/back aliases
    cards_out = [
        {"question": c["question"], "answer": c["answer"], "front": c["question"], "back": c["answer"]}
        for c in cards
    ]
    return jsonify({"note_id": note["id"], "flashcards": cards_out})


@app.get("/flashcards/export")
def flashcards_export():
    """
    Export Anki-importable TSV: Front<TAB>Back per line.
    Anki import: File -> Import -> select .tsv (Type: Basic).
    """
    auth = require_auth_api()
    if auth:
        return auth
    user = current_user()
    note_id = request.args.get("note_id", type=int)
    if note_id is not None and note_id <= 0:
        return jsonify({"error": "Invalid note_id."}), 400
    note = _get_note_for_user(user["id"], note_id)
    if not note:
        return jsonify({"error": "No note found. Upload a file first."}), 404

    existing = query_all(
        "SELECT question, answer FROM flashcards WHERE note_id = ? ORDER BY id ASC",
        (note["id"],),
    )
    if not existing:
        try:
            cards = generate_flashcards(note["original_text"], limit=10)
        except Exception:
            return jsonify({"error": "Flashcard generation failed. Try again."}), 500
        if not cards:
            return jsonify({"error": "Could not generate flashcards from this text."}), 422
        for c in cards:
            execute(
                "INSERT INTO flashcards (note_id, question, answer) VALUES (?, ?, ?)",
                (note["id"], c["question"], c["answer"]),
            )
        existing = query_all(
            "SELECT question, answer FROM flashcards WHERE note_id = ? ORDER BY id ASC",
            (note["id"],),
        )

    def _clean_field(s: str) -> str:
        # TSV-safe (avoid breaking columns/rows)
        return (s or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()

    lines = [f"{_clean_field(r['question'])}\t{_clean_field(r['answer'])}" for r in existing]
    tsv = "\n".join(lines) + "\n"
    filename = f"anki_flashcards_note_{note['id']}.tsv"
    return Response(
        tsv,
        mimetype="text/tab-separated-values; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/quiz")
def quiz_route():
    auth = require_auth_api()
    if auth:
        return auth
    user = current_user()
    note_id = request.args.get("note_id", type=int)
    if note_id is not None and note_id <= 0:
        return jsonify({"error": "Invalid note_id."}), 400
    note = _get_note_for_user(user["id"], note_id)
    if not note:
        return jsonify({"error": "No note found. Upload a file first."}), 404

    existing = query_all(
        "SELECT question, options_json, correct_index, answer_text, explanation FROM quiz WHERE note_id = ? ORDER BY id ASC",
        (note["id"],),
    )
    if existing:
        quiz_items = []
        for r in existing:
            import json

            opts = json.loads(r["options_json"])
            answer_text = r["answer_text"] or (opts[r["correct_index"]] if opts else "")
            quiz_items.append(
                {
                    "question": r["question"],
                    "options": opts,
                    "correct_index": r["correct_index"],
                    "answer": answer_text,
                    "explanation": r["explanation"] or "",
                }
            )
        return jsonify({"note_id": note["id"], "quiz": quiz_items})

    try:
        items = generate_quiz(note["original_text"], limit=5)
    except Exception:
        return jsonify({"error": "Quiz generation failed. Try again."}), 500
    if not items:
        return jsonify({"error": "Could not generate a quiz from this text."}), 422
    for it in items:
        options = it.get("options") or []
        answer_text = (it.get("answer") or "").strip()
        explanation = (it.get("explanation") or "").strip()
        try:
            correct_index = options.index(answer_text)
        except Exception:
            correct_index = 0
        execute(
            "INSERT INTO quiz (note_id, question, options_json, correct_index, answer_text, explanation) VALUES (?, ?, ?, ?, ?, ?)",
            (
                note["id"],
                it["question"],
                options_to_json(options),
                correct_index,
                answer_text,
                explanation,
            ),
        )
    # Compatibility: keep correct_index; also return answer + explanation
    items_out = []
    for it in items:
        options = it.get("options") or []
        answer_text = (it.get("answer") or "").strip()
        try:
            correct_index = options.index(answer_text)
        except Exception:
            correct_index = 0
        items_out.append(
            {
                "question": it.get("question", ""),
                "options": options,
                "correct_index": correct_index,
                "answer": answer_text,
                "explanation": (it.get("explanation") or "").strip(),
            }
        )
    return jsonify({"note_id": note["id"], "quiz": items_out})


@app.post("/chat")
def chat_route():
    """
    JSON API (no UI changes required).
    Body: {"question": "...", "note_id": 123 (optional)}
    Response: {"answer": "...", "note_id": 123}
    """
    auth = require_auth_api()
    if auth:
        return auth
    user = current_user()
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    note_id = payload.get("note_id")

    if not question:
        return jsonify({"error": "Question is required."}), 400
    if note_id is not None:
        try:
            note_id = int(note_id)
        except Exception:
            return jsonify({"error": "note_id must be an integer."}), 400

    # Ensure note belongs to user if note_id is provided
    note = _get_note_for_user(user["id"], note_id if note_id else None)
    if not note:
        return jsonify({"error": "No note found. Upload a file first."}), 404

    try:
        ans = answer_question(question=question, note_text=note["original_text"])
    except Exception as e:
        # Print traceback to server terminal for easier debugging in development.
        traceback.print_exc()
        return jsonify({"error": f"Chat failed. {str(e) or 'Check API key and try again.'}"}), 500

    if not ans:
        return jsonify({"error": "No answer generated."}), 422
    return jsonify({"answer": ans, "note_id": note["id"]})


if __name__ == "__main__":
    # For college projects: simple dev server.
    app.run(debug=True, host="127.0.0.1", port=5000)

