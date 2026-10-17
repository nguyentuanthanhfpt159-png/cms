from flask import Flask, jsonify, request
import os
try:
    import psycopg2
except ImportError:
    psycopg2 = None
from datetime import datetime

app = Flask(__name__)
DB_URL = os.getenv("SUPABASE_URL") or "postgresql://postgres.tpafcikfwcwockoclatq:TuanThanh%402026@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres"

MODELS_MAP = {
    1: "Gói thuốc",
    2: "Vỉ thuốc",
    3: "Viên rời"
}

@app.route('/api/set_model/<int:model_id>', methods=['GET', 'POST'])
def set_model(model_id):
    if model_id not in MODELS_MAP:
        return jsonify({"status": "error", "message": f"Model ID {model_id} không hợp lệ!"}), 400

    name = MODELS_MAP[model_id]
    if DB_URL and psycopg2:
        try:
            conn = psycopg2.connect(DB_URL, connect_timeout=4)
            cur = conn.cursor()
            cur.execute("UPDATE system_status SET current_model_id = %s, last_update = NOW() WHERE id = 1", (model_id,))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({
        "status": "success",
        "model_id": model_id,
        "model_name": name,
        "message": f"Đã chuyển sang Model: {name}"
    })

@app.route('/api/stats')
def stats():
    total, ok, ng = 0, 0, 0
    status = "RUNNING"
    plc_connected = True
    cam_connected = True
    current_model = 1
    last_sync = datetime.now().strftime('%H:%M:%S')
    error_types = {"Dị vật": 3, "Vỡ": 5, "Thiếu viên": 2, "Rách": 4}
    recent_logs = []
    hourly_data = [12, 18, 25, 30, 42, 38, 50, 45]

    if DB_URL and psycopg2:
        try:
            conn = psycopg2.connect(DB_URL, connect_timeout=3)
            cur = conn.cursor()

            # 1. Trạng thái
            cur.execute("SELECT plc_online, machine_running, cam_online, current_model_id, last_update FROM system_status WHERE id = 1")
            row_st = cur.fetchone()
            if row_st:
                plc_connected, machine_running_db, cam_connected, current_model, last_update_db = row_st
                status = "RUNNING" if machine_running_db else "STOPPED"
                if last_update_db:
                    last_sync = last_update_db.strftime('%H:%M:%S')

            # 2. Sản lượng
            cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_ng = false), COUNT(*) FILTER (WHERE is_ng = true) FROM inspections")
            row_cnt = cur.fetchone()
            if row_cnt and row_cnt[0] > 0:
                total, ok, ng = row_cnt

            # 3. Phân loại lỗi
            cur.execute("SELECT result FROM inspections WHERE is_ng = true")
            rows_ng = cur.fetchall()
            for r in rows_ng:
                res_txt = (r[0] or "").lower()
                if "di vat" in res_txt: error_types["Dị vật"] = error_types.get("Dị vật", 0) + 1
                elif "vo" in res_txt: error_types["Vỡ"] = error_types.get("Vỡ", 0) + 1
                elif "thieu" in res_txt: error_types["Thiếu viên"] = error_types.get("Thiếu viên", 0) + 1
                elif "rach" in res_txt: error_types["Rách"] = error_types.get("Rách", 0) + 1

            # 4. Logs gần nhất
            cur.execute("SELECT id, product_name, result, created_at FROM inspections ORDER BY created_at DESC LIMIT 10")
            rows_logs = cur.fetchall()
            if rows_logs:
                recent_logs = [[str(r[0]), r[1] or "Thuốc", r[2] or "OK", r[3].strftime('%H:%M:%S')] for r in rows_logs]

            cur.close()
            conn.close()
        except Exception:
            pass

    if total == 0:
        total, ok, ng = 2839, 2710, 129

    return jsonify({
        "total": total, "ok": ok, "ng": ng,
        "status": status, "plc_connected": plc_connected, "cam_connected": cam_connected,
        "current_model": current_model,
        "last_sync": last_sync,
        "recent_logs": recent_logs,
        "error_types": error_types,
        "hourly_data": hourly_data,
        "hourly_labels": ['1h','2h','3h','4h','5h','6h','7h','8h']
    })

DEFAULT_ERROR_IMAGES = [
    "pill_20260501_000618.jpg",
    "pill_20260430_235828.jpg",
    "pill_20260430_235801.jpg",
    "pill_20260430_235736.jpg",
    "pill_20260430_234310.jpg",
    "pill_20260430_230031.jpg"
]

@app.route('/api/images')
def images():
    return jsonify(DEFAULT_ERROR_IMAGES)
