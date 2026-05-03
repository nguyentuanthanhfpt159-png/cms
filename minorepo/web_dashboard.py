from flask import Flask, render_template, jsonify, send_from_directory
import os
import pandas as pd
import time
import json
from datetime import datetime
import kiem_tra_thuoc_logic as logic
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

app = Flask(__name__)

# Cấu hình đường dẫn (PHẢI KHỚP VỚI main1.py)
BASE_DIR = r"D:\Code\captured_medicine"
LOG_FILE = os.path.join(BASE_DIR, "Lich_su_phan_loai.csv")
IMAGE_DIR = os.path.join(BASE_DIR, "NG_LOI") 
STATUS_FILE = os.path.join(BASE_DIR, "system_status.json")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    if not DB_URL:
        return jsonify({"status": "error", "message": "Chua cau hinh SUPABASE_URL"})

    ok, ng, total = 0, 0, 0
    status = "STOPPED"
    plc_connected = False
    cam_connected = False
    hourly_data = [0]*8
    error_types = {"Dị vật": 0, "Vỡ": 0, "Thiếu viên": 0}
    recent_logs = []
    last_sync = "--:--:--"
    current_model = 1

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        # 1. Trạng thái hệ thống
        cur.execute("SELECT plc_online, machine_running, cam_online, current_model_id, last_update FROM system_status WHERE id = 1")
        row_st = cur.fetchone()
        if row_st:
            plc_connected, machine_running_db, cam_connected, current_model, last_update_db = row_st
            status = "RUNNING" if machine_running_db else "STOPPED"
            last_sync = last_update_db.strftime('%H:%M:%S')

        # 2. Thống kê sản lượng
        cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_ng = false), COUNT(*) FILTER (WHERE is_ng = true) FROM inspections")
        total, ok, ng = cur.fetchone()

        # 3. Phân tích loại lỗi
        error_types = {"Dị vật": 0, "Vỡ/Nứt": 0, "Thiếu viên": 0, "Lỗi vỉ": 0}
        cur.execute("SELECT product_name, result FROM inspections WHERE is_ng = true")
        rows_ng = cur.fetchall()
        for prod_name, result in rows_ng:
            res_txt = result.lower()
            if "di vat" in res_txt: error_types["Dị vật"] += 1
            if "vo" in res_txt or "nut" in res_txt: error_types["Vỡ/Nứt"] += 1
            if "thieu" in res_txt: error_types["Thiếu viên"] += 1
            if "vỉ" in prod_name.lower(): error_types["Lỗi vỉ"] += 1

        # 4. Nhật ký gần nhất (Sử dụng created_at)
        cur.execute("SELECT id, product_name, result, created_at FROM inspections ORDER BY created_at DESC LIMIT 10")
        rows_logs = cur.fetchall()
        recent_logs = [[str(r[0]), r[1], r[2], r[3].strftime('%H:%M:%S')] for r in rows_logs]

        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

    return jsonify({
        "total": total, "ok": ok, "ng": ng,
        "status": status, "plc_connected": plc_connected, "cam_connected": cam_connected,
        "current_model": current_model,
        "last_sync": last_sync,
        "error_types": error_types, "hourly_data": hourly_data,
        "hourly_labels": ['1h','2h','3h','4h','5h','6h','7h','8h'],
        "recent_logs": recent_logs,
        "is_vi_thuoc": "vỉ" in (recent_logs[0][1].lower() if recent_logs else "")
    })

@app.route('/api/images')
def get_recent_errors():
    return jsonify([]) # Vercel không xem được ảnh local

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
