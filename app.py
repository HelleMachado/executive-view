import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "executive_view_central.db"))

app = Flask(__name__, static_folder="static")

DEFAULT_STATE_KEYS = [
    "cc4_dados",
    "cc4_importacoes",
    "cc4_pagamentos",
    "cc4_unidades",
    "cc4_operadoras",
]

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            ip TEXT,
            created_at TEXT NOT NULL
        )
    """)
    row = conn.execute("SELECT id FROM app_state WHERE id = 1").fetchone()
    if row is None:
        initial_data = {k: "[]" for k in DEFAULT_STATE_KEYS}
        conn.execute(
            "INSERT INTO app_state (id, data, version, updated_at) VALUES (1, ?, 1, ?)",
            (json.dumps(initial_data, ensure_ascii=False), datetime.utcnow().isoformat())
        )
    conn.commit()
    conn.close()

def get_state_row():
    init_db()
    conn = connect()
    row = conn.execute("SELECT data, version, updated_at FROM app_state WHERE id = 1").fetchone()
    conn.close()
    return row

@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/executive_view_operacional")
def dashboard():
    return send_from_directory(app.static_folder, "executive_view_operacional.html")

@app.route("/executive_view_operacional.html")
def dashboard_html():
    return send_from_directory(app.static_folder, "executive_view_operacional.html")

@app.route("/api/state", methods=["GET"])
def api_get_state():
    row = get_state_row()
    try:
        data = json.loads(row["data"])
    except Exception:
        data = {k: "[]" for k in DEFAULT_STATE_KEYS}
    return jsonify({"ok": True, "data": data, "version": row["version"], "updated_at": row["updated_at"]})

@app.route("/api/state", methods=["POST"])
def api_save_state():
    payload = request.get_json(force=True, silent=True) or {}
    incoming = payload.get("data") or {}
    cleaned = {}
    for k in DEFAULT_STATE_KEYS:
        value = incoming.get(k, "[]")
        cleaned[k] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    conn = connect()
    current = conn.execute("SELECT version FROM app_state WHERE id = 1").fetchone()
    version = (current["version"] if current else 0) + 1
    now = datetime.utcnow().isoformat()
    conn.execute("UPDATE app_state SET data = ?, version = ?, updated_at = ? WHERE id = 1",
                 (json.dumps(cleaned, ensure_ascii=False), version, now))
    conn.execute("INSERT INTO sync_logs (event, ip, created_at) VALUES (?, ?, ?)",
                 ("state_saved", request.remote_addr, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "version": version, "updated_at": now})

@app.route("/api/sync-logs", methods=["GET"])
def sync_logs():
    init_db()
    conn = connect()
    rows = [dict(r) for r in conn.execute("SELECT * FROM sync_logs ORDER BY id DESC LIMIT 100").fetchall()]
    conn.close()
    return jsonify(rows)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
