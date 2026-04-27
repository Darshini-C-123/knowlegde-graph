"""
Knowledge Graph Builder Swarm — Flask application.

Endpoints:
  /api/process      POST   Process text through multi-agent pipeline
  /api/upload       POST   Upload .txt/.docx file
  /api/last         GET    Last run result
  /api/qa           POST   Ask a question on the built graph
  /api/runs         GET    Run history list (for replay)
  /api/run/<id>     GET    Single run details (replay)
  /api/growth       GET    Graph growth metrics across runs
  /api/reset        POST   Clear current session data
  /api/seed         GET    Return available seed texts
"""
from __future__ import annotations

import os
import sqlite3
from functools import wraps

from docx import Document
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, will use system environment

import pipeline
import qa_engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "kg-swarm-dev-key-change-in-production")

# Per-user last run (graph, metrics, logs) for graph/logs pages
_user_store: dict[str, dict] = {}

# Seed text presets
SEED_TEXTS = {
    "tech_companies": (
        "Elon Musk founded SpaceX in 2002 and Tesla in 2003. SpaceX is headquartered in "
        "Hawthorne, California. Tesla is located in Austin, Texas. Musk also acquired Twitter "
        "in 2022. Satya Nadella is the CEO of Microsoft, which is headquartered in Redmond, "
        "Washington. Microsoft acquired GitHub in 2018 and LinkedIn in 2016."
    ),
    "world_capitals": (
        "Paris is the capital of France. Berlin is the capital of Germany. Tokyo is the capital "
        "of Japan. London is the capital of the United Kingdom. Washington D.C. is the capital "
        "of the United States. New Delhi is the capital of India. Canberra is the capital of Australia."
    ),
    "movie_industry": (
        "Christopher Nolan directed Inception and The Dark Knight. Leonardo DiCaprio starred in "
        "Inception and Titanic. Titanic was directed by James Cameron. The Dark Knight featured "
        "Heath Ledger as the Joker. Cameron also directed Avatar. Steven Spielberg directed "
        "Jurassic Park and Schindler's List."
    ),
    "legal_clause": (
        "The Licensor grants the Licensee a non-exclusive, non-transferable license to use the "
        "Software. The agreement is governed by the laws of the State of Delaware. Any dispute "
        "arising from this contract shall be resolved through arbitration in New York City. "
        "The Licensee shall not reverse-engineer, decompile, or disassemble the Software. "
        "Confidential information shared between Company A and Company B remains protected "
        "for five years after termination."
    ),
}


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            # Check if this is an API endpoint (starts with /api/)
            if request.path and request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Authentication required. Please login first."}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    err = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not username or not password:
            err = "Username and password are required."
        else:
            conn = get_db()
            row = conn.execute(
                "SELECT id, username, password FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            conn.close()
            if row and check_password_hash(row["password"], password):
                session["user"] = row["username"]
                return redirect(url_for("dashboard"))
            err = "Invalid username or password."
    return render_template("login.html", error=err)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    err = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if len(username) < 2:
            err = "Username must be at least 2 characters."
        elif len(password) < 4:
            err = "Password must be at least 4 characters."
        else:
            h = generate_password_hash(password)
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (username, h),
                )
                conn.commit()
                conn.close()
                session["user"] = username
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                conn.close()
                err = "Username already exists."
    return render_template("signup.html", error=err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", username=session["user"])


@app.route("/graph")
@login_required
def graph_page():
    return render_template("graph.html", username=session["user"])


@app.route("/logs")
@login_required
def logs_page():
    return render_template("logs.html", username=session["user"])


def _store_for_user() -> dict:
    u = session["user"]
    if u not in _user_store:
        _user_store[u] = {
            "with_agents": None,
            "without_agents": None,
            "logs": [],
            "messages": [],
            "transitions": [],
            "agent_timeline": [],
            "run_id": None,
            "last_summary": "",
        }
    return _user_store[u]


@app.route("/api/process", methods=["POST"])
@login_required
def api_process():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "No text provided."}), 400

    try:
        result = pipeline.run(text)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    n_nodes = len(result.get("graph", {}).get("nodes", []))
    n_edges = len(result.get("graph", {}).get("edges", []))
    summary = f"Processed knowledge graph with {n_nodes} nodes and {n_edges} edges."

    st = _store_for_user()
    st["last_result"] = result
    st["logs"] = result.get("logs") or []
    st["messages"] = result.get("messages") or []
    st["transitions"] = result.get("transitions") or []
    st["agent_timeline"] = result.get("agent_timeline") or []
    st["run_id"] = result.get("run_id")
    st["last_summary"] = summary
    st["last_text"] = text  # Store original text for Gemini QA context

    return jsonify(
        {
            "ok": True,
            "run_id": result.get("run_id"),
            "summary": summary,
            "graph": result.get("graph", {}),
            "metrics": result.get("metrics", {}),
            "messages": result.get("messages") or [],
            "transitions": result.get("transitions") or [],
            "agent_timeline": result.get("agent_timeline") or [],
            "logs": result.get("logs") or [],
        }
    )


@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No file uploaded."}), 400

    name = f.filename.lower()
    raw = f.read()

    try:
        if name.endswith(".txt"):
            text = raw.decode("utf-8", errors="replace")
        elif name.endswith(".docx"):
            path = os.path.join(BASE_DIR, "_upload_tmp.docx")
            with open(path, "wb") as out:
                out.write(raw)
            doc = Document(path)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            try:
                os.remove(path)
            except OSError:
                pass
        else:
            return jsonify({"ok": False, "error": "Only .txt and .docx are supported."}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    text = (text or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "File is empty."}), 400

    try:
        result = pipeline.run(text)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    n_nodes = len(result.get("graph", {}).get("nodes", []))
    n_edges = len(result.get("graph", {}).get("edges", []))
    summary = f"Processed knowledge graph with {n_nodes} nodes and {n_edges} edges."

    st = _store_for_user()
    st["last_result"] = result
    st["logs"] = result.get("logs") or []
    st["messages"] = result.get("messages") or []
    st["transitions"] = result.get("transitions") or []
    st["agent_timeline"] = result.get("agent_timeline") or []
    st["run_id"] = result.get("run_id")
    st["last_summary"] = summary
    st["last_text"] = text  # Store original text for Gemini QA context

    return jsonify(
        {
            "ok": True,
            "run_id": result.get("run_id"),
            "text": text,
            "summary": summary,
            "graph": result.get("graph", {}),
            "metrics": result.get("metrics", {}),
            "messages": result.get("messages") or [],
            "transitions": result.get("transitions") or [],
            "agent_timeline": result.get("agent_timeline") or [],
            "logs": result.get("logs") or [],
        }
    )


@app.route("/api/last", methods=["GET"])
@login_required
def api_last():
    st = _store_for_user()
    result = st.get("last_result", {})
    return jsonify(
        {
            "ok": True,
            "run_id": st.get("run_id"),
            "graph": result.get("graph", {}),
            "metrics": result.get("metrics", {}),
            "logs": st.get("logs") or [],
            "messages": st.get("messages") or [],
            "transitions": st.get("transitions") or [],
            "agent_timeline": st.get("agent_timeline") or [],
            "summary": st.get("last_summary") or "",
        }
    )


@app.route("/api/qa", methods=["POST"])
@login_required
def api_qa():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()

    st = _store_for_user()
    result = st.get("last_result", {})
    if not result or not result.get("graph"):
        return jsonify({"ok": False, "error": "No graph available yet. Run the pipeline first."}), 400

    graph = result["graph"]
    # Get original text for Gemini context (stored in user session or pipeline result)
    original_text = result.get("original_text", st.get("last_text", ""))
    
    answer = qa_engine.answer_question(question, graph, original_text)
    return jsonify({"ok": True, "answer": answer})


@app.route("/api/runs", methods=["GET"])
@login_required
def api_runs():
    """Return list of stored runs (for replay)."""
    runs = pipeline.get_run_history()
    summary = []
    for r in runs:
        wm = r.get("with_agents", {}).get("metrics", {})
        summary.append({
            "run_id": r.get("run_id"),
            "timestamp": r.get("timestamp"),
            "node_count": wm.get("node_count", 0),
            "edge_count": wm.get("edge_count", 0),
        })
    return jsonify({"ok": True, "runs": summary})


@app.route("/api/run/<run_id>", methods=["GET"])
@login_required
def api_run_detail(run_id: str):
    """Get full details for one run (replay)."""
    r = pipeline.get_run_by_id(run_id)
    if not r:
        return jsonify({"ok": False, "error": "Run not found."}), 404
    return jsonify({
        "ok": True,
        "run_id": r.get("run_id"),
        "timestamp": r.get("timestamp"),
        "with_agents": r.get("with_agents"),
        "without_agents": r.get("without_agents"),
        "logs": r.get("logs") or [],
        "messages": r.get("messages") or [],
        "transitions": r.get("transitions") or [],
        "agent_timeline": r.get("agent_timeline") or [],
    })


@app.route("/api/growth", methods=["GET"])
@login_required
def api_growth():
    """Graph growth metrics across all runs."""
    return jsonify({"ok": True, "growth": pipeline.get_graph_growth()})


@app.route("/api/reset", methods=["POST"])
@login_required
def api_reset():
    """Clear current user's session data."""
    u = session["user"]
    if u in _user_store:
        _user_store[u] = {
            "with_agents": None,
            "without_agents": None,
            "logs": [],
            "messages": [],
            "transitions": [],
            "agent_timeline": [],
            "run_id": None,
            "last_summary": "",
        }
    return jsonify({"ok": True})


@app.route("/api/seed", methods=["GET"])
@login_required
def api_seed():
    """Return available seed text presets."""
    return jsonify({"ok": True, "seeds": SEED_TEXTS})


init_db()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
