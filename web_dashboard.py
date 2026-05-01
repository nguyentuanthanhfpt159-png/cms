from flask import Flask, render_template, jsonify, send_from_directory
import os
import pandas as pd
import time
import json
from datetime import datetime
import kiem_tra_thuoc_logic as logic

app = Flask(__name__)

# Cấu hình đường dẫn (PHẢI KHỚP VỚI main1.py)
BASE_DIR = r"D:\Code\captured_medicine"
LOG_FILE = os.path.join(BASE_DIR, "Lich_su_phan_loai.csv")
IMAGE_DIR = os.path.join(BASE_DIR, "NG_LOI") 
STATUS_FILE = os.path.join(BASE_DIR, "system_status.json")

print(f"--- DASHBOARD DANG TIM DU LIEU TAI: {LOG_FILE} ---")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/set_model/<int:model_id>')
def set_model(model_id):
    try:
        # Thay vì gửi trực tiếp tới PLC (gây xung đột), ta ghi vào file lệnh
        # main1.py sẽ đọc file này và thực hiện lệnh
        cmd_path = os.path.join(BASE_DIR, "command.json")
        with open(cmd_path, "w") as f:
            json.dump({"cmd": "set_model", "value": model_id, "timestamp": time.time()}, f)
        
        return jsonify({"status": "success", "message": f"Đã gửi yêu cầu đổi Model {model_id}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/stats')
def get_stats():
    ok, ng, total = 0, 0, 0
    status = "STOPPED"
    plc_connected = False
    cam_connected = False
    hourly_data = [0]*8
    error_types = {"Dị vật": 0, "Vỡ": 0, "Thiếu viên": 0}
    recent_logs = []
    last_sync = "--:--:--"
    current_model = 1
    st = {}

    # 1. Đọc trạng thái từ file JSON
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                st = json.load(f)
                diff = time.time() - st.get('last_update', 0)
                if diff < 10:
                    plc_connected = st.get('plc_online', False)
                    cam_connected = st.get('cam_online', False)
                    status = "RUNNING" if st.get('machine_running', False) else "STOPPED"
                    last_sync = datetime.fromtimestamp(st.get('last_update', 0)).strftime('%H:%M:%S')
                    current_model = st.get('current_model_id', 1)
                else:
                    plc_connected = False
                    cam_connected = False
                    last_sync = "Mất đồng bộ"
        except Exception as e:
            print(f"Debug: Lỗi đọc file JSON: {e}")

    # 2. Đọc dữ liệu từ CSV
    if os.path.exists(LOG_FILE):
        try:
            df = pd.read_csv(LOG_FILE, encoding='utf-8', on_bad_lines='skip')
            df.columns = df.columns.str.strip()
            
            # Kiểm tra cột bắt buộc tồn tại
            if not df.empty and 'Kết quả' in df.columns:
                total = len(df)
                # Dùng marker [NG]/[OK] để đếm chính xác, tránh nhầm vì tiếng Việt
                ng = int(df['Kết quả'].astype(str).str.startswith("[NG]").sum())
                ok = total - ng
                
                # Đếm loại lỗi
                error_types["Dị vật"] = int(df['Kết quả'].astype(str).str.contains("di vat", case=False).sum())
                error_types["Vỡ"]     = int(df['Kết quả'].astype(str).str.contains("vo", case=False).sum())
                error_types["Thiếu viên"] = int(df['Kết quả'].astype(str).str.contains("thieu", case=False).sum())
                
                # Biểu đồ theo giờ - hỗ trợ cả 2 định dạng timestamp
                if 'Thời gian' in df.columns:
                    def parse_time(s):
                        s = str(s).strip()
                        # Mới: "2026-04-27 23:32:32"
                        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y%m%d_%H%M%S", "%H:%M:%S"]:
                            try:
                                return datetime.strptime(s, fmt)
                            except:
                                continue
                        return None
                    df['_dt'] = pd.to_datetime(df['Thời gian'].apply(parse_time), errors='coerce')
                    current_hour = pd.Timestamp.now().floor('h')
                    hours = [current_hour - pd.Timedelta(hours=i) for i in range(7, -1, -1)]
                    hourly_labels = [h.strftime('%H:00') for h in hours]
                    hourly_data = []
                    for h in hours:
                        count = df[(df['_dt'] >= h) & (df['_dt'] < h + pd.Timedelta(hours=1))].shape[0]
                        hourly_data.append(int(count))
                else:
                    hourly_labels = ['1h','2h','3h','4h','5h','6h','7h','8h']
                
                # 10 bản ghi gần nhất - trả về 4 phần tử đúng thứ tự: [STT, Sản phẩm, Kết quả, Thời gian]
                # Thử lấy các cột theo định dạng cũ (4 cột) hoặc định dạng mới (3 cột)
                df_tail = df.tail(10).fillna('')
                recent_logs = []
                for i, row in df_tail.iterrows():
                    vals = list(row.values)
                    if len(vals) >= 4:
                        # Định dạng cũ: STT, Sản phẩm, Kết quả, Thời gian
                        recent_logs.append([str(vals[0]), str(vals[1]), str(vals[2]), str(vals[3])])
                    elif len(vals) == 3:
                        # Định dạng mới: Sản phẩm, Kết quả, Thời gian -> đệm STT
                        recent_logs.append([str(i+1), str(vals[0]), str(vals[1]), str(vals[2])])
                recent_logs = recent_logs[::-1]  # Mới nhất lên đầu

        except Exception as e:
            print(f"Debug: Lỗi xử lý CSV: {e}")
    else:
        print(f"Debug: Không tìm thấy file CSV tại {LOG_FILE}")

    return jsonify({
        "total": total, "ok": ok, "ng": ng,
        "status": status, "plc_connected": plc_connected, "cam_connected": cam_connected,
        "current_model": current_model,
        "last_sync": last_sync,
        "error_types": error_types, "hourly_data": hourly_data,
        "hourly_labels": hourly_labels if 'hourly_labels' in locals() else ['1h','2h','3h','4h','5h','6h','7h','8h'],
        "recent_logs": recent_logs
    })

@app.route('/api/images')
def get_recent_errors():
    if not os.path.exists(IMAGE_DIR):
        return jsonify([])
    try:
        files = [f for f in os.listdir(IMAGE_DIR) if f.endswith('.jpg')]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(IMAGE_DIR, x)), reverse=True)
        return jsonify(files[:12])
    except:
        return jsonify([])

@app.route('/error_images/<filename>')
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

if __name__ == '__main__':
    print(f"--- DASHBOARD DANG CHAY TAI: http://localhost:5000 ---")
    app.run(host='0.0.0.0', port=5000, debug=False)
