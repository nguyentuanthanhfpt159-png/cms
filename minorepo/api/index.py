import os
import psycopg2
from flask import Flask, jsonify, send_file

app = Flask(__name__)
DB_URL = os.getenv("SUPABASE_URL")

@app.route('/')
def home():
    html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'index.html'))
    if os.path.exists(html_path):
        return send_file(html_path)
    return "<h1>Dashboard is Running</h1>"

@app.route('/api/images')
def images():
    return jsonify([])

@app.route('/api/stats')
def stats():
    data = {
        "total": 150, "ok": 138, "ng": 12,
        "status": "RUNNING", "plc_connected": True, "cam_connected": True,
        "current_model": 1, "last_sync": "--:--:--", "recent_logs": [],
        "error_types": {"Dị vật": 3, "Vỡ": 5, "Thiếu viên": 2},
        "hourly_data": [12, 18, 25, 30, 42, 38, 50, 45],
        "hourly_labels": ['1h','2h','3h','4h','5h','6h','7h','8h']
    }
    if DB_URL:
        try:
            conn = psycopg2.connect(DB_URL, connect_timeout=3)
            cur = conn.cursor()
            cur.execute("SELECT plc_online, machine_running, cam_online, current_model_id, last_update FROM system_status WHERE id = 1")
            row = cur.fetchone()
            if row:
                data["plc_connected"], running, data["cam_connected"], data["current_model"], dt = row
                data["status"] = "RUNNING" if running else "STOPPED"
                if dt: data["last_sync"] = dt.strftime('%H:%M:%S')
            cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_ng = false), COUNT(*) FILTER (WHERE is_ng = true) FROM inspections")
            res = cur.fetchone()
            if res and res[0] is not None:
                data["total"], data["ok"], data["ng"] = res
            cur.close()
            conn.close()
        except Exception:
            pass
    return jsonify(data)

def handler(environ, start_response):
    return app(environ, start_response)
