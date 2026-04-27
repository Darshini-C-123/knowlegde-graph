"""
Vercel Serverless API for Knowledge Graph Builder
Adapted from app.py for serverless deployment
"""
from __future__ import annotations

import os
import sqlite3
import json
from functools import wraps
from urllib.parse import parse_qs

# Load environment variables from Vercel
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import Flask modules for serverless
from flask import Flask, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

# Import our modules
import sys
import subprocess
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Download and load spaCy model for serverless
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # Download spaCy model if not available
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"], check=True)
    import spacy
    nlp = spacy.load("en_core_web_sm")

import pipeline
import qa_engine
import gemini_config

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "kg-swarm-vercel-deployment")

# In-memory storage for serverless environment
_user_store = {}
_run_history = []

# Database setup for serverless
DATABASE = os.path.join(os.path.dirname(__file__), "database.db")

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
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
            return jsonify({"ok": False, "error": "Authentication required. Please login first."}), 401
        return f(*args, **kwargs)
    return decorated

def _store_for_user() -> dict:
    u = session.get("user", "anonymous")
    if u not in _user_store:
        _user_store[u] = {
            "last_result": None,
            "logs": [],
            "messages": [],
            "transitions": [],
            "agent_timeline": [],
            "run_id": None,
            "last_summary": "",
            "last_text": "",
        }
    return _user_store[u]

# Seed texts
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

# API Routes
@app.route("/api/process", methods=["POST"])
@login_required
def api_process():
    data = request.get_json(silent=True) or {}
    
    # Handle both direct text and file upload
    text = (data.get("text") or "").strip()
    
    # If file content is provided (base64 encoded for serverless)
    if not text and data.get("file_content"):
        import base64
        try:
            # Decode base64 content
            file_data = base64.b64decode(data.get("file_content"))
            
            # Check if it's a docx file by magic number or extension
            if data.get("filename", "").lower().endswith(".docx"):
                # Process docx in memory
                from io import BytesIO
                from docx import Document
                doc = Document(BytesIO(file_data))
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            else:
                # Process as text file
                text = file_data.decode("utf-8", errors="replace")
        except Exception as e:
            return jsonify({"ok": False, "error": f"File processing error: {str(e)}"}), 400
    
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
    st["last_text"] = text

    # Store in run history
    _run_history.append(result)
    if len(_run_history) > 50:
        _run_history.pop(0)

    return jsonify({
        "ok": True,
        "run_id": result.get("run_id"),
        "summary": summary,
        "graph": result.get("graph", {}),
        "metrics": result.get("metrics", {}),
        "messages": result.get("messages") or [],
        "transitions": result.get("transitions") or [],
        "agent_timeline": result.get("agent_timeline") or [],
        "logs": result.get("logs") or [],
    })

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
    original_text = result.get("original_text", st.get("last_text", ""))
    
    answer = qa_engine.answer_question(question, graph, original_text)
    return jsonify({"ok": True, "answer": answer})

@app.route("/api/seed", methods=["GET"])
@login_required
def api_seed():
    return jsonify({"ok": True, "seeds": SEED_TEXTS})

@app.route("/api/last", methods=["GET"])
@login_required
def api_last():
    st = _store_for_user()
    result = st.get("last_result", {})
    return jsonify({
        "ok": True,
        "run_id": st.get("run_id"),
        "graph": result.get("graph", {}),
        "metrics": result.get("metrics", {}),
        "logs": st.get("logs") or [],
        "messages": st.get("messages") or [],
        "transitions": st.get("transitions") or [],
        "agent_timeline": st.get("agent_timeline") or [],
        "summary": st.get("last_summary") or "",
    })

@app.route("/api/reset", methods=["POST"])
@login_required
def api_reset():
    u = session.get("user", "anonymous")
    if u in _user_store:
        _user_store[u] = {
            "last_result": None,
            "logs": [],
            "messages": [],
            "transitions": [],
            "agent_timeline": [],
            "run_id": None,
            "last_summary": "",
            "last_text": "",
        }
    return jsonify({"ok": True})

# Simple login for demo (in production, use proper auth)
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "demo").strip()
    password = data.get("password", "demo").strip()
    
    # Simple demo authentication
    if username and password:
        session["user"] = username
        return jsonify({"ok": True, "username": username})
    
    return jsonify({"ok": False, "error": "Invalid credentials"}), 401

@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "ok": True,
        "status": "running",
        "gemini_available": gemini_config.gemini_config.is_available(),
        "version": "1.0.0"
    })

# Health check endpoint
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"})

# Initialize database
init_db()

# Vercel serverless handler
def handler(request):
    return app(request.environ, lambda status, headers: None)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
