from flask import Flask, render_template, jsonify, send_from_directory, request
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

try:
    import pandas as pd
except ImportError:
    pd = None
import time
import json
from datetime import datetime
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

app = Flask(__name__, template_folder=os.path.dirname(os.path.abspath(__file__)))

# Cấu hình đường dẫn tích hợp Delta Robot & Hệ thống Vision
BASE_DIR = r"d:\Eruka"
LOG_FILE = os.path.join(BASE_DIR, "Ket_qua_thuc_nghiem.csv")
OLD_LOG_FILE = os.path.join(BASE_DIR, "minorepo", "captured_medicine", "Lich_su_phan_loai.csv")
CMD_FILE = os.path.join(BASE_DIR, "command.json")
STATUS_FILE = os.path.join(BASE_DIR, "minorepo", "system_status.json")
IMAGE_DIR = os.path.join(BASE_DIR, "minorepo", "captured_medicine", "NG_LOI")

MODELS_MAP = {
    1: {"code": "GOI_THUOC", "name": "Gói thuốc"},
    2: {"code": "VITHUOC", "name": "Vỉ thuốc"},
    3: {"code": "VIENROI", "name": "Viên rời"}
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/set_model/<int:model_id>', methods=['GET', 'POST'])
def set_model(model_id):
    if model_id not in MODELS_MAP:
        return jsonify({"status": "error", "message": f"Model ID {model_id} không hợp lệ!"}), 400
    
    info = MODELS_MAP[model_id]

    # 1. Ghi ra command.json để sapdendichroi.py nhận diện
    try:
        cmd_data = {
            "cmd": "set_model",
            "model_id": model_id,
            "model_code": info["code"],
            "model_name": info["name"],
            "timestamp": time.time()
        }
        with open(CMD_FILE, "w", encoding="utf-8") as f:
            json.dump(cmd_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Lỗi ghi CMD_FILE: {e}")

    # 2. Cập nhật file system_status.json local
    try:
        st_data = {}
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                st_data = json.load(f)
        st_data["current_model"] = model_id
        st_data["current_model_code"] = info["code"]
        st_data["current_model_name"] = info["name"]
        st_data["last_update"] = time.time()
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(st_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[WARN] Loi ghi STATUS_FILE: {e}")

    # 3. Đồng bộ lên Cloud Supabase nếu có kết nối
    if DB_URL:
        try:
            conn = psycopg2.connect(DB_URL, connect_timeout=3)
            cur = conn.cursor()
            cur.execute("UPDATE system_status SET current_model_id = %s, last_update = NOW() WHERE id = 1", (model_id,))
            conn.commit()
            cur.close()
            conn.close()
            print(f"[SUCCESS] Da dong bo Model {model_id} ({info['name']}) len Supabase!")
        except Exception as e:
            print(f"[WARN] Loi update Supabase: {e}")

    return jsonify({
        "status": "success",
        "model_id": model_id,
        "model_code": info["code"],
        "model_name": info["name"],
        "message": f"Đã chuyển sang Model: {info['name']}"
    })

@app.route('/api/stats')
def get_stats():
    ok, ng, total = 0, 0, 0
    status = "RUNNING"
    plc_connected = True
    cam_connected = True
    hourly_data = [12, 18, 25, 30, 42, 38, 50, 45]
    error_types = {"Dị vật": 3, "Vỡ": 5, "Thiếu viên": 2, "Rách": 4}
    recent_logs = []
    last_sync = datetime.now().strftime('%H:%M:%S')
    current_model = 1

    db_success = False
    if DB_URL:
        try:
            conn = psycopg2.connect(DB_URL, connect_timeout=3)
            cur = conn.cursor()
            
            # 1. Trạng thái hệ thống
            cur.execute("SELECT plc_online, machine_running, cam_online, current_model_id, last_update FROM system_status WHERE id = 1")
            row_st = cur.fetchone()
            if row_st:
                plc_connected, machine_running_db, cam_connected, current_model, last_update_db = row_st
                status = "RUNNING" if machine_running_db else "STOPPED"
                if last_update_db:
                    last_sync = last_update_db.strftime('%H:%M:%S')

            # 2. Thống kê sản lượng
            cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_ng = false), COUNT(*) FILTER (WHERE is_ng = true) FROM inspections")
            row_cnt = cur.fetchone()
            if row_cnt and row_cnt[0] > 0:
                total, ok, ng = row_cnt

            # 3. Phân tích loại lỗi
            cur.execute("SELECT result FROM inspections WHERE is_ng = true")
            rows_ng = cur.fetchall()
            for r in rows_ng:
                res_txt = (r[0] or "").lower()
                if "di vat" in res_txt: error_types["Dị vật"] = error_types.get("Dị vật", 0) + 1
                elif "vo" in res_txt: error_types["Vỡ"] = error_types.get("Vỡ", 0) + 1
                elif "thieu" in res_txt: error_types["Thiếu viên"] = error_types.get("Thiếu viên", 0) + 1
                elif "rach" in res_txt: error_types["Rách"] = error_types.get("Rách", 0) + 1

            # 4. Nhật ký gần nhất
            cur.execute("SELECT id, product_name, result, created_at FROM inspections ORDER BY created_at DESC LIMIT 10")
            rows_logs = cur.fetchall()
            if rows_logs:
                recent_logs = [[str(r[0]), r[1] or "Thuốc", r[2] or "OK", r[3].strftime('%H:%M:%S')] for r in rows_logs]

            cur.close()
            conn.close()
            db_success = True
        except Exception as e:
            print(f"[NOTE] Database Supabase offline hoặc timeout: {e}")

    # Fallback dữ liệu từ file thực nghiệm thực tế nếu Supabase offline hoặc chưa có dữ liệu
    if not db_success or total == 0:
        if os.path.exists(STATUS_FILE):
            try:
                with open(STATUS_FILE, "r", encoding="utf-8") as f:
                    st_data = json.load(f)
                    plc_connected = st_data.get("plc_connected", True)
                    cam_connected = st_data.get("cam_connected", True)
                    status = st_data.get("status", "RUNNING")
                    current_model = st_data.get("current_model", current_model)
            except Exception:
                pass

        target_csv = LOG_FILE if os.path.exists(LOG_FILE) else (OLD_LOG_FILE if os.path.exists(OLD_LOG_FILE) else None)
        if target_csv and pd is not None:
            try:
                df = pd.read_csv(target_csv)
                total = len(df)
                if 'Kết Quả Phân Loại' in df.columns:
                    ng_mask = df['Kết Quả Phân Loại'].str.contains('NG|LỖI', case=False, na=False)
                    ng = int(ng_mask.sum())
                    ok = total - ng
                    
                    recent_df = df.tail(10).iloc[::-1]
                    recent_logs = []
                    for _, r in recent_df.iterrows():
                        recent_logs.append([
                            str(r.get('Mã Gói', r.get('STT', ''))),
                            str(r.get('Nhãn AI Nhận Diện', 'Gói thuốc')),
                            str(r.get('Kết Quả Phân Loại', 'OK')),
                            str(r.get('Thời Gian', ''))
                        ])
                elif 'Result' in df.columns:
                    ng = len(df[df['Result'].str.contains('NG|Lỗi|Rách|Vỡ|Dị vật', case=False, na=False)])
                    ok = total - ng
            except Exception as ex:
                print(f"Lỗi đọc file CSV {target_csv}: {ex}")

    return jsonify({
        "total": total, "ok": ok, "ng": ng,
        "status": status, "plc_connected": plc_connected, "cam_connected": cam_connected,
        "current_model": current_model,
        "last_sync": last_sync,
        "error_types": error_types, "hourly_data": hourly_data,
        "hourly_labels": ['1h','2h','3h','4h','5h','6h','7h','8h'],
        "recent_logs": recent_logs
    })

@app.route('/api/images')
@app.route('/api/images/<int:model_id>')
def get_recent_errors(model_id=None):
    if model_id is None:
        model_id = request.args.get('model', type=int)

    if model_id is None:
        if os.path.exists(CMD_FILE):
            try:
                with open(CMD_FILE, "r", encoding="utf-8") as f:
                    cmd_data = json.load(f)
                    model_id = cmd_data.get("model_id", 1)
            except Exception:
                model_id = 1
        else:
            model_id = 1

    # 1. Ưu tiên truy vấn ĐỘNG trực tiếp từ Supabase
    info = MODELS_MAP.get(model_id, {"name": "Gói thuốc"})
    prod_name = info["name"]
    if DB_URL and psycopg2:
        try:
            conn = psycopg2.connect(DB_URL, connect_timeout=3)
            cur = conn.cursor()
            cur.execute("""
                SELECT image_url 
                FROM inspections 
                WHERE product_name ILIKE %s AND is_ng = true AND image_url IS NOT NULL AND image_url != ''
                ORDER BY created_at DESC 
                LIMIT 6;
            """, (f"%{prod_name}%",))
            rows = cur.fetchall()
            cur.close()
            conn.close()
            if rows:
                return jsonify([r[0] for r in rows])
        except Exception:
            pass

    # 2. Đọc ĐỘNG từ thư mục riêng biệt của từng loại thuốc trên ổ đĩa máy tính
    folder_map = {1: "GOI_THUOC", 2: "VITHUOC", 3: "VIENROI"}
    sub_folder = folder_map.get(model_id, "GOI_THUOC")
    sub_dir = os.path.join(IMAGE_DIR, sub_folder)

    if os.path.exists(sub_dir):
        try:
            files = [f for f in os.listdir(sub_dir) if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
            if files:
                files.sort(key=lambda x: os.path.getmtime(os.path.join(sub_dir, x)), reverse=True)
                return jsonify([f"{sub_folder}/{f}" for f in files[:6]])
        except Exception:
            pass

    return jsonify([])

@app.route('/error_images/<path:filename>')
def serve_image(filename):
    if os.path.exists(IMAGE_DIR):
        return send_from_directory(IMAGE_DIR, filename)
    return "", 404

if __name__ == '__main__':
    print("🚀 Đang khởi động Web Dashboard tại: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
