from flask import Flask, jsonify, make_response
import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
import io
import csv

load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

app = Flask(__name__)

@app.route('/api/export')
@app.route('/export')
def export_all():
    if not DB_URL:
        return "Chưa cấu hình Database", 500

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SET TIME ZONE 'Asia/Ho_Chi_Minh';")
        
        # Lấy toàn bộ dữ liệu nhật ký
        cur.execute("SELECT id, product_name, result, created_at FROM inspections ORDER BY created_at DESC")
        rows = cur.fetchall()
        
        # Tạo file CSV trong bộ nhớ
        si = io.StringIO()
        si.write('\ufeff') # Thêm BOM để hiển thị đúng tiếng Việt trong Excel
        cw = csv.writer(si)
        cw.writerow(['ID', 'Sản phẩm', 'Kết quả', 'Thời gian'])
        
        for r in rows:
            cw.writerow([
                str(r[0]), 
                r[1], 
                r[2], 
                r[3].strftime('%d/%m/%Y %H:%M') if r[3] else ""
            ])
        
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=Bao_cao_Pharma_Full_{datetime.now().strftime('%Y%m%d')}.csv"
        output.headers["Content-type"] = "text/csv; charset=utf-8"
        
        cur.close()
        conn.close()
        return output

    except Exception as e:
        return str(e), 500

@app.route('/api/stats')
@app.route('/stats')

def get_stats():
    if not DB_URL:
        return jsonify({"status": "error", "message": "Chưa cấu hình SUPABASE_URL"})

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SET TIME ZONE 'Asia/Ho_Chi_Minh';")
        
        # 1. Trạng thái hệ thống và bộ đếm từ system_status
        cur.execute("""
            SELECT 
                plc_online, machine_running, cam_online, current_model_id, last_update,
                vien_ok, vien_ng, vi_ok, vi_ng
            FROM system_status 
            WHERE id = 1
        """)
        row_st = cur.fetchone()
        
        plc_connected, machine_running, cam_online, current_model, last_update = False, False, False, 1, "--:--:--"
        ss_vien_ok, ss_vien_ng, ss_vi_ok, ss_vi_ng = 0, 0, 0, 0
        
        if row_st:
            plc_connected, machine_running_db, cam_online, current_model, last_update_dt, \
            ss_vien_ok, ss_vien_ng, ss_vi_ok, ss_vi_ng = row_st
            last_update = last_update_dt.strftime('%d/%m/%Y %H:%M') if last_update_dt else "--:--:--"
            machine_running = machine_running_db
        
        # Mapping ID -> Name
        mapping = {1: "Viên rời", 2: "Vỉ thuốc"}
        current_model_name = mapping.get(current_model, "Unknown")

        # 2. Thống kê sản lượng từ counters
        vien_total = ss_vien_ok + ss_vien_ng
        vi_total = ss_vi_ok + ss_vi_ng
        
        # 3. Phân tích loại lỗi theo model hiện tại
        # Lấy counter NG thực tế từ system_status
        current_ng_total = ss_vien_ng if current_model == 1 else ss_vi_ng
        
        # Khởi tạo các loại lỗi tùy theo Model (Viên rời chỉ có Dị vật và Vỡ/Nứt)
        if current_model == 1:
            error_types = {"Dị vật": 0, "Vỡ/Nứt": 0, "Chưa phân loại": 0}
        else:
            error_types = {"Dị vật": 0, "Vỡ/Nứt": 0, "Thiếu viên": 0, "Chưa phân loại": 0}

        cur.execute("SELECT result, details FROM inspections WHERE is_ng = true AND product_name = %s", (current_model_name,))
        rows_ng = cur.fetchall()
        
        known_count = 0
        for r, d in rows_ng:
            # Gộp cả result và details để tìm từ khóa cho chính xác
            search_txt = f"{r} {d}".lower() if (r or d) else ""
            
            if any(k in search_txt for k in ["di vat", "dị vật", "di_vat", "vat the la"]):
                error_types["Dị vật"] += 1
                known_count += 1
            elif any(k in search_txt for k in ["vo", "vỡ", "nut", "nứt", "hong", "hỏng"]):
                error_types["Vỡ/Nứt"] += 1
                known_count += 1
            elif current_model == 2 and any(k in search_txt for k in ["thieu", "thiếu", "bi cat", "bị cắt"]):
                error_types["Thiếu viên"] += 1
                known_count += 1
        
        # Phần còn lại của counter (bao gồm cả các mẫu NG chưa được phân loại hoặc chưa có log chi tiết) sẽ vào mục "Chưa phân loại"
        error_types["Chưa phân loại"] = max(0, current_ng_total - known_count)

        # 4. Nhật ký gần nhất
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'inspections' AND column_name = 'image_url'")
        has_image_col = cur.fetchone() is not None
        
        query = "SELECT id, product_name, result, created_at, image_url FROM inspections ORDER BY created_at DESC LIMIT 10" if has_image_col else \
                "SELECT id, product_name, result, created_at, NULL as image_url FROM inspections ORDER BY created_at DESC LIMIT 10"
        
        cur.execute(query)
        recent_logs = [[str(r[0]), r[1], r[2], r[3].strftime('%d/%m/%Y %H:%M') if r[3] else "--/--/-- --:--", r[4]] for r in cur.fetchall()]

        # 5. Thống kê theo giờ
        def get_hourly_stats(product_name):
            cur.execute("""
                SELECT 
                    COUNT(i.id) as count
                FROM (
                    SELECT generate_series(
                        date_trunc('hour', NOW()) - interval '7 hours',
                        date_trunc('hour', NOW()),
                        interval '1 hour'
                    ) as hour
                ) h
                LEFT JOIN inspections i ON date_trunc('hour', i.created_at) = h.hour AND i.product_name = %s
                GROUP BY h.hour
                ORDER BY h.hour
            """, (product_name,))
            return [r[0] for r in cur.fetchall()]

        cur.execute("""
            SELECT to_char(hour, 'HH24') || 'h' 
            FROM generate_series(
                date_trunc('hour', NOW()) - interval '7 hours',
                date_trunc('hour', NOW()),
                interval '1 hour'
            ) as hour
        """)
        hourly_labels = [r[0] for r in cur.fetchall()]
        
        vien_hourly = get_hourly_stats("Viên rời")
        vi_hourly = get_hourly_stats("Vỉ thuốc")
        hourly_data = vien_hourly if current_model == 1 else vi_hourly

        cur.close()
        conn.close()

        return jsonify({
            "total": vien_total + vi_total, 
            "ok": ss_vien_ok + ss_vi_ok, 
            "ng": ss_vien_ng + ss_vi_ng,
            "total_vien": vien_total,
            "total_vi": vi_total,
            "vien_stats": {"total": vien_total, "ok": ss_vien_ok, "ng": ss_vien_ng, "hourly": vien_hourly},
            "vi_stats": {"total": vi_total, "ok": ss_vi_ok, "ng": ss_vi_ng, "hourly": vi_hourly},
            "status": "RUNNING" if machine_running else "STOPPED",
            "plc_connected": plc_connected,
            "cam_connected": cam_online,
            "current_model": current_model_name,
            "current_model_id": current_model,
            "last_sync": last_update,
            "recent_logs": recent_logs,
            "error_types": error_types,
            "hourly_labels": hourly_labels,
            "hourly_data": hourly_data
        })

    except Exception as e:
        if 'conn' in locals() and conn:
            conn.close()
        print(f"API Error: {e}")
        return jsonify({"status": "error", "message": str(e)})


@app.route('/api/set_model/<int:model_id>')
@app.route('/set_model/<int:model_id>')
def set_model(model_id):
    if not DB_URL:
        return jsonify({"status": "error", "message": "Chưa cấu hình SUPABASE_URL"})
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SET TIME ZONE 'Asia/Ho_Chi_Minh';")
        cur.execute("UPDATE system_status SET current_model_id = %s WHERE id = 1", (model_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "success", "message": f"Đã cập nhật Model ID = {model_id}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/images')
@app.route('/images')
def get_images():
    return jsonify([])

if __name__ == "__main__":
    app.run(debug=True)

