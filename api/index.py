from flask import Flask, render_template, jsonify, send_from_directory
import os
import pandas as pd
import time
import json
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

app = Flask(__name__, template_folder='../templates', static_folder='../static')

def get_db_connection():
    return psycopg2.connect(DB_URL)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    if not DB_URL:
        return jsonify({"status": "error", "message": "Chưa cấu hình SUPABASE_URL"})

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 1. Lấy trạng thái hệ thống mới nhất
        cur.execute("SELECT * FROM system_status WHERE id = 1")
        st = cur.fetchone()
        
        status = "STOPPED"
        plc_connected = False
        cam_connected = False
        last_sync = "Không có dữ liệu"
        current_model = 1

        if st:
            diff = (datetime.now(st['last_update'].tzinfo) - st['last_update']).total_seconds()
            if diff < 15: # Coi như online nếu cập nhật trong 15s qua
                plc_connected = st['plc_online']
                cam_connected = st['cam_online']
                status = "RUNNING" if st['machine_running'] else "STOPPED"
                last_sync = st['last_update'].strftime('%H:%M:%S')
                current_model = st['current_model_id']
            else:
                last_sync = "Mất đồng bộ"

        # 2. Tính toán thống kê từ bảng inspections
        cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_ng THEN 1 ELSE 0 END) as ng FROM inspections")
        counts = cur.fetchone()
        total = counts['total'] or 0
        ng = counts['ng'] or 0
        ok = total - ng

        # 3. Đếm loại lỗi
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE result ILIKE '%di vat%') as di_vat,
                COUNT(*) FILTER (WHERE result ILIKE '%vo%') as vo,
                COUNT(*) FILTER (WHERE result ILIKE '%thieu%') as thieu
            FROM inspections WHERE is_ng = true
        """)
        errors = cur.fetchone()
        error_types = {
            "Dị vật": errors['di_vat'] or 0,
            "Vỡ": errors['vo'] or 0,
            "Thiếu viên": errors['thieu'] or 0
        }

        # 4. Lấy 10 log gần nhất
        cur.execute("SELECT product_name, result, timestamp FROM inspections ORDER BY timestamp DESC LIMIT 10")
        logs = cur.fetchall()
        recent_logs = []
        for l in logs:
            recent_logs.append([
                l['product_name'],
                l['result'],
                l['timestamp'].strftime('%H:%M:%S')
            ])

        # 5. Dữ liệu biểu đồ theo giờ (8 giờ gần nhất)
        hourly_data = []
        hourly_labels = []
        for i in range(7, -1, -1):
            target_hour = datetime.now() - timedelta(hours=i)
            label = target_hour.strftime('%H:00')
            hourly_labels.append(label)
            
            cur.execute("""
                SELECT COUNT(*) FROM inspections 
                WHERE timestamp >= %s AND timestamp < %s
            """, (target_hour.replace(minute=0, second=0, microsecond=0), 
                  target_hour.replace(minute=59, second=59, microsecond=999999)))
            h_count = cur.fetchone()['count']
            hourly_data.append(h_count)

        cur.close()
        conn.close()

        return jsonify({
            "ok": ok, "ng": ng, "total": total,
            "status": status,
            "plc_connected": plc_connected,
            "cam_connected": cam_connected,
            "current_model": "Viên rời" if current_model == 1 else "Vỉ thuốc",
            "last_sync": last_sync,
            "error_types": error_types,
            "hourly_data": hourly_data,
            "hourly_labels": hourly_labels,
            "recent_logs": recent_logs
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/images')
def get_recent_errors():
    # Phần này tạm thời trả về trống vì ảnh đang lưu ở máy tính cục bộ
    # Sau này anh có thể dùng Cloudinary để đẩy ảnh lên mây
    return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
