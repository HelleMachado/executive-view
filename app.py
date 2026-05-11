import json, os, sqlite3
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
KEYS = ["cc4_dados","cc4_importacoes","cc4_pagamentos","cc4_unidades","cc4_operadoras"]

def using_postgres():
    return bool(DATABASE_URL) and DATABASE_URL.startswith(("postgres://","postgresql://")) and psycopg2 is not None

def pg_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    if using_postgres():
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS app_state (id INTEGER PRIMARY KEY, data JSONB NOT NULL, version INTEGER NOT NULL DEFAULT 1, updated_at TIMESTAMP NOT NULL DEFAULT NOW());")
                cur.execute("CREATE TABLE IF NOT EXISTS sync_logs (id SERIAL PRIMARY KEY, event VARCHAR(80), ip VARCHAR(120), created_at TIMESTAMP DEFAULT NOW());")
                cur.execute("SELECT id FROM app_state WHERE id=1;")
                if cur.fetchone() is None:
                    cur.execute("INSERT INTO app_state (id,data,version,updated_at) VALUES (1,%s,1,NOW());",(json.dumps({k:"[]" for k in KEYS},ensure_ascii=False),))
            conn.commit()
    else:
        conn=sqlite3.connect(SQLITE_PATH)
        conn.execute("CREATE TABLE IF NOT EXISTS app_state (id INTEGER PRIMARY KEY CHECK (id=1), data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL)")
        row=conn.execute("SELECT id FROM app_state WHERE id=1").fetchone()
        if row is None:
            conn.execute("INSERT INTO app_state (id,data,version,updated_at) VALUES (1,?,1,?)",(json.dumps({k:"[]" for k in KEYS},ensure_ascii=False),datetime.utcnow().isoformat()))
        conn.commit(); conn.close()

def get_state():
    init_db()
    if using_postgres():
        with pg_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT data,version,updated_at FROM app_state WHERE id=1;")
                r=cur.fetchone()
                d=r["data"] if not isinstance(r["data"],str) else json.loads(r["data"])
                return {"data":d,"version":r["version"],"updated_at":str(r["updated_at"])}
    conn=sqlite3.connect(SQLITE_PATH); conn.row_factory=sqlite3.Row
    r=conn.execute("SELECT data,version,updated_at FROM app_state WHERE id=1").fetchone(); conn.close()
    return {"data":json.loads(r["data"]),"version":r["version"],"updated_at":r["updated_at"]}

def save_state(data, ip):
    init_db()
    clean={k:(data.get(k,"[]") if isinstance(data.get(k,"[]"),str) else json.dumps(data.get(k,"[]"),ensure_ascii=False)) for k in KEYS}
    if using_postgres():
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version FROM app_state WHERE id=1;")
                v=(cur.fetchone()[0])+1
                cur.execute("UPDATE app_state SET data=%s, version=%s, updated_at=NOW() WHERE id=1;",(json.dumps(clean,ensure_ascii=False),v))
                cur.execute("INSERT INTO sync_logs (event,ip) VALUES (%s,%s);",("state_saved",ip))
            conn.commit()
        return v
    conn=sqlite3.connect(SQLITE_PATH); conn.row_factory=sqlite3.Row
    v=conn.execute("SELECT version FROM app_state WHERE id=1").fetchone()["version"]+1
    conn.execute("UPDATE app_state SET data=?, version=?, updated_at=? WHERE id=1",(json.dumps(clean,ensure_ascii=False),v,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return v

@app.route("/")
def home(): return send_from_directory(app.static_folder,"index.html")
@app.route("/executive_view_operacional")
def dash(): return send_from_directory(app.static_folder,"executive_view_operacional.html")
@app.route("/executive_view_operacional.html")
def dash_html(): return send_from_directory(app.static_folder,"executive_view_operacional.html")
@app.route("/api/state",methods=["GET"])
def api_get(): return jsonify({"ok":True,**get_state()})
@app.route("/api/state",methods=["POST"])
def api_post():
    payload=request.get_json(force=True,silent=True) or {}
    v=save_state(payload.get("data") or {}, request.remote_addr)
    return jsonify({"ok":True,"version":v})
@app.route("/api/health")
def health(): return jsonify({"ok":True,"database":"postgres" if using_postgres() else "sqlite-fallback","has_database_url":bool(DATABASE_URL),"psycopg2_available":psycopg2 is not None})
if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
