from flask import Flask, jsonify
import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

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
            plc_connected, machine_running_db, cam_online, current_model, last_update_dt = row_st
            last_update = last_update_dt.strftime('%H:%M:%S')
            machine_running = machine_running_db

        # 2. Thống kê sản lượng
        cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_ng = false), COUNT(*) FILTER (WHERE is_ng = true) FROM inspections")
        total, ok, ng = cur.fetchone()

        # 3. Phân tích loại lỗi
        error_types = {"Dị vật": 0, "Vỡ": 0, "Thiếu viên": 0}
        cur.execute("SELECT result FROM inspections WHERE is_ng = true")
        rows_ng = cur.fetchall()
        for r in rows_ng:
            res_txt = r[0].lower()
            if "di vat" in res_txt: error_types["Dị vật"] += 1
            elif "vo" in res_txt or "nut" in res_txt: error_types["Vỡ"] += 1
            elif "thieu" in res_txt: error_types["Thiếu viên"] += 1

        # 4. Nhật ký gần nhất
        cur.execute("SELECT id, product_name, result, created_at FROM inspections ORDER BY created_at DESC LIMIT 10")
        rows_logs = cur.fetchall()
        recent_logs = [[str(r[0]), r[1], r[2], r[3].strftime('%H:%M:%S')] for r in rows_logs]

        # 5. Thống kê theo giờ (8 giờ gần nhất)
        cur.execute("""
            SELECT 
                to_char(hour, 'HH24') || 'h' as label,
                COUNT(i.id) as count
            FROM (
                SELECT generate_series(
                    date_trunc('hour', NOW()) - interval '7 hours',
                    date_trunc('hour', NOW()),
                    interval '1 hour'
                ) as hour
            ) h
            LEFT JOIN inspections i ON date_trunc('hour', i.created_at) = h.hour
            GROUP BY h.hour
            ORDER BY h.hour
        """)
        hourly_rows = cur.fetchall()
        hourly_labels = [r[0] for r in hourly_rows]
        hourly_data = [r[1] for r in hourly_rows]

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
            "error_types": error_types,
            "hourly_data": hourly_data,
            "hourly_labels": hourly_labels
        })

    except Exception as e:
        if 'conn' in locals() and conn:
            conn.close()
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/set_model/<int:model_id>')
def set_model(model_id):
    if not DB_URL:
        return jsonify({"status": "error", "message": "Chưa cấu hình SUPABASE_URL"})
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("UPDATE system_status SET current_model_id = %s WHERE id = 1", (model_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "success", "message": f"Đã cập nhật Model ID = {model_id}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/images')
def get_images():
    return jsonify([])

if __name__ == "__main__":
    app.run(debug=True)
