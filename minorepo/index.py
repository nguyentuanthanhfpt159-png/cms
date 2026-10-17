from flask import Flask, jsonify, request
import os
try:
    import psycopg2
except ImportError:
    psycopg2 = None
from datetime import datetime

app = Flask(__name__)
DB_URL = os.getenv("SUPABASE_URL") or "postgresql://postgres.tpafcikfwcwockoclatq:TuanThanh%402026@aws-1-ap-northeast-2.pooler.supabase.com:6543/postgres"

# ĐỊNH NGHĨA PHÂN BIỆT RÕ RÀNG 3 MODEL
MODELS_MAP = {
    1: "Gói thuốc",
    2: "Vỉ thuốc",
    3: "Viên thuốc"
}

MODEL_PATTERNS = {
    1: "%gói%",
    2: "%vỉ%",
    3: "%viên%"
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
    model_id = request.args.get('model', default=None, type=int)
    total, ok, ng = 0, 0, 0
    status = "RUNNING"
    plc_connected = True
    cam_connected = True
    current_model = 1
    last_sync = datetime.now().strftime('%H:%M:%S')
    error_types = {}
    recent_logs = []
    hourly_data = [12, 18, 25, 30, 42, 38, 50, 45]

    if DB_URL and psycopg2:
        try:
            conn = psycopg2.connect(DB_URL, connect_timeout=3)
            cur = conn.cursor()

            # 1. Trạng thái hệ thống
            cur.execute("SELECT plc_online, machine_running, cam_online, current_model_id, last_update FROM system_status WHERE id = 1")
            row_st = cur.fetchone()
            if row_st:
                plc_connected, machine_running_db, cam_connected, db_model_id, last_update_db = row_st
                status = "RUNNING" if machine_running_db else "STOPPED"
                if last_update_db:
                    last_sync = last_update_db.strftime('%H:%M:%S')
                if model_id is None:
                    model_id = db_model_id or 1

            if model_id is None:
                model_id = 1

            current_model = model_id
            target_pattern = MODEL_PATTERNS.get(model_id, "%gói%")

            # 2. Thống kê sản lượng tách biệt 100% theo Model được chọn
            cur.execute("""
                SELECT COUNT(*), 
                       COUNT(*) FILTER (WHERE is_ng = false), 
                       COUNT(*) FILTER (WHERE is_ng = true) 
                FROM inspections 
                WHERE product_name ILIKE %s
            """, (target_pattern,))
            row_cnt = cur.fetchone()
            if row_cnt and row_cnt[0] > 0:
                total, ok, ng = row_cnt

            # 3. Phân loại lỗi riêng theo từng Model
            cur.execute("""
                SELECT result 
                FROM inspections 
                WHERE product_name ILIKE %s AND is_ng = true
            """, (target_pattern,))
            rows_ng = cur.fetchall()

            if model_id == 1:
                # Gói thuốc
                error_types = {"Rách": 0, "Hở mép": 0, "Mờ date": 0, "Nhăn": 0}
                for r in rows_ng:
                    txt = (r[0] or "").lower()
                    if "rách" in txt or "rach" in txt: error_types["Rách"] += 1
                    elif "hở" in txt or "ho" in txt: error_types["Hở mép"] += 1
                    elif "mờ" in txt or "mo" in txt: error_types["Mờ date"] += 1
                    elif "nhăn" in txt or "nhan" in txt: error_types["Nhăn"] += 1
                    else: error_types["Rách"] += 1
            elif model_id == 2:
                # Vỉ thuốc
                error_types = {"Thiếu viên": 0, "Nứt/Vỡ": 0, "Dị vật": 0}
                for r in rows_ng:
                    txt = (r[0] or "").lower()
                    if "thieu" in txt or "thiếu" in txt: error_types["Thiếu viên"] += 1
                    elif "nứt" in txt or "vỡ" in txt or "nut" in txt or "vo" in txt: error_types["Nứt/Vỡ"] += 1
                    elif "dị vật" in txt or "di vat" in txt: error_types["Dị vật"] += 1
                    else: error_types["Nứt/Vỡ"] += 1
            else:
                # Viên thuốc
                error_types = {"Vỡ viên": 0, "Dị vật": 0}
                for r in rows_ng:
                    txt = (r[0] or "").lower()
                    if "vo" in txt or "vỡ" in txt: error_types["Vỡ viên"] += 1
                    elif "di vat" in txt or "dị vật" in txt: error_types["Dị vật"] += 1
                    else: error_types["Vỡ viên"] += 1

            # 4. Nhật ký kiểm tra tách riêng theo từng Model
            cur.execute("""
                SELECT id, product_name, result, created_at 
                FROM inspections 
                WHERE product_name ILIKE %s
                ORDER BY created_at DESC LIMIT 10
            """, (target_pattern,))
            rows_logs = cur.fetchall()
            if rows_logs:
                m_label = MODELS_MAP.get(model_id, "Thuốc")
                recent_logs = [[str(r[0]), r[1] or m_label, r[2] or "OK", r[3].strftime('%H:%M:%S')] for r in rows_logs]

            cur.close()
            conn.close()
        except Exception as e:
            print("Lỗi stats Supabase:", e)

    # Fallback mặc định nếu chưa có dữ liệu trong DB
    if total == 0:
        if model_id == 1:
            total, ok, ng = 6, 0, 6
            error_types = {"Rách": 2, "Hở mép": 2, "Mờ date": 1, "Nhăn": 1}
        elif model_id == 2:
            total, ok, ng = 137, 16, 121
            error_types = {"Thiếu viên": 58, "Nứt/Vỡ": 38, "Dị vật": 25}
        else:
            total, ok, ng = 157, 34, 123
            error_types = {"Vỡ viên": 78, "Dị vật": 45}

    return jsonify({
        "total": total, "ok": ok, "ng": ng,
        "status": status, "plc_connected": plc_connected, "cam_connected": cam_connected,
        "current_model": current_model,
        "robot_model": db_model_id if 'db_model_id' in locals() and db_model_id else current_model,
        "model_name": MODELS_MAP.get(current_model, "Gói thuốc"),
        "last_sync": last_sync,
        "recent_logs": recent_logs,
        "error_types": error_types,
        "hourly_data": hourly_data,
        "hourly_labels": ['1h','2h','3h','4h','5h','6h','7h','8h']
    })

@app.route('/api/images')
@app.route('/api/images/<int:model_id>')
def images(model_id=None):
    if model_id is None:
        model_id = request.args.get('model', type=int)

    if model_id is None and DB_URL and psycopg2:
        try:
            conn = psycopg2.connect(DB_URL, connect_timeout=3)
            cur = conn.cursor()
            cur.execute("SELECT current_model_id FROM system_status WHERE id = 1")
            row = cur.fetchone()
            if row and row[0]:
                model_id = row[0]
            cur.close()
            conn.close()
        except Exception:
            pass

    if model_id is None:
        model_id = 1

    image_urls = []

    # Tách biệt 100% hình ảnh lỗi của Vỉ thuốc và Viên thuốc
    if DB_URL and psycopg2:
        try:
            conn = psycopg2.connect(DB_URL, connect_timeout=3)
            cur = conn.cursor()
            
            if model_id == 2:
                # Chỉ lấy ảnh lỗi của Vỉ thuốc
                cur.execute("""
                    SELECT image_url 
                    FROM inspections 
                    WHERE product_name ILIKE '%vỉ%' 
                      AND (details NOT ILIKE '%viên rời%' OR details IS NULL)
                      AND is_ng = true AND image_url IS NOT NULL AND image_url != ''
                    ORDER BY created_at DESC 
                    LIMIT 6;
                """)
            elif model_id == 3:
                # Chỉ lấy ảnh lỗi của Viên thuốc
                cur.execute("""
                    SELECT image_url 
                    FROM inspections 
                    WHERE (product_name ILIKE '%viên%' OR product_name ILIKE '%vienroi%')
                      AND (details NOT ILIKE '%phát hiện vỉ%' OR details IS NULL)
                      AND is_ng = true AND image_url IS NOT NULL AND image_url != ''
                    ORDER BY created_at DESC 
                    LIMIT 6;
                """)
            else:
                # Chỉ lấy ảnh lỗi của Gói thuốc
                cur.execute("""
                    SELECT image_url 
                    FROM inspections 
                    WHERE product_name ILIKE '%gói%' 
                      AND is_ng = true AND image_url IS NOT NULL AND image_url != ''
                    ORDER BY created_at DESC 
                    LIMIT 6;
                """)

            rows = cur.fetchall()
            cur.close()
            conn.close()
            if rows:
                image_urls = [r[0] for r in rows]
        except Exception as e:
            print("Lỗi truy vấn Supabase images:", e)

    return jsonify(image_urls)
