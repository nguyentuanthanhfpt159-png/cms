from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/api/stats')
def stats():
    return jsonify({"total": 150, "ok": 138, "ng": 12, "status": "RUNNING", "plc_connected": True, "cam_connected": True, "current_model": 1, "last_sync": "15:30:00", "recent_logs": [], "error_types": {"Dị vật": 3, "Vỡ": 5, "Thiếu viên": 2}, "hourly_data": [12, 18, 25, 30, 42, 38, 50, 45], "hourly_labels": ['1h','2h','3h','4h','5h','6h','7h','8h']})
