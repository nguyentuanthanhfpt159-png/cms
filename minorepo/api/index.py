from flask import Flask, jsonify, send_file
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

app = Flask(__name__)

# 1. Đường dẫn trang chủ: Mở file index.html
@app.route('/')
def index():
    html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'index.html'))
    if os.path.exists(html_path):
        return send_file(html_path)
    return "<h1>Dashboard is Running</h1>"

# 2. Đường dẫn API lấy số liệu phân loại
@app.route('/api/stats')
def get_stats():
    total, ok, ng = 150, 138, 12
    status = "RUNNING"
    plc_connected = True
    cam_connected = True
    current_model = 1
    last_update = "--:--:--"
    recent_logs = []
    error_types = {"Dị vật": 3, "Vỡ": 5, "Thiếu viên": 2}
    hourly_data = [12, 18, 25, 30, 42, 38, 50, 45]

    if DB_URL:
        try:
            conn = psycopg2.connect(DB_URL, connect_timeout=3)
            cur = conn.cursor()
            
            # Trạng thái hệ thống
            cur.execute("SELECT plc_online, machine_running, cam_online, current_model_id, last_update FROM system_status WHERE id = 1")
            row_st = cur.fetchone()
            if row_st:
                plc_connected, machine_running, cam_online, current_model, last_update_dt = row_st
                status = "RUNNING" if machine_running else "STOPPED"
                if last_update_dt:
                    last_update = last_update_dt.strftime('%H:%M:%S')

            # Thống kê sản lượng
            cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_ng = false), COUNT(*) FILTER (WHERE is_ng = true) FROM inspections")
            total, ok, ng = cur.fetchone()

            # Nhật ký gần nhất
            cur.execute("SELECT id, product_name, result, created_at FROM inspections ORDER BY created_at DESC LIMIT 10")
            rows_logs = cur.fetchall()
            recent_logs = [[str(r[0]), r[1], r[2], r[3].strftime('%H:%M:%S')] for r in rows_logs]

            cur.close()
            conn.close()
        except Exception as e:
            print(f"Supabase offline, using fallback: {e}")

    return jsonify({
        "total": total, "ok": ok, "ng": ng,
        "status": status,
        "plc_connected": plc_connected,
        "cam_connected": cam_connected,
        "current_model": current_model,
        "last_sync": last_update,
        "recent_logs": recent_logs,
        "error_types": error_types,
        "hourly_data": hourly_data,
        "hourly_labels": ['1h','2h','3h','4h','5h','6h','7h','8h']
    })

def handler(environ, start_response):
    return app(environ, start_response)
