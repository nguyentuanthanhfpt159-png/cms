import cv2
import numpy as np
import snap7
from snap7.util import set_real, set_dint, set_bool, get_bool, get_real, get_int
import time
import math
import os
import threading
import json
import torch
import sys
import csv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Kết nối Cloud Supabase (Non-blocking async)
try:
    import psycopg2
    import requests
    from dotenv import load_dotenv
    load_dotenv(r"d:\Eruka\minorepo\.env")
    SUPABASE_DB_URL = os.getenv("SUPABASE_URL")
    SUPABASE_API_URL = os.getenv("SUPABASE_API_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
except Exception:
    psycopg2 = None
    requests = None
    SUPABASE_DB_URL = None
    SUPABASE_API_URL = None
    SUPABASE_KEY = None

LOCAL_CAPTURE_DIR = r"d:\Eruka\minorepo\captured_medicine"

def push_inspection_async(product_name, result, is_ng, details="", crop_frame=None):
    """
    Tự động lưu ảnh cắt từ Camera AI và upload bất đồng bộ lên Supabase Storage.
    Chạy 100% trên luồng ngầm (daemon thread), không làm trễ chu kỳ bám đuổi của Robot.
    """
    def _worker():
        image_url = None
        # 1. Xử lý lưu ảnh cục bộ và đẩy lên Supabase Storage
        if crop_frame is not None and getattr(crop_frame, 'size', 0) > 0:
            try:
                ts_str = time.strftime("%Y%m%d_%H%M%S")
                ms_str = f"{int(time.time() * 1000) % 1000:03d}"
                file_name = f"pill_{ts_str}_{ms_str}.jpg"

                sub_folder = "NG_LOI/GOI_THUOC" if is_ng else "OK_DAT/GOI_THUOC"
                local_dir = os.path.join(LOCAL_CAPTURE_DIR, sub_folder)
                os.makedirs(local_dir, exist_ok=True)
                local_file_path = os.path.join(local_dir, file_name)

                ret, buf = cv2.imencode('.jpg', crop_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    img_bytes = buf.tobytes()
                    with open(local_file_path, 'wb') as f_out:
                        f_out.write(img_bytes)

                    if SUPABASE_API_URL and SUPABASE_KEY and requests:
                        upload_url = f"{SUPABASE_API_URL}/storage/v1/object/inspection-images/{file_name}"
                        headers = {
                            'Authorization': f'Bearer {SUPABASE_KEY}',
                            'apikey': SUPABASE_KEY,
                            'Content-Type': 'image/jpeg'
                        }
                        r_up = requests.post(upload_url, data=img_bytes, headers=headers, timeout=5)
                        if r_up.status_code in [200, 201]:
                            image_url = f"{SUPABASE_API_URL}/storage/v1/object/public/inspection-images/{file_name}"
                            print(f"☁️ [CAMERA -> SUPABASE] Đã upload ảnh lỗi mới: {file_name}")
                        else:
                            print(f"⚠️ [SUPABASE STORAGE] HTTP {r_up.status_code}: {r_up.text[:100]}")
            except Exception as ex_img:
                print(f"⚠️ Lỗi lưu/upload ảnh camera: {ex_img}")

        # 2. Ghi bản ghi vào bảng inspections trên Supabase
        if not SUPABASE_DB_URL or not psycopg2:
            return
        try:
            conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=3)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO inspections (product_name, result, is_ng, details, image_url, created_at) VALUES (%s, %s, %s, %s, %s, NOW())",
                (product_name, result, is_ng, details, image_url)
            )
            conn.commit()
            cur.close()
            conn.close()
            print(f"📊 [SUPABASE DB] Đã lưu kết quả kiểm tra: {product_name} | Lỗi: {is_ng}")
        except Exception as ex_db:
            print(f"⚠️ Lỗi ghi Supabase DB: {ex_db}")

    threading.Thread(target=_worker, daemon=True).start()


def push_system_status_async(plc_ok, cam_ok, is_running, model_id):
    def _worker():
        if not SUPABASE_DB_URL or not psycopg2:
            return
        try:
            conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=3)
            cur = conn.cursor()
            cur.execute(
                "UPDATE system_status SET plc_online=%s, cam_online=%s, machine_running=%s, current_model_id=%s, last_update=NOW() WHERE id=1",
                (plc_ok, cam_ok, is_running, model_id)
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

# File lưu dữ liệu thực nghiệm tự động để làm biểu đồ báo cáo
EXP_CSV_PATH = r"d:\Eruka\Ket_qua_thuc_nghiem.csv"
exp_counter = 0

def init_experiment_csv():
    global exp_counter
    if not os.path.exists(EXP_CSV_PATH):
        with open(EXP_CSV_PATH, mode='w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                "STT", "Thời Gian", "Mã Gói", "Nhãn AI Nhận Diện", 
                "Độ Tin Cậy (%)", "Tọa Độ X (mm)", "Tọa Độ Y (mm)", 
                "Kết Quả Phân Loại", "Hành Động Hệ Thống"
            ])
        exp_counter = 0
    else:
        try:
            with open(EXP_CSV_PATH, mode='r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                rows = list(reader)
                exp_counter = max(0, len(rows) - 1)
        except Exception:
            exp_counter = 0
    print(f"📊 [THỰC NGHIỆM] File kết quả: {EXP_CSV_PATH} (Đã có {exp_counter} mẫu)")

def log_experiment_result(item_id, class_name, conf_val, x_mm, y_mm, is_ng):
    global exp_counter
    exp_counter += 1
    t_str = time.strftime("%H:%M:%S")
    conf_pct = f"{int(conf_val * 100)}%"
    res_label = "NG (LỖI)" if is_ng else "OK (ĐẠT)"
    action_label = "ROBOT GẮP VÀO KHAY NG" if is_ng else "CHO TRÔI QUA (ĐẠT)"

    try:
        with open(EXP_CSV_PATH, mode='a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                exp_counter, t_str, f"#{item_id}", class_name, 
                conf_pct, f"{x_mm:.1f}", f"{y_mm:.1f}", 
                res_label, action_label
            ])
        print(f"📝 [THỰC NGHIỆM] Đã ghi nhận Mẫu #{exp_counter}: {class_name.upper()} ({conf_pct}) tại X={x_mm:.1f}mm -> {res_label}")
    except Exception as e:
        print(f"⚠️ Lỗi ghi file thực nghiệm: {e}")


# Kiểm tra thư viện PyPylon và Ultralytics
PYPYLON_AVAILABLE = False
try:
    from pypylon import pylon
    PYPYLON_AVAILABLE = True
except ImportError:
    pass

try:
    from ultralytics import YOLO
except ImportError:
    pass

# =========================================================================
# 1. CẤU HÌNH HỆ THỐNG PHÂN LOẠI THUỐC & PLC S7-1200 (DB16 & DB30 FIFO)
# =========================================================================
PLC_IP = '192.168.0.10'       
DB_DELTA_DATA  = 16           # DB16: Delta_data (Dữ liệu điều khiển trực tiếp Robot)
DB_PYTHON_FIFO = 30           # DB30: Data_Python (Hàng đợi FIFO Tracking 200Hz trong OB30)

# --- ĐỊA CHỈ TRUY CẬP DB30 (Data_Python - FIFO Tracking 200Hz trong PLC) ---
ADDR_DB30_TRIGGER_BYTE  = 0    # DB30.DBX0.0 (Bool): New_Item_Trigger (Kích nạp gói mới vào Queue)
ADDR_DB30_ITEM_ID       = 2    # DB30.DBD2   (DInt): Item_ID
ADDR_DB30_ITEM_X        = 6    # DB30.DBD6   (Real): Item_X (Tọa độ X mm)
ADDR_DB30_ITEM_Y        = 10   # DB30.DBD10  (Real): Item_Y (Khoảng cách âm từ vạch vàng tới Robot)
ADDR_DB30_CONVEYOR_SPD  = 14   # DB30.DBD14  (Real): Conveyor_Speed (mm/s)
ADDR_DB30_ROBOT_BUSY    = 158  # DB30.DBX158.0 (Bool): Robot_Busy (Cờ bận từ FC4 Fast PickPlace)
ADDR_DB30_STEP_STATE    = 160  # DB30.DBW160 (Int): Step_State (0: Chờ, 1: Hút, 2: Nhả, 3: Về Standby)

# --- ĐỊA CHỈ TRUY CẬP DB16 (Delta_data - Giám sát & Bổ trợ) ---
ADDR_DB16_TARGET_X      = 0    # DBD0  (Real): Target_X_mm
ADDR_DB16_TARGET_Y      = 4    # DBD4  (Real): Target_Y_mm
ADDR_DB16_TARGET_Z      = 8    # DBD8  (Real): Target_Z_mm
ADDR_DB16_ROBOT_SPEED   = 12   # DBD12 (Real): Robot_Speed_mm_s
ADDR_DB16_CMD_START_PICK= 28   # DBX28.1 (Bool): Cmd_Start_Pick
ADDR_DB16_CMD_VACUUM    = 42   # DBX42.0 (Bool): Cmd_Vacuum_Pump
ADDR_DB16_ROBOT_BUSY    = 42   # DBX42.1 (Bool): Status_Robot_Busy

# =========================================================================
# 2. CẤU HÌNH AI MODEL PHÂN LOẠI (GÓI THUỐC / VỈ THUỐC / VIÊN RỜI)
# =========================================================================
MODEL_MODE = "GOI_THUOC"

MODEL_CONFIGS = {
    "GOI_THUOC": {
        "name": "Gói Thuốc (Mới)",
        "path": r"d:\Eruka\best.pt",
        "fallback_path": r"d:\Eruka\minorepo\best_thuoc_m.pt",
        "allowed_classes": ["binh thuong", "rach"],
        "ok_classes": ["binh thuong"],
        "ng_classes": ["rach"]
    },
    "VITHUOC": {
        "name": "Vỉ Thuốc",
        "path": r"d:\Eruka\minorepo\vithuoc.pt",
        "fallback_path": r"d:\Eruka\minorepo\vithuoc.pt",
        "allowed_classes": ["vi_thuoc", "thieu_vien", "nut_vo", "di_vat"],
        "ok_classes": ["vi_thuoc"],
        "ng_classes": ["thieu_vien", "nut_vo", "di_vat"]
    },
    "VIENROI": {
        "name": "Viên Rời",
        "path": r"d:\Eruka\minorepo\vienroi.pt",
        "fallback_path": r"d:\Eruka\minorepo\vienroi.pt",
        "allowed_classes": ["vienok", "vo", "di vat"],
        "ok_classes": ["vienok"],
        "ng_classes": ["vo", "di vat"]
    }
}

active_cfg = MODEL_CONFIGS.get(MODEL_MODE, MODEL_CONFIGS["GOI_THUOC"])
AI_MODEL_PATH = active_cfg["path"] if os.path.exists(active_cfg["path"]) else active_cfg["fallback_path"]
ALLOWED_CLASSES = active_cfg["allowed_classes"]
OK_CLASSES = active_cfg["ok_classes"]
NG_CLASSES = active_cfg["ng_classes"]
CONF_THRESHOLD = 0.40

# =========================================================================
# 3. THÔNG SỐ CƠ KHÍ & QUY ĐỔI CAMERA 
# =========================================================================
Z_TOP_HOME = -250.0  
Z_STANDBY  = -360.0  # Vị trí làm việc / chờ đón đầu
Z_BOTTOM   = -400.0  # Vị trí gắp vật chạm mặt băng tải  

# Khoảng cách thực tế từ Vạch Vàng tới Tâm Robot là 130mm:
DISTANCE_TRIGGER_TO_ROBOT = 160
# Tỷ lệ thực tế mm/pixel đo đạc chuẩn xác từ Camera (Gói thuốc 75mm x 51mm tương ứng 563px x 390px):
PIXEL_TO_MM_X = 0.133               # 75.0mm / 563px = 0.1332 mm/px
PIXEL_TO_MM_Y = 0.131               # 51.0mm / 390px = 0.1308 mm/px
FOV_HEIGHT_MM = 90.0
TRIGGER_LINE_RATIO = 0.25          # Vạch vàng ở 25% phía trên khung hình
TRIGGER_LINE_OFFSET_MM = 0.0
CENTER_X_OFFSET_MM = 0.0           # Tâm chính giữa 0.0mm
X_CALIB_OFFSET = -20.0             # Bù kéo đầu hút sang TRÁI -20.0mm để triệt tiêu độ lệch cơ khí 20mm sang phải
V_CONVEYOR = 50.0              # Vận tốc băng tải (50.0 mm/s)

# =========================================================================
# 3.1. THUẬT TOÁN ÁNH XẠ PHỐI CẢNH HOMOGRAPHY 3x3 (CT 3.79 - 3.84)
# =========================================================================
OFFSET_X = 0.0                      # Bù sai số lắp đặt cơ khí trục X (CT 3.83)
OFFSET_Y = 0.0                      # Bù sai số lắp đặt cơ khí trục Y (CT 3.84)

def get_homography_matrix(center_x, trigger_y):
    """
    Khởi tạo ma trận Homography H (3x3) ánh xạ không gian ảnh sang tọa độ Robot (CT 3.79)
    H = [[h11, h12, h13],
         [h21, h22, h23],
         [h31, h32, h33]]
    """
    h11 = float(PIXEL_TO_MM_X)
    h12 = 0.0
    h13 = - (float(center_x) * float(PIXEL_TO_MM_X)) + float(X_CALIB_OFFSET)

    h21 = 0.0
    h22 = - float(PIXEL_TO_MM_Y)
    h23 = - float(DISTANCE_TRIGGER_TO_ROBOT) + (float(trigger_y) * float(PIXEL_TO_MM_Y))

    h31 = 0.0
    h32 = 0.0
    h33 = 1.0

    return np.array([
        [h11, h12, h13],
        [h21, h22, h23],
        [h31, h32, h33]
    ], dtype=np.float64)

def pixel_to_robot_homography(cx_px, cy_px, center_x, trigger_y):
    """
    Chuyển đổi tọa độ Pixel (cx_px, cy_px) -> Tọa độ thực Robot (X_PLC, Y_PLC)
    Tuân thủ đúng hệ phương trình ma trận Homography (3.79 - 3.84)
    """
    H = get_homography_matrix(center_x, trigger_y)
    
    # 1. Tọa độ đồng nhất dạng vector 3x1 (CT 3.79)
    p_img = np.array([float(cx_px), float(cy_px), 1.0], dtype=np.float64)
    
    # 2. Phép nhân ma trận H * p_img (CT 3.79)
    p_temp = np.dot(H, p_img)
    X_tmp, Y_tmp, W = p_temp[0], p_temp[1], p_temp[2]
    
    if abs(W) < 1e-6:
        W = 1.0
        
    # 3. Chuẩn hóa khử méo phối cảnh bằng cách chia cho W (CT 3.80, 3.81)
    X_LT = X_tmp / W
    Y_LT = Y_tmp / W
    
    # 4. Bù sai số cơ khí lắp đặt (CT 3.83, 3.84)
    X_PLC = X_LT + OFFSET_X
    Y_PLC = Y_LT + OFFSET_Y
    
    return X_PLC, Y_PLC

def apply_static_crop(frame):
    h, w = frame.shape[:2]
    if w <= 1200:
        return frame, 0, 0
    x1, x2 = int(w * 0.330), int(w * 0.650)
    y1, y2 = int(h * 0.040), int(h * 0.940)
    return frame[y1:y2, x1:x2], x1, y1

# =========================================================================
# 4. BIẾN TOÀN CỤC & ĐỒNG BỘ ĐA LUỒNG
# =========================================================================
queue_lock = threading.Lock()
frame_lock = threading.Lock()

shared_data = {
    'tracked_objects': {},
    'next_obj_id': 1,
    'object_queue': [],
    'new_items_to_plc': [],         # Hàng đợi gửi sang DB30 của PLC
    'count_ok': 0,
    'count_ng': 0,
    'robot_state': "READY / STANDBY",
    'is_busy': False,
    'is_running': True,
    'latest_frame': None,
    'latest_crop_box': (0, 0, 0, 0),
    'fps_ai': 0.0,
    'fps_tracking': 0.0,
    'CENTER_X': 0,
    'H_FULL': 0,
    'W_FULL': 0,
    'TRIGGER_LINE_Y': 0,
    'model_mode': MODEL_MODE,
    'current_model_id': 1,
    'model_switch_requested': None
}

# =========================================================================
# 5. LUỒNG 1: CAMERA & AI INFERENCE WORKER (GPU RTX 3050)
# =========================================================================
def ai_vision_worker(camera, cam_mode, model, converter=None):
    global shared_data, DISTANCE_TRIGGER_TO_ROBOT, PIXEL_TO_MM_X, PIXEL_TO_MM_Y, CENTER_X_OFFSET_MM, X_CALIB_OFFSET, V_CONVEYOR
    global ALLOWED_CLASSES, OK_CLASSES, NG_CLASSES, MODEL_MODE, active_cfg
    print("🚀 [THREAD 1] Luồng AI Vision đã khởi chạy...")
    
    device_id = 0 if torch.cuda.is_available() else "cpu"
    print(f"🔥 [THREAD 1] Thiết bị suy luận AI: {device_id} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")

    fps_calc_time = time.time()
    frame_counter = 0

    while shared_data['is_running']:
        # Kiểm tra yêu cầu chuyển đổi Model (Hot-reload từ Dashboard)
        if shared_data.get('model_switch_requested'):
            target_cfg_key = shared_data['model_switch_requested']
            shared_data['model_switch_requested'] = None
            if target_cfg_key in MODEL_CONFIGS:
                try:
                    cfg = MODEL_CONFIGS[target_cfg_key]
                    target_path = cfg["path"] if os.path.exists(cfg["path"]) else cfg["fallback_path"]
                    print(f"\n🔄 [AI VISION] ĐANG TẢI MODEL MỚI: {cfg['name']} ({target_path})...")
                    model = YOLO(target_path)
                    active_cfg = cfg
                    ALLOWED_CLASSES = cfg["allowed_classes"]
                    OK_CLASSES = cfg["ok_classes"]
                    NG_CLASSES = cfg["ng_classes"]
                    MODEL_MODE = target_cfg_key
                    shared_data['model_mode'] = target_cfg_key
                    print(f"✅ [AI VISION] ĐÃ KÍCH HOẠT THÀNH CÔNG SANG MODEL: {cfg['name']}!\n")
                except Exception as e:
                    print(f"⚠️ Lỗi chuyển đổi Model AI: {e}")
        full_frame = None
        if cam_mode == "MVS":
            ret, full_frame = camera.get_frame()
            if not ret or full_frame is None:
                time.sleep(0.005)
                continue
        elif cam_mode == "BASLER" and PYPYLON_AVAILABLE and camera is not None:
            if not camera.IsGrabbing(): break
            try:
                grabResult = camera.RetrieveResult(1000, pylon.TimeoutHandling_ThrowException)
                if grabResult.GrabSucceeded():
                    full_frame = converter.Convert(grabResult).GetArray()
                grabResult.Release()
            except Exception:
                time.sleep(0.01)
                continue
        elif cam_mode == "WEBCAM":
            ret, full_frame = camera.read()
            if not ret or full_frame is None:
                time.sleep(0.01)
                continue

        if full_frame is None:
            continue

        H_FULL, W_FULL = full_frame.shape[:2]
        CENTER_X = int(W_FULL * 0.50 + (CENTER_X_OFFSET_MM / PIXEL_TO_MM_X))
        TRIGGER_LINE_Y = int(H_FULL * TRIGGER_LINE_RATIO - (TRIGGER_LINE_OFFSET_MM / PIXEL_TO_MM_Y))

        cropped_frame, crop_x1, crop_y1 = apply_static_crop(full_frame)
        h_crop, w_crop = cropped_frame.shape[:2]

        results = model.predict(source=cropped_frame, conf=CONF_THRESHOLD, device=device_id, verbose=False)
        detected_items = []

        if hasattr(results[0], 'obb') and results[0].obb is not None and len(results[0].obb) > 0:
            for obb in results[0].obb:
                cx_c, cy_c, w_c, h_c = float(obb.xywhr[0][0]), float(obb.xywhr[0][1]), float(obb.xywhr[0][2]), float(obb.xywhr[0][3])
                cls_id = int(obb.cls[0])
                conf_val = float(obb.conf[0])
                detected_items.append((cx_c + crop_x1, cy_c + crop_y1, w_c, h_c, model.names[cls_id], conf_val))
        elif hasattr(results[0], 'boxes') and results[0].boxes is not None and len(results[0].boxes) > 0:
            for box in results[0].boxes:
                cx_c, cy_c, w_c, h_c = float(box.xywh[0][0]), float(box.xywh[0][1]), float(box.xywh[0][2]), float(box.xywh[0][3])
                cls_id = int(box.cls[0])
                conf_val = float(box.conf[0])
                detected_items.append((cx_c + crop_x1, cy_c + crop_y1, w_c, h_c, model.names[cls_id], conf_val))

        # Gợi ý tự động tính tỷ lệ Pixel -> mm chuẩn xác cho gói thuốc thực tế (Rộng 51mm, Dài 75mm)
        if len(detected_items) > 0:
            for item in detected_items:
                _, _, w_item, h_item, c_name, conf_i = item
                if conf_i > 0.60:
                    suggest_px_x = 51.0 / w_item if w_item > 0 else 0.240
                    suggest_px_y = 75.0 / h_item if h_item > 0 else 0.280
                    # In 1 dòng kích thước rõ ràng
                    # print(f"📏 [GÓI THUỐC]: W = {w_item:.1f} px, H = {h_item:.1f} px => PIXEL_TO_MM_X = {suggest_px_x:.4f}, PIXEL_TO_MM_Y = {suggest_px_y:.4f}")

        now_t = time.time()
        matched_ids = set()

        with queue_lock:
            for cx_full, cy_full, w_full_px, h_full_px, class_name, conf_val in detected_items:
                if class_name not in ALLOWED_CLASSES:
                    continue

                is_curr_ng = (class_name in NG_CLASSES)
                is_curr_ok = (class_name in OK_CLASSES)
                box_w = w_full_px if w_full_px > 80 else 180
                box_h = h_full_px if h_full_px > 80 else 260
                pct_str = f"{int(conf_val * 100)}%"

                best_match_id = None
                min_dist = 9999.0
                for obj_id, obj in shared_data['tracked_objects'].items():
                    dist = math.hypot(obj['cx'] - cx_full, obj['cy'] - cy_full)
                    if dist < 140.0 and dist < min_dist:
                        min_dist = dist
                        best_match_id = obj_id

                if best_match_id is not None:
                    matched_ids.add(best_match_id)
                    obj = shared_data['tracked_objects'][best_match_id]
                    prev_cy = obj['cy']
                    obj['cx'] = cx_full
                    obj['cy'] = cy_full
                    obj['w_px'] = box_w
                    obj['h_px'] = box_h
                    obj['conf'] = conf_val
                    obj['last_seen'] = now_t
                    
                    if not obj['is_triggered']:
                        if is_curr_ng:
                            obj['is_ng'] = True
                            obj['class_name'] = class_name
                            obj['status_label'] = f"NG ({class_name.upper()} {pct_str})"
                        elif is_curr_ok and not obj.get('is_ng', False):
                            obj['class_name'] = class_name
                            obj['status_label'] = f"OK ({class_name.upper()} {pct_str})"

                        # Sự kiện qua vạch vàng duy nhất 1 lần -> Nạp vào DB30 FIFO của PLC
                        if prev_cy >= TRIGGER_LINE_Y and cy_full < TRIGGER_LINE_Y:
                            obj['is_triggered'] = True
                            
                            # 👉 ÁP DỤNG THUẬT TOÁN HOMOGRAPHY 3x3 (CT 3.79 - 3.84)
                            x_calc, y_calc = pixel_to_robot_homography(cx_full, cy_full, CENTER_X, TRIGGER_LINE_Y)
                            x_robot = max(-75.0, min(75.0, x_calc))
                            y_start = y_calc
                            obj['x_robot'] = x_robot

                            # Cắt ảnh gói thuốc từ full_frame của camera
                            crop_pkg = None
                            try:
                                h_frame, w_frame = full_frame.shape[:2]
                                pad_x = int(box_w * 0.15) + 10
                                pad_y = int(box_h * 0.15) + 10
                                x1 = max(0, int(cx_full - box_w / 2 - pad_x))
                                y1 = max(0, int(cy_full - box_h / 2 - pad_y))
                                x2 = min(w_frame, int(cx_full + box_w / 2 + pad_x))
                                y2 = min(h_frame, int(cy_full + box_h / 2 + pad_y))
                                if x2 > x1 and y2 > y1:
                                    crop_pkg = full_frame[y1:y2, x1:x2].copy()
                            except Exception:
                                crop_pkg = None

                            if obj.get('is_ng', False):
                                obj['status_label'] = f"CHOT: NG ({obj['class_name']} {pct_str})"
                                shared_data['count_ng'] += 1
                                item_info = {
                                    'id': best_match_id,
                                    'x_robot': x_robot,
                                    'y_rel_robot': y_start,
                                    'class_name': obj['class_name'],
                                    'is_ok': False,
                                    'w_px': box_w,
                                    'h_px': box_h,
                                    'status_label': obj['status_label']
                                }
                                shared_data['object_queue'].append(item_info)
                                shared_data['new_items_to_plc'].append(item_info) # Nạp vào DB30
                                log_experiment_result(best_match_id, obj['class_name'], conf_val, x_robot, y_start, True)
                                push_inspection_async(f"{active_cfg.get('name', 'Thuốc')} #{best_match_id} ({obj['class_name']})", "NG (LỖI)", True, f"X={x_robot:.1f}mm, conf={conf_val*100:.0f}%", crop_frame=crop_pkg)
                                print(f"🚨 [VẠCH VÀNG] CHỐT GÓI THUỐC LỖI #{best_match_id} -> Nạp DB30: X={x_robot:.1f}mm, Y_start={y_start:.1f}mm")
                            else:
                                obj['status_label'] = f"CHOT: OK ({pct_str})"
                                shared_data['count_ok'] += 1
                                log_experiment_result(best_match_id, obj['class_name'], conf_val, x_robot, y_start, False)
                                push_inspection_async(f"{active_cfg.get('name', 'Thuốc')} #{best_match_id} ({obj['class_name']})", "OK (ĐẠT)", False, f"X={x_robot:.1f}mm, conf={conf_val*100:.0f}%", crop_frame=crop_pkg)
                                print(f"✅ [VẠCH VÀNG] CHỐT GÓI THUỐC ĐẠT (OK) tại X={x_robot:.1f}mm -> Cho trôi qua.")

                else:
                    if cy_full >= TRIGGER_LINE_Y - 20:
                        new_id = shared_data['next_obj_id']
                        shared_data['next_obj_id'] += 1
                        shared_data['tracked_objects'][new_id] = {
                            'id': new_id,
                            'cx': cx_full,
                            'cy': cy_full,
                            'w_px': box_w,
                            'h_px': box_h,
                            'class_name': class_name,
                            'conf': conf_val,
                            'is_ng': is_curr_ng,
                            'is_triggered': False,
                            'last_seen': now_t,
                            'status_label': f"CHECK: {class_name.upper()} ({pct_str})"
                        }

            for obj_id, obj in list(shared_data['tracked_objects'].items()):
                if obj_id not in matched_ids:
                    if obj.get('is_triggered', False):
                        obj['cy'] -= (V_CONVEYOR / PIXEL_TO_MM_Y) * (now_t - obj['last_seen'])
                        obj['last_seen'] = now_t
                    else:
                        if now_t - obj['last_seen'] > 0.40:
                            del shared_data['tracked_objects'][obj_id]

            for obj_id, obj in list(shared_data['tracked_objects'].items()):
                if obj['cy'] < 0 or (now_t - obj['last_seen'] > 3.0):
                    if obj_id in shared_data['tracked_objects']:
                        del shared_data['tracked_objects'][obj_id]

        with frame_lock:
            shared_data['latest_frame'] = full_frame.copy()
            shared_data['latest_crop_box'] = (crop_x1, crop_y1, crop_x1 + w_crop, crop_y1 + h_crop)
            shared_data['CENTER_X'] = CENTER_X
            shared_data['H_FULL'] = H_FULL
            shared_data['W_FULL'] = W_FULL
            shared_data['TRIGGER_LINE_Y'] = TRIGGER_LINE_Y

        frame_counter += 1
        if time.time() - fps_calc_time >= 1.0:
            shared_data['fps_ai'] = frame_counter / (time.time() - fps_calc_time)
            frame_counter = 0
            fps_calc_time = time.time()

# =========================================================================
# 6. LUỒNG 2: GỬI GÓI MỚI VÀO DB30 FIFO CỦA PLC & GIÁM SÁT REAL-TIME
# =========================================================================
def tracking_plc_master(client, plc_connected):
    global shared_data, V_CONVEYOR
    print("⚡ [THREAD 2] Luồng Truyền thông DB30 FIFO & DB16 của PLC đã khởi chạy...")

    def send_item_to_db30(item_id, x, y):
        if not plc_connected or client is None: return
        try:
            # Ghi vào DB30.DBX0.0 (Trigger), DBD2 (ID), DBD6 (X), DBD10 (Y), DBD14 (Speed)
            buf_db = bytearray(18)
            set_bool(buf_db, 0, 0, True)             # DB30.DBX0.0 = True (Bật xung kích nạp)
            set_dint(buf_db, 2, int(item_id))        # DB30.DBD2 = Item_ID
            set_real(buf_db, 6, float(x))            # DB30.DBD6 = Item_X (mm)
            set_real(buf_db, 10, float(y))           # DB30.DBD10 = Item_Y (mm)
            set_real(buf_db, 14, float(V_CONVEYOR))  # DB30.DBD14 = Conveyor_Speed (mm/s)
            client.db_write(DB_PYTHON_FIFO, 0, buf_db)
            
            time.sleep(0.020)
            
            buf_trig_off = bytearray(1)
            set_bool(buf_trig_off, 0, 0, False)
            client.db_write(DB_PYTHON_FIFO, 0, buf_trig_off)
            
            print(f"⚡ [PLC DB30 FIFO] ĐÃ NẠP GÓI #{item_id} (X={x:.1f}mm, Y={y:.1f}mm) VÀO HÀNG ĐỢI 10 PHẦN TỬ CỦA PLC!")
        except Exception as err:
            print(f"⚠️ Lỗi nạp dữ liệu sang DB30 của PLC: {err}")

    cycle_counter = 0
    fps_calc_time = time.time()

    while shared_data['is_running']:
        # 1. Nạp các gói thuốc lỗi mới vào hàng đợi DB30 của PLC
        with queue_lock:
            items_to_send = list(shared_data['new_items_to_plc'])
            shared_data['new_items_to_plc'].clear()

        for item_push in items_to_send:
            send_item_to_db30(item_push['id'], item_push['x_robot'], item_push['y_rel_robot'])

        # 2. Đọc trạng thái Bận / Rảnh & Nhịp bước từ PLC
        is_busy = False
        step_state = 0
        if plc_connected and client is not None:
            try:
                # Đọc DB30.DBX158.0 (Data_Python.Robot_Busy)
                data_busy_db30 = client.db_read(DB_PYTHON_FIFO, ADDR_DB30_ROBOT_BUSY, 1)
                is_busy_db30 = get_bool(data_busy_db30, 0, 0)
                
                # Đọc DB16.DBX42.1 (Delta_data.Status_Robot_Busy)
                data_busy_db16 = client.db_read(DB_DELTA_DATA, ADDR_DB16_ROBOT_BUSY, 1)
                is_busy_db16 = get_bool(data_busy_db16, 0, 1)
                
                # Đọc Step_State từ DB30.DBW160
                data_step = client.db_read(DB_PYTHON_FIFO, ADDR_DB30_STEP_STATE, 2)
                step_state = int(data_step[0] << 8 | data_step[1])
                
                is_busy = is_busy_db30 or is_busy_db16
            except Exception:
                pass

        shared_data['is_busy'] = is_busy
        if is_busy:
            step_names = {
                1: "BƯỚC 1: TIẾP CẬN TRÊN CAO",
                2: "BƯỚC 2: CẮM THẲNG HÚT ĐÁY",
                3: "BƯỚC 3: NHẤC THẲNG LÊN CAO",
                4: "BƯỚC 4: BAY SANG KHAY NG XẢ",
                5: "BƯỚC 5: THU TAY VỀ STANDBY"
            }
            shared_data['robot_state'] = f"BUSY ({step_names.get(step_state, 'PICKING')})"
        else:
            shared_data['robot_state'] = "READY / STANDBY"

        cycle_counter += 1
        if time.time() - fps_calc_time >= 1.0:
            shared_data['fps_tracking'] = cycle_counter / (time.time() - fps_calc_time)
            cycle_counter = 0
            fps_calc_time = time.time()

        time.sleep(0.010)

# =========================================================================
# 6.1. LUỒNG 3: ĐỌC LỆNH ĐỔI MODEL TỪ DASHBOARD & ĐỒNG BỘ SUPABASE CLOUD
# =========================================================================
def command_and_cloud_sync_worker(plc_connected, cam_mode):
    global shared_data
    CMD_FILE = r"d:\Eruka\command.json"
    last_cmd_time = 0
    last_sync_time = 0

    mode_id_map = {
        1: "GOI_THUOC",
        2: "VITHUOC",
        3: "VIENROI"
    }
    id_mode_map = {v: k for k, v in mode_id_map.items()}

    while shared_data['is_running']:
        try:
            # 1. Đọc file command.json từ web_dashboard (nếu có lệnh đổi Model)
            if os.path.exists(CMD_FILE):
                try:
                    with open(CMD_FILE, "r", encoding="utf-8") as f:
                        cmd = json.load(f)
                    ts = cmd.get("timestamp", 0)
                    if ts > last_cmd_time:
                        last_cmd_time = ts
                        if cmd.get("cmd") == "set_model":
                            target_id = cmd.get("model_id", 1)
                            target_mode = cmd.get("model_code", mode_id_map.get(target_id, "GOI_THUOC"))
                            if target_mode != shared_data.get('model_mode'):
                                print(f"\n📥 [LỆNH DASHBOARD] Yêu cầu chuyển đổi sang Model #{target_id} ({target_mode})!")
                                shared_data['current_model_id'] = target_id
                                shared_data['model_switch_requested'] = target_mode
                except Exception:
                    pass

            # 2. Đồng bộ trạng thái PLC, Camera, Robot và Model lên Supabase Cloud mỗi 2.5 giây
            now_t = time.time()
            if now_t - last_sync_time >= 2.5:
                last_sync_time = now_t
                curr_mid = shared_data.get('current_model_id', id_mode_map.get(shared_data.get('model_mode'), 1))
                push_system_status_async(
                    plc_ok=plc_connected,
                    cam_ok=(cam_mode != "SYNTHETIC"),
                    is_running=shared_data['is_running'],
                    model_id=curr_mid
                )
        except Exception:
            pass
        time.sleep(0.5)

# =========================================================================
# 7. HÀM MAIN: KHỞI ĐỘNG HỆ THỐNG
# =========================================================================
def main():
    global shared_data, DISTANCE_TRIGGER_TO_ROBOT, CENTER_X_OFFSET_MM, X_CALIB_OFFSET, V_CONVEYOR, exp_counter

    init_experiment_csv()
    print("⏳ Đang kết nối PLC S7-1200...")
    client = snap7.client.Client()
    plc_connected = False
    try:
        client.connect(PLC_IP, 0, 1)
        plc_connected = True
        print(f"✅ Đã kết nối thành công PLC S7-1200 ({PLC_IP})!")
        
        # Reset DB30 và DB16 ban đầu
        try:
            # 1. Reset DB30.DBX0.0 (New_Item_Trigger = False)
            data_trig_rst = bytearray(1)
            set_bool(data_trig_rst, 0, 0, False)
            client.db_write(DB_PYTHON_FIFO, 0, data_trig_rst)

            # 2. Xóa sạch 10 phần tử trong Queue DB30 (từ byte 18 đến 157)
            buf_clear_queue = bytearray(140)
            client.db_write(DB_PYTHON_FIFO, 18, buf_clear_queue)

            # 3. Reset Robot_Busy và Step_State = 0
            buf_clear_state = bytearray(4)
            client.db_write(DB_PYTHON_FIFO, 158, buf_clear_state)

            # 4. Reset DB16.DBX28.1 & DB16.DBX42.0 & DB16.DBX42.1
            data_init = client.db_read(DB_DELTA_DATA, ADDR_DB16_CMD_START_PICK, 1)
            set_bool(data_init, 0, 1, False)
            client.db_write(DB_DELTA_DATA, ADDR_DB16_CMD_START_PICK, data_init)

            data_v = client.db_read(DB_DELTA_DATA, ADDR_DB16_CMD_VACUUM, 1)
            set_bool(data_v, 0, 0, False)
            client.db_write(DB_DELTA_DATA, ADDR_DB16_CMD_VACUUM, data_v)

            data_b = client.db_read(DB_DELTA_DATA, 42, 1)
            set_bool(data_b, 0, 1, False)
            client.db_write(DB_DELTA_DATA, 42, data_b)
            print("🧹 Đã Xóa sạch hàng đợi rác và Reset trạng thái DB30 & DB16 về 0 thành công!")
        except Exception as e:
            print(f"⚠️ Reset cờ PLC: {e}")

        # Kích Servo %M10.6
        try:
            m_data = client.mb_read(10, 2)
            axis_ready = get_bool(m_data, 0, 6)
            if not axis_ready:
                m_byte = client.mb_read(10, 1)
                set_bool(m_byte, 0, 6, True)
                client.mb_write(10, 1, m_byte)
            
            # 5. Đồng bộ ngay V_CONVEYOR vào DB30.DBD14 (Conveyor_Speed)
            buf_speed = bytearray(4)
            set_real(buf_speed, 0, float(V_CONVEYOR))
            client.db_write(DB_PYTHON_FIFO, 14, buf_speed)
            print(f"🚀 [TỐC ĐỘ] ĐÃ ĐỒNG BỘ VẬN TỐC {V_CONVEYOR:.1f} mm/s SANG PLC (%DB30.DBD14)!")

            buf_xyz = bytearray(12)
            set_real(buf_xyz, 0, 0.0)
            set_real(buf_xyz, 4, 0.0)
            set_real(buf_xyz, 8, float(Z_STANDBY))
            client.db_write(DB_DELTA_DATA, ADDR_DB16_TARGET_X, buf_xyz)
            print(f"📍 ĐÃ CÀI ĐẶT TỌA ĐỘ CHỜ (Z={Z_STANDBY}mm) CHO ROBOT!")
        except Exception as err:
            print(f"⚠️ Lỗi khởi tạo PLC: {err}")

    except Exception as e:
        plc_connected = False
        print(f"⚠️ Lỗi kết nối PLC: {e}")

    model_display_name = active_cfg.get("name", MODEL_MODE)
    print(f"⏳ Đang nạp Model AI [{model_display_name}]...")
    model = YOLO(AI_MODEL_PATH)
    print("✅ Đã nạp thành công Model AI!")

    # Khởi tạo Camera
    cam_mode = "SYNTHETIC"
    camera = None
    converter = None

    try:
        from mvs_camera import MvsCamera
        mvs = MvsCamera()
        if mvs.open():
            cam_mode = "MVS"
            camera = mvs
            print("✅ Đã kết nối thành công Camera công nghiệp Hikrobot MVS (192.168.0.100)!")
    except Exception as e:
        print(f"ℹ️ Hikrobot MVS: {e}")

    if cam_mode == "SYNTHETIC" and PYPYLON_AVAILABLE:
        try:
            tlFactory = pylon.TlFactory.GetInstance()
            devices = tlFactory.EnumerateDevices()
            if len(devices) > 0:
                cam = pylon.InstantCamera(tlFactory.CreateFirstDevice())
                cam.Open()
                cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                converter = pylon.ImageFormatConverter()
                converter.OutputPixelFormat = pylon.PixelType_BGR8packed
                converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
                cam_mode = "BASLER"
                camera = cam
                print("✅ Đã kết nối thành công Camera công nghiệp Basler qua PyPylon!")
        except Exception as e:
            print(f"ℹ️ Basler: {e}")

    if cam_mode == "SYNTHETIC":
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if cap.isOpened():
            cam_mode = "WEBCAM"
            camera = cap
            print("📷 Sử dụng Camera Webcam làm nguồn cấp video!")
        else:
            print("⚠️ Không tìm thấy Camera vật lý. Khởi chạy luồng giả lập (Synthetic Engine)!")

    t_vision = threading.Thread(target=ai_vision_worker, args=(camera, cam_mode, model, converter), daemon=True)
    t_tracking = threading.Thread(target=tracking_plc_master, args=(client, plc_connected), daemon=True)
    t_sync = threading.Thread(target=command_and_cloud_sync_worker, args=(plc_connected, cam_mode), daemon=True)

    t_vision.start()
    t_tracking.start()
    t_sync.start()

    print("🚀 HỆ THỐNG ĐÃ SẴN SÀNG CHẠY VỚI HÀNG ĐỢI DB30 FIFO CỦA PLC...")
    print("👉 Phím tắt điều chỉnh Realtime:")
    print("   • [ - / = ] : Giảm / Tăng khoảng cách tới Robot (DISTANCE_TRIGGER_TO_ROBOT)")
    print("   • [ [ / ] ] : Giảm / Tăng vận tốc băng tải (V_CONVEYOR)")
    print("   • [ , / . ] : Bù trục X sang Trái / sang Phải (X_CALIB_OFFSET)")
    print("   • [ T / Y ] : Test gắp lệch Trái (-35mm) / Phải (+35mm)")
    print("   • [ C ]     : Xóa sạch Log CSV và Reset bộ đếm")
    print("   • [ Q ]     : Thoát chương trình\n")

    while True:
        display_frame = None
        crop_info = None
        CENTER_X = 0
        H_FULL = 0
        W_FULL = 0
        TRIGGER_LINE_Y = 0

        with frame_lock:
            if shared_data['latest_frame'] is not None:
                display_frame = shared_data['latest_frame'].copy()
                crop_info = shared_data['latest_crop_box']
                CENTER_X = shared_data['CENTER_X']
                H_FULL = shared_data['H_FULL']
                W_FULL = shared_data['W_FULL']
                TRIGGER_LINE_Y = shared_data['TRIGGER_LINE_Y']

        if display_frame is None:
            time.sleep(0.01)
            continue

        cv2.putText(display_frame, "[VUNG TRUYEN TOA DO & DON DAU DB30 FIFO - DA KHOA NHAN]", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

        if 0 < TRIGGER_LINE_Y < H_FULL:
            cv2.line(display_frame, (0, TRIGGER_LINE_Y), (W_FULL, TRIGGER_LINE_Y), (0, 255, 255), 3)
            label_yellow = f"--- VACH CHOT KET QUA -> TAM ROBOT ({DISTANCE_TRIGGER_TO_ROBOT:.0f}mm) ---"
            cv2.putText(display_frame, label_yellow, (15, TRIGGER_LINE_Y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 255, 255), 2)
            cv2.putText(display_frame, f"[VUNG NHAN DIEN & KIEM TRA - {FOV_HEIGHT_MM:.0f}mm]", (15, TRIGGER_LINE_Y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 0), 2)

        with queue_lock:
            tracked_list = list(shared_data['tracked_objects'].values())
            current_queue = list(shared_data['object_queue'])
            c_ok = shared_data['count_ok']
            c_ng = shared_data['count_ng']
            r_state = shared_data['robot_state']
            fps_ai = shared_data['fps_ai']
            fps_tr = shared_data['fps_tracking']

        for obj in tracked_list:
            cx_o = int(obj['cx'])
            cy_o = int(obj['cy'])
            w_o = int(obj.get('w_px', 180))
            h_o = int(obj.get('h_px', 260))
            bx1 = max(0, cx_o - w_o // 2)
            by1 = max(0, cy_o - h_o // 2)
            bx2 = min(W_FULL - 1, cx_o + w_o // 2)
            by2 = min(H_FULL - 1, cy_o + h_o // 2)

            is_trig = obj.get('is_triggered', False)
            is_ng = obj.get('is_ng', False)

            if is_trig:
                box_color = (0, 0, 255) if is_ng else (0, 255, 0)
                tag_text = obj.get('status_label', 'CHOT')
            else:
                box_color = (0, 0, 255) if is_ng else (0, 255, 0)
                tag_text = f"DANG CHECK: {obj['class_name'].upper()}"

            cv2.rectangle(display_frame, (bx1, by1), (bx2, by2), box_color, 3)
            cv2.circle(display_frame, (cx_o, cy_o), 6, (0, 255, 255), -1)
            cv2.rectangle(display_frame, (bx1, by1 - 26), (bx1 + len(tag_text) * 11, by1), box_color, -1)
            cv2.putText(display_frame, tag_text, (bx1 + 5, max(15, by1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            
            # Hiển thị kích thước Pixel thực tế & Hệ số quy đổi chuẩn ngay dưới hộp thuốc
            px_rate_x = 51.0 / w_o if w_o > 0 else 0.240
            cv2.putText(display_frame, f"W:{w_o}px, H:{h_o}px -> PIXEL_TO_MM: {px_rate_x:.3f}", (bx1, min(H_FULL - 10, by2 + 18)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 255), 2)

        # Trục đỏ căn tâm
        cv2.line(display_frame, (CENTER_X, 0), (CENTER_X, H_FULL), (0, 0, 255), 2)
        cv2.circle(display_frame, (CENTER_X, TRIGGER_LINE_Y), 7, (0, 255, 255), -1)

        # Bảng OSD
        cv2.rectangle(display_frame, (10, 10), (480, 195), (0, 0, 0), -1)
        cv2.putText(display_frame, f"QUEUE NG: {len(current_queue)} | STATE: {r_state}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2)
        cv2.putText(display_frame, f"THUOC OK: {c_ok} | THUOC NG: {c_ng}", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 255, 0), 2)
        cv2.putText(display_frame, f"DB30 L={DISTANCE_TRIGGER_TO_ROBOT:.0f}mm | V={V_CONVEYOR:.0f}mm/s", (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        cv2.putText(display_frame, f"HOMOGRAPHY 3x3 | X_OFF: {X_CALIB_OFFSET:+.1f}mm", (20, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        cv2.putText(display_frame, f"EXP LOG: Ket_qua_thuc_nghiem.csv ({exp_counter} mau)", (20, 155), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 215, 0), 2)
        cv2.putText(display_frame, f"AI: {fps_ai:.1f} FPS | TRACK: {fps_tr:.0f} Hz", (20, 185), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 2)

        frame_resized = cv2.resize(display_frame, (1024, 768))
        cv2.imshow("HE THONG PHAN LOAI THUOC ROBOT DELTA - DB30 FIFO", frame_resized)
        
        k = cv2.waitKey(1) & 0xFF
        if k == ord('q') or k == ord('Q'): 
            break
        elif k == ord('-'):
            DISTANCE_TRIGGER_TO_ROBOT = max(50.0, DISTANCE_TRIGGER_TO_ROBOT - 5.0)
            print(f"📏 Khoảng cách Cam->Robot: {DISTANCE_TRIGGER_TO_ROBOT:.1f}mm")
        elif k == ord('='):
            DISTANCE_TRIGGER_TO_ROBOT += 5.0
            print(f"📏 Khoảng cách Cam->Robot: {DISTANCE_TRIGGER_TO_ROBOT:.1f}mm")
        elif k == ord('['):
            V_CONVEYOR = max(10.0, V_CONVEYOR - 5.0)
            print(f"⚡ Vận tốc băng tải: {V_CONVEYOR:.1f}mm/s")
        elif k == ord(']'):
            V_CONVEYOR += 5.0
            print(f"⚡ Vận tốc băng tải: {V_CONVEYOR:.1f}mm/s")
        elif k == ord(','):
            X_CALIB_OFFSET -= 1.0
            print(f"📐 Bù lệch tâm Robot sang Trái: {X_CALIB_OFFSET:+.1f}mm")
        elif k == ord('.'):
            X_CALIB_OFFSET += 1.0
            print(f"📐 Bù lệch tâm Robot sang Phải: {X_CALIB_OFFSET:+.1f}mm")
        elif k == ord('t') or k == ord('T'):
            with queue_lock:
                shared_data['new_items_to_plc'].append({
                    'id': 991, 'x_robot': -35.0, 'y_rel_robot': -DISTANCE_TRIGGER_TO_ROBOT
                })
            print(f"🧪 [TEST TRÁI] ĐÃ PHÁT LỆNH TEST GẮP LỆCH TRÁI X = -35.0 mm!")
        elif k == ord('y') or k == ord('Y'):
            with queue_lock:
                shared_data['new_items_to_plc'].append({
                    'id': 992, 'x_robot': +35.0, 'y_rel_robot': -DISTANCE_TRIGGER_TO_ROBOT
                })
            print(f"🧪 [TEST PHẢI] ĐÃ PHÁT LỆNH TEST GẮP LỆCH PHẢI X = +35.0 mm!")
        elif k == ord('c') or k == ord('C'):
            with open(EXP_CSV_PATH, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "STT", "Thời Gian", "Mã Gói", "Nhãn AI Nhận Diện", 
                    "Độ Tin Cậy (%)", "Tọa Độ X (mm)", "Tọa Độ Y (mm)", 
                    "Kết Quả Phân Loại", "Hành Động Hệ Thống"
                ])
            exp_counter = 0
            with queue_lock:
                shared_data['count_ok'] = 0
                shared_data['count_ng'] = 0
            print("🧹 [THỰC NGHIỆM] ĐÃ XÓA SẠCH LOG VÀ RESET BỘ ĐẾM VỀ 0 ĐỂ CHẠY LẠI TỪ ĐẦU!")

    shared_data['is_running'] = False
    time.sleep(0.2)

    try:
        if cam_mode == "BASLER" and camera is not None:
            camera.StopGrabbing()
            camera.Close()
        elif cam_mode == "MVS" and camera is not None:
            camera.close()
        elif cam_mode == "WEBCAM" and camera is not None:
            camera.release()
        cv2.destroyAllWindows()
        if plc_connected:
            client.disconnect()
        print("🛑 ĐÃ DỪNG HỆ THỐNG AN TOÀN.")
    except: pass

if __name__ == "__main__":
    main()