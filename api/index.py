from flask import Flask, render_template, jsonify, send_from_directory
import os
import pandas as pd
import time
import json
from datetime import datetime

# VÔ HIỆU HÓA PLC VÀ YOLO TRÊN VERCEL
# import kiem_tra_thuoc_logic as logic 

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Cấu hình đường dẫn (Trên Cloud sẽ để mặc định hoặc dùng Database sau này)
BASE_DIR = "/tmp" # Vercel cho phép ghi tạm vào /tmp
LOG_FILE = os.path.join(BASE_DIR, "Lich_su_phan_loai.csv")
IMAGE_DIR = os.path.join(BASE_DIR, "NG_LOI") 
STATUS_FILE = os.path.join(BASE_DIR, "system_status.json")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/set_model/<int:model_id>')
def set_model(model_id):
    return jsonify({"status": "warning", "message": "Chức năng đổi Model yêu cầu kết nối PLC thực tế tại nhà."})

@app.route('/api/stats')
def get_stats():
    # Mock data khi chưa có Supabase
    return jsonify({
        "ok": 0, "ng": 0, "total": 0,
        "status": "OFFLINE",
        "plc_connected": False,
        "cam_connected": False,
        "current_model": "Chưa rõ",
        "last_sync": "Cloud Mode",
        "error_types": {"Dị vật": 0, "Vỡ": 0, "Thiếu viên": 0},
        "hourly_data": [0]*8,
        "hourly_labels": ['1h','2h','3h','4h','5h','6h','7h','8h'],
        "recent_logs": []
    })

@app.route('/api/images')
def get_recent_errors():
    return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
