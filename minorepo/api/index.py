from flask import Flask, jsonify
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

app = Flask(__name__)

@app.route('/api/stats')
def get_stats():
    if not DB_URL:
        return jsonify({"status": "error", "message": "Chưa cấu hình SUPABASE_URL"})

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        # 1. Trạng thái hệ thống
        cur.execute("SELECT plc_online, machine_running, cam_online, current_model_id, last_update FROM system_status WHERE id = 1")
        row_st = cur.fetchone()
        
        plc_connected, machine_running, cam_online, current_model, last_update = False, False, False, 1, "--:--:--"
        if row_st:
            plc_connected, machine_running, cam_online, current_model, last_update_dt = row_st
            last_update = last_update_dt.strftime('%H:%M:%S')

        # 2. Thống kê sản lượng
        cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_ng = false), COUNT(*) FILTER (WHERE is_ng = true) FROM inspections")
        total, ok, ng = cur.fetchone()

        # 3. Nhật ký gần nhất (SỬA LỖI: created_at thay vì timestamp)
        cur.execute("SELECT id, product_name, result, created_at FROM inspections ORDER BY created_at DESC LIMIT 10")
        rows_logs = cur.fetchall()
        recent_logs = [[str(r[0]), r[1], r[2], r[3].strftime('%H:%M:%S')] for r in rows_logs]

        cur.close()
        conn.close()

        return jsonify({
            "total": total, "ok": ok, "ng": ng,
            "status": "RUNNING" if machine_running else "STOPPED",
            "plc_connected": plc_connected,
            "cam_connected": cam_online,
            "current_model": current_model,
            "last_sync": last_update,
            "recent_logs": recent_logs,
            "error_types": {"Dị vật": 0, "Vỡ": 0, "Thiếu viên": 0}, # Cần thêm logic nếu muốn chi tiết
            "hourly_data": [0]*8
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# Vercel yêu cầu app này
def handler(environ, start_response):
    return app(environ, start_response)
