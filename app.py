import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SQLITE_PATH = BASE_DIR / "executive_view_central.db"

app = Flask(__name__, static_folder="static")

DEFAULT_STATE_KEYS = ["cc4_dados", "cc4_importacoes", "cc4_pagamentos", "cc4_unidades", "cc4_operadoras"]

def using_postgres():
    return bool(DATABASE_URL) and DATABASE_URL.startswith(("postgres://", "postgresql://")) and psycopg2 is not None

def now_iso():
    return datetime.utcnow().isoformat()

def pg_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_postgres():
    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_state (
                    id INTEGER PRIMARY KEY,
                    data JSONB NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_logs (
                    id SERIAL PRIMARY KEY,
                    event VARCHAR(80) NOT NULL,
                    ip VARCHAR(120),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """)
            cur.execute("SELECT id FROM app_state WHERE id = 1;")
            if cur.fetchone() is None:
                initial = {k: "[]" for k in DEFAULT_STATE_KEYS}
                cur.execute("INSERT INTO app_state (id, data, version, updated_at) VALUES (1, %s, 1, NOW());",
                            (json.dumps(initial, ensure_ascii=False),))
        conn.commit()

def init_sqlite():
    conn = sqlite3.connect(SQLITE_PATH)
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
        initial = {k: "[]" for k in DEFAULT_STATE_KEYS}
        conn.execute("INSERT INTO app_state (id, data, version, updated_at) VALUES (1, ?, 1, ?)",
                     (json.dumps(initial, ensure_ascii=False), now_iso()))
    conn.commit()
    conn.close()

def init_db():
    if using_postgres():
        init_postgres()
    else:
        init_sqlite()

def get_state():
    init_db()
    if using_postgres():
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT data, version, updated_at FROM app_state WHERE id = 1;")
                row = cur.fetchone()
                data = row["data"]
                if isinstance(data, str):
                    data = json.loads(data)
                return {
                    "data": data,
                    "version": row["version"],
                    "updated_at": row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
                }
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT data, version, updated_at FROM app_state WHERE id = 1").fetchone()
    conn.close()
    try:
        data = json.loads(row["data"])
    except Exception:
        data = {k: "[]" for k in DEFAULT_STATE_KEYS}
    return {"data": data, "version": row["version"], "updated_at": row["updated_at"]}

def save_state(incoming):
    init_db()
    cleaned = {}
    for k in DEFAULT_STATE_KEYS:
        value = incoming.get(k, "[]")
        cleaned[k] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    if using_postgres():
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version FROM app_state WHERE id = 1;")
                current = cur.fetchone()
                version = (current[0] if current else 0) + 1
                cur.execute("UPDATE app_state SET data = %s, version = %s, updated_at = NOW() WHERE id = 1;",
                            (json.dumps(cleaned, ensure_ascii=False), version))
                cur.execute("INSERT INTO sync_logs (event, ip, created_at) VALUES (%s, %s, NOW());",
                            ("state_saved", request.remote_addr))
            conn.commit()
        return version, now_iso()

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    current = conn.execute("SELECT version FROM app_state WHERE id = 1").fetchone()
    version = (current["version"] if current else 0) + 1
    now = now_iso()
    conn.execute("UPDATE app_state SET data = ?, version = ?, updated_at = ? WHERE id = 1",
                 (json.dumps(cleaned, ensure_ascii=False), version, now))
    conn.execute("INSERT INTO sync_logs (event, ip, created_at) VALUES (?, ?, ?)",
                 ("state_saved", request.remote_addr, now))
    conn.commit()
    conn.close()
    return version, now

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
    state = get_state()
    return jsonify({"ok": True, **state})

@app.route("/api/state", methods=["POST"])
def api_save_state():
    payload = request.get_json(force=True, silent=True) or {}
    incoming = payload.get("data") or {}
    version, updated_at = save_state(incoming)
    return jsonify({"ok": True, "version": version, "updated_at": updated_at})

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "database": "postgres" if using_postgres() else "sqlite-fallback", "has_database_url": bool(DATABASE_URL)})

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
