"""
=============================================================================
HỆ THỐNG ĐIỀU KHIỂN & VISION CÁNH TAY ROBOT 3 BẬC TỰ DO (3-DOF ARM)
=============================================================================
- Giao tiếp PLC Siemens S7-1200 qua Snap7 (DB4, Bơm %Q1.0, CB1 %I0.3, CB2 %I0.4)
- Thuật toán Động học chuẩn: IK(x, y, z) & FK(q1, q2, q3) thuần túy không gian Descartes
- Quy trình Gắp - Thả hoàn toàn theo tọa độ (X, Y, Z) mm (chuẩn kiến trúc DoAnRobot)
=============================================================================
"""

import cv2
import numpy as np
import snap7
from snap7.util import set_real, set_bool, get_bool, get_real
import time
import math
import os
import threading
import sys
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# =============================================================================
# 1. CẤU HÌNH PLC S7-1200 & PHẦN CỨNG
# =============================================================================

# =============================================================================
# KẾT NỐI CLOUD SUPABASE & TỰ ĐỘNG LƯU / UPLOAD ẢNH CHỤP CAMERA AI
# =============================================================================
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
    def _worker():
        image_url = None
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
                            print(f"☁️ [CAMERA -> SUPABASE] Đã upload ảnh: {file_name}")
            except Exception as ex_img:
                print(f"⚠️ Lỗi lưu ảnh camera: {ex_img}")

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
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()

PLC_IP          = '192.168.0.10'
PLC_RACK        = 0
PLC_SLOT        = 1
DB_ROBOT_NUMBER = 4

# Khối DB4 trong TIA Portal:
OFFSET_DB_TRIGGER = (0, 0)       # DB4.DBX0.0: Kich Xung (Bool)
OFFSET_DB_X       = 2            # DB4.DBD2:   Trục Cẳng tay (Real)
OFFSET_DB_Y       = 6            # DB4.DBD6:   Trục Cánh tay (Real)
OFFSET_DB_Z       = 10           # DB4.DBD10:  Trục Xoay đế  (Real)
OFFSET_DB_SPEED   = 50           # DB4.DBD50:  Vận tốc (Real)

# Cấu hình Bơm hút chân không (%Q1.0) & Cảm biến (%I0.3, %I0.4):
ENABLE_VACUUM_PUMP = True
Q_BYTE_BOM         = 1
Q_BIT_BOM          = 0           # %Q1.0: Bơm hút
I_BYTE_INPUTS      = 0
I_BIT_CB1_CAM      = 3           # %I0.3: CB1 trạm Camera
I_BIT_CB2_ROBOT    = 4           # %I0.4: CB2 trạm Robot

# =============================================================================
# GIỚI HẠN AN TOÀN TRỤC (ĐỘ) ĐỒNG BỘ 100% GIỮA BÁO CÁO ĐỒ ÁN & PLC S7-1200:
# =============================================================================
# 1. Trục 1 - Xoay đế (Trục Z PLC / DBD10):
#    - Lý thuyết Báo cáo: -90° <= theta1 <= +90° (quy ước nhìn thẳng băng tải là 0°)
#    - Thực tế PLC: Cảm biến Home đặt lệch 90°, nên góc PLC = theta1 - 90°.
#      * Khay 1 (Trái):   Z = -160.0° (tương đương theta1 = -70° trong báo cáo)
#      * Băng tải (Giữa): Z = -90.0°  (tương đương theta1 = 0° trong báo cáo)
#      * Khay 2 (Phải):   Z = -26.0°  (tương đương theta1 = +64° trong báo cáo)
#      Góc quét cơ khí thực tế chỉ là 134° <= 180° báo cáo (hoàn toàn an toàn cơ khí).
LIMIT_Z = (-170.0, 10.0)         # Trục 1 - Xoay đế (đáp ứng từ Khay 1 -160° đến Khay 2 -26°)

# 2. Trục 2 - Cánh tay / Vai (Trục Y PLC / DBD6):
#    - Lý thuyết Báo cáo: -90° <= theta2 <= +90°
#    - Thực tế PLC: Standby (-41.5°), hạ thả khay (-50.0°), hạ gắp băng tải (-60.0°)
LIMIT_Y = (-90.0, 10.0)          # Trục 2 - Cánh tay / Vai

# 3. Trục 3 - Cẳng tay / Khuỷu (Trục X PLC / DBD2):
#    - Lý thuyết Báo cáo: -150° <= theta3 <= 0°
#    - Thực tế PLC: Vươn cẳng tay quanh -73.0°
LIMIT_X = (-150.0, 10.0)         # Trục 3 - Cẳng tay / Khuỷu chuẩn theo công thức (4.21)

# Kích thước cơ khí robot (mm):
L1 = 134.0   # Chiều cao trụ đế
L2 = 120.0   # Chiều dài khâu vai
L3 = 120.0   # Chiều dài khâu cẳng tay
L4 = 54.0    # Độ vươn ngang đầu giác hút

# =============================================================================
# 2. ĐỊNH NGHĨA TỌA ĐỘ DESCARTES (X, Y, Z) mm - KHÔNG DÙNG DẠY ĐIỂM
# =============================================================================
# Vị trí Standby theo góc PLC (Thứ tự PLC: X=Cẳng tay, Y=Vai, Z=Xoay đế):
POS_STANDBY = (-70.00, -50.50, -90.00)  # Cẳng tay=-70.0°, Vai=-50.5°, Đế=-90.0°

# Vị trí Home / Chờ an toàn trên cao (mm):
HOME_POS    = (0.00, -250.00, 149.43)

# Cao độ thao tác trên băng tải (mm):
Z_APPROACH  = 174.11   # Cao độ tiếp cận trên đỉnh phôi
Z_PICK      = 109.30   # Cao độ mặt phôi trên băng tải
Z_LIFT      = 174.11   # Cao độ nhấc phôi lên an toàn

# Tọa độ 2 Khay phân loại (Thứ tự PLC: X=Cẳng tay, Y=Vai, Z=Xoay đế):
KHAY_1_POS  = (-73.00, -41.50, -160.00)     # Khay 1 (Trái):  Cẳng tay=-73°, Vai=-50°, Đế=-160°
KHAY_2_POS  = (-73.00, -41.50, -26.00)      # Khay 2 (Phải): Cẳng tay=-73°, Vai=-50°, Đế=-26°
BOX_1_POS   = KHAY_1_POS                    # Alias tương thích
BOX_2_POS   = KHAY_2_POS                    # Alias tương thích

# Cấu hình Camera & Tâm quan sát (Hiệu chuẩn thực tế: Bề rộng băng tải 75mm = 205px ROI -> 0.366 mm/px):
CAM_OFFSET_X   = 0.00       # Tâm băng tải chuẩn trục X Robot (mm) - Băng tải tại X=0.00
CAM_OFFSET_Y   = -250.00    # Vị trí tâm băng tải chuẩn theo tâm giác hút (Y = -250.00 mm)
PIXEL_TO_MM_X  = 0.366      # Tỷ lệ mm/pixel theo chiều ngang ảnh (75.0mm / 205px = 0.3658)
PIXEL_TO_MM_Y  = 0.366      # Tỷ lệ mm/pixel theo chiều dọc ảnh   (42.0mm / 114px = 0.3684)

# Hiệu chuẩn bù sai số gắp thực tế (mm) nếu cần vi chỉnh thêm:
OFFSET_PICK_LEFT_Y  = 14.00    # Bù hàng trong (gần robot) vươn ra thêm 45mm vì bị co quá sâu (dùng khi fallback)
OFFSET_PICK_RIGHT_Y = 0.00     # Hàng ngoài (gần CB2) giữ nguyên 0mm vì đã gắp chuẩn 100%

# Cấu hình vùng ROI chụp ảnh băng tải (nằm trọn vẹn trong lòng băng tải xanh):
ROI_X       = 255
ROI_Y       = 10
ROI_WIDTH   = 205
ROI_HEIGHT  = 465
ROI_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roi_conveyor.json")

# =============================================================================
# CẤU HÌNH MA TRẬN PHỐI CẢNH 4 ĐIỂM (PERSPECTIVE TRANSFORM - CHUẨN TEST2206.py)
# =============================================================================
CALIB_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibration.json")
TRANSFORM_MATRIX  = None
CALIB_OFFSET_X    = 0.00
CALIB_OFFSET_Y    = 0.00

def load_calibration_config():
    """Tải ma trận biến đổi phối cảnh 4 điểm (Perspective Transform) từ calibration.json"""
    global TRANSFORM_MATRIX, CALIB_OFFSET_X, CALIB_OFFSET_Y
    if os.path.exists(CALIB_CONFIG_PATH):
        try:
            with open(CALIB_CONFIG_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            if "transform_matrix" in d and len(d["transform_matrix"]) == 3:
                TRANSFORM_MATRIX = np.array(d["transform_matrix"], dtype=np.float32)
                CALIB_OFFSET_X = float(d.get("offset_x", 0.0))
                CALIB_OFFSET_Y = float(d.get("offset_y", 0.0))
                print(f"🎯 [CALIB] Đã nạp thành công Ma trận phối cảnh 4 điểm từ calibration.json!")
                print(f"   👉 Bù vi chỉnh (Fine-tuning): Offset X = {CALIB_OFFSET_X:+.1f} mm, Offset Y = {CALIB_OFFSET_Y:+.1f} mm")
                return True
        except Exception as e:
            print(f"⚠️ [CALIB] Lỗi đọc calibration.json: {e}")
    TRANSFORM_MATRIX = None
    print("ℹ️ [CALIB] Chưa có ma trận phối cảnh, dùng công thức tuyến tính mặc định.")
    return False

# Nạp ma trận hiệu chuẩn ngay khi khởi động
load_calibration_config()

# =============================================================================
# CẤU HÌNH MÔ HÌNH NHẬN DIỆN YOLO (ULTRALYTICS YOLO)
# =============================================================================
YOLO_MODEL_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "best.pt")
YOLO_CONF_THRESH = 0.45
YOLO_MODEL       = None

# Ánh xạ tên Class của YOLO sang vị trí Khay tương ứng
YOLO_CLASS_MAPPING = {
    'tp4056': {'box': KHAY_1_POS, 'name': 'Khay 1 (Trái)'},
    'lm2596': {'box': KHAY_2_POS, 'name': 'Khay 2 (Phải)'},
    'phoi1':  {'box': KHAY_1_POS, 'name': 'Khay 1 (Trái)'},
    'phoi2':  {'box': KHAY_2_POS, 'name': 'Khay 2 (Phải)'},
    'type1':  {'box': KHAY_1_POS, 'name': 'Khay 1 (Trái)'},
    'type2':  {'box': KHAY_2_POS, 'name': 'Khay 2 (Phải)'},
}

def load_yolo_model():
    """Tự động nạp mô hình YOLO (best.pt) nếu có trong thư mục dự án"""
    global YOLO_MODEL
    if os.path.exists(YOLO_MODEL_PATH):
        try:
            from ultralytics import YOLO
            YOLO_MODEL = YOLO(YOLO_MODEL_PATH)
            print(f"🤖 [YOLO] Đã nạp thành công mô hình: {YOLO_MODEL_PATH}")
            if hasattr(YOLO_MODEL, 'names'):
                print(f"   👉 Danh sách lớp (Classes): {YOLO_MODEL.names}")
            return True
        except Exception as e:
            print(f"⚠️ [YOLO] Lỗi nạp mô hình ({e}). Sẽ dùng thuật toán OpenCV.")
    else:
        print(f"ℹ️ [YOLO] Chưa có '{os.path.basename(YOLO_MODEL_PATH)}' -> Tự động dùng thuật toán OpenCV.")
    return False

# Tự động thử nạp YOLO ngay khi khởi động
load_yolo_model()


def load_roi_config():
    if os.path.exists(ROI_CONFIG_PATH):
        try:
            with open(ROI_CONFIG_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    if "x" in d and "width" in d:
                        return [int(d.get("x", ROI_X)), int(d.get("y", ROI_Y)),
                                int(d.get("width", ROI_WIDTH)), int(d.get("height", ROI_HEIGHT))]
                    elif "roi" in d and len(d["roi"]) == 4:
                        x1, y1, x2, y2 = [int(v) for v in d["roi"]]
                        w = x2 - x1 if x2 > x1 else x2
                        h = y2 - y1 if y2 > y1 else y2
                        return [x1, y1, w, h]
        except Exception:
            pass
    return [ROI_X, ROI_Y, ROI_WIDTH, ROI_HEIGHT]

def save_roi_config(x, y, w, h):
    try:
        with open(ROI_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"x": int(x), "y": int(y), "width": int(w), "height": int(h), "roi": [int(x), int(y), int(x + w), int(y + h)]}, f, indent=4)
        print(f"💾 [ROI] Đã lưu vùng ROI băng tải: X={x}, Y={y}, Ngang={w}px, Dài={rh if 'rh' in locals() else h}px")
    except Exception as e:
        print(f"⚠️ [ROI] Lỗi lưu ROI: {e}")


# =============================================================================
# 3. THUẬT TOÁN ĐỘNG HỌC THUẬN (FK) & ĐỘNG HỌC NGHỊCH (IK) CHUẨN
# =============================================================================
def IK(x, y, z):
    """
    ĐỘNG HỌC NGHỊCH (IK) - Chuẩn theo Chương 4 & kiến trúc DoAnRobot:
    Đầu vào: (x, y, z) mm
    Đầu ra:  (q1, q2, q3) độ lý thuyết hoặc (None, None, None) nếu ngoài tầm với.
    """
    try:
        q1 = math.degrees(math.atan2(y, x))
        r = math.sqrt(x * x + y * y)
        r_1 = r - L4
        z_1 = L1 - z
        A = r_1 * r_1 + z_1 * z_1
        max_reach = L2 + L3
        min_reach = abs(L2 - L3)
        d = math.sqrt(A)
        if d > max_reach or d < min_reach:
            return None, None, None

        c3 = (A - L2 * L2 - L3 * L3) / (2.0 * L2 * L3)
        c3 = max(min(c3, 1.0), -1.0)
        s3 = math.sqrt(max(0.0, 1.0 - c3 * c3))
        q3 = math.degrees(math.atan2(s3, c3))

        c2 = r_1 * (L3 * c3 + L2) + (L3 * s3) * z_1
        s2 = z_1 * (L3 * c3 + L2) - (L3 * s3) * r_1
        q2 = math.degrees(math.atan2(s2, c2))
        return q1, q2, q3
    except Exception:
        return None, None, None

def FK(q1, q2, q3):
    """
    ĐỘNG HỌC THUẬN (FK) - Chuẩn theo hệ phương trình (4.8):
    Đầu vào: (q1, q2, q3) độ lý thuyết
    Đầu ra:  (x, y, z) mm
    """
    q1_rad = math.radians(q1)
    q2_rad = math.radians(q2)
    q3_rad = math.radians(q3)

    r_wrist = L2 * math.cos(q2_rad) + L3 * math.cos(q2_rad + q3_rad)
    z_wrist = L1 - (L2 * math.sin(q2_rad) + L3 * math.sin(q2_rad + q3_rad))

    x = (r_wrist + L4) * math.cos(q1_rad)
    y = (r_wrist + L4) * math.sin(q1_rad)
    z = z_wrist
    return x, y, z

def angles_to_plc(q1, q2, q3):
    """
    Quy đổi 3 góc lý thuyết (q1, q2, q3) sang hệ tọa độ thanh ghi PLC DB4:
      - DB4.DBD10 (Trục 1 - Xoay đế):  plc_z = q1
      - DB4.DBD6  (Trục 2 - Cánh tay): plc_y = -(90.0 + q2)
      - DB4.DBD2  (Trục 3 - Cẳng tay): plc_x = -q3
    """
    plc_z = float(q1)
    plc_y = -(90.0 + float(q2))
    plc_x = -float(q3)
    return plc_x, plc_y, plc_z

def plc_to_angles(plc_x, plc_y, plc_z):
    """Quy đổi từ tọa độ PLC ngược lại 3 góc lý thuyết"""
    q1 = float(plc_z)
    q2 = -90.0 - float(plc_y)
    q3 = -float(plc_x)
    return q1, q2, q3


# =============================================================================
# 4. TRÌNH ĐIỀU KHIỂN PLC SIEMENS S7-1200 (SNAP7)
# =============================================================================
class PLCController:
    def __init__(self, ip=PLC_IP, rack=PLC_RACK, slot=PLC_SLOT):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.client = snap7.client.Client()
        self.connected = False
        self.lock = threading.Lock()

    def connect(self):
        with self.lock:
            try:
                if not self.client.get_connected():
                    self.client.connect(self.ip, self.rack, self.slot)
                self.connected = self.client.get_connected()
                if self.connected:
                    print(f"✅ [PLC] Đã kết nối thành công tới S7-1200 tại {self.ip}")
            except Exception as e:
                self.connected = False
                print(f"⚠️ [PLC] Chưa thể kết nối ({e}). Chạy chế độ mô phỏng.")
        return self.connected

    def send_target_angles(self, plc_x, plc_y, plc_z, speed=32.0):
        """Ghi 3 góc trục vào DB4 và kích xung di chuyển DB4.DBX0.0"""
        # Kẹp an toàn cơ khí theo mô hình thực tế:
        plc_x = max(LIMIT_X[0], min(LIMIT_X[1], float(plc_x)))
        plc_y = max(LIMIT_Y[0], min(LIMIT_Y[1], float(plc_y)))
        plc_z = max(LIMIT_Z[0], min(LIMIT_Z[1], float(plc_z)))

        if not self.connected:
            return True
        with self.lock:
            try:
                if not self.client.get_connected():
                    self.connect()

                # Ghi tọa độ X, Y, Z vào DB4 (DBD2, DBD6, DBD10)
                buf_coords = bytearray(12)
                set_real(buf_coords, 0, float(plc_x))
                set_real(buf_coords, 4, float(plc_y))
                set_real(buf_coords, 8, float(plc_z))
                self.client.db_write(DB_ROBOT_NUMBER, OFFSET_DB_X, buf_coords)

                # Ghi tốc độ
                buf_spd = bytearray(4)
                set_real(buf_spd, 0, float(speed))
                self.client.db_write(DB_ROBOT_NUMBER, OFFSET_DB_SPEED, buf_spd)

                # Kích xung di chuyển (True -> False)
                buf_trig = bytearray(1)
                set_bool(buf_trig, 0, 0, True)
                self.client.db_write(DB_ROBOT_NUMBER, 0, buf_trig)
                time.sleep(0.040)
                set_bool(buf_trig, 0, 0, False)
                self.client.db_write(DB_ROBOT_NUMBER, 0, buf_trig)
                return True
            except Exception as e:
                print(f"⚠️ [PLC] Lỗi gửi tọa độ: {e}")
                self.connected = False
                return False

    def move_to_xyz(self, x, y, z, speed=32.0, wait_time=2.0):
        """
        ĐIỀU KHIỂN ROBOT THEO TỌA ĐỘ DESCARTES (X, Y, Z) mm:
        Tự động giải Động học nghịch (IK) -> chuyển đổi góc -> kích PLC di chuyển.
        """
        q1, q2, q3 = IK(x, y, z)
        if q1 is None:
            print(f"❌ [IK NGOÀI TẦM VỚI] Tọa độ (X={x:.1f}, Y={y:.1f}, Z={z:.1f}) mm không thể với tới!")
            return False

        plc_x, plc_y, plc_z = angles_to_plc(q1, q2, q3)
        ok = self.send_target_angles(plc_x, plc_y, plc_z, speed=speed)
        robot_state.update_from_cartesian(x, y, z, q1, q2, q3, plc_x, plc_y, plc_z)
        if wait_time > 0:
            time.sleep(wait_time)
        return ok

    def set_vacuum(self, on=True):
        """Bật / Tắt bơm hút chân không (%Q1.0)"""
        if not ENABLE_VACUUM_PUMP or not self.connected:
            robot_state.vacuum_state = on
            return True
        with self.lock:
            try:
                if not self.client.get_connected():
                    self.connect()
                data = self.client.ab_read(Q_BYTE_BOM, 1)
                set_bool(data, 0, Q_BIT_BOM, on)
                self.client.ab_write(Q_BYTE_BOM, data)
                robot_state.vacuum_state = on
                return True
            except Exception:
                return False

    def trigger_homing(self):
        """Kích hoạt chu trình Homing PLC (DB4.DBX55.7)"""
        if not self.connected:
            return True
        with self.lock:
            try:
                if not self.client.get_connected():
                    self.connect()
                buf = bytearray(1)
                set_bool(buf, 0, 7, True)
                self.client.db_write(DB_ROBOT_NUMBER, 55, buf)
                time.sleep(0.050)
                set_bool(buf, 0, 7, False)
                self.client.db_write(DB_ROBOT_NUMBER, 55, buf)
                print("🚀 [PLC] Đã kích hoạt lệnh Homing!")
                return True
            except Exception as e:
                print(f"⚠️ [PLC] Lỗi Homing: {e}")
                return False

    def trigger_conveyor_continue(self):
        """Kích hoạt xung báo PLC cho băng tải chạy tiếp đón mẻ mới (DB4.DBX55.1)"""
        if not self.connected:
            print("🚀 [PLC MÔ PHỎNG] Đã phát xung kích băng tải chạy tiếp đón mẻ Fomo mới!")
            return True
        with self.lock:
            try:
                if not self.client.get_connected():
                    self.connect()
                buf = bytearray(1)
                set_bool(buf, 0, 1, True)
                self.client.db_write(DB_ROBOT_NUMBER, 55, buf)
                time.sleep(0.060)
                set_bool(buf, 0, 1, False)
                self.client.db_write(DB_ROBOT_NUMBER, 55, buf)
                print("🚀 [PLC] Đã kích xung (DB4.DBX55.1) -> Băng tải chạy tiếp!")
                return True
            except Exception as e:
                print(f"⚠️ [PLC] Lỗi kích chạy băng tải: {e}")
                return False

plc = PLCController()


# =============================================================================
# 5. QUẢN LÝ TRẠNG THÁI ROBOT
# =============================================================================
class RobotStateManager:
    def __init__(self):
        self.current_state = "HOME"
        self.is_busy = False
        self.vacuum_state = False
        self.current_xyz = list(HOME_POS)
        q1, q2, q3 = IK(*HOME_POS)
        self.current_angles = (q1, q2, q3) if q1 is not None else (0.0, 0.0, 0.0)
        self.current_plc = angles_to_plc(*self.current_angles)
        self.lock = threading.Lock()

    def set_state(self, state):
        with self.lock:
            self.current_state = state

    def update_from_cartesian(self, x, y, z, q1, q2, q3, plc_x, plc_y, plc_z):
        with self.lock:
            self.current_xyz = [x, y, z]
            self.current_angles = (q1, q2, q3)
            self.current_plc = (plc_x, plc_y, plc_z)

robot_state = RobotStateManager()


# =============================================================================
# 6. QUY TRÌNH GẮP - ĐẶT HOÀN TOÀN THEO TỌA ĐỘ DESCARTES (X, Y, Z) mm
# =============================================================================
def execute_pick_and_place(pick_x, pick_y, target_box_pos, item_name="PHOI"):
    """
    CHU TRÌNH GẮP - ĐẶT TỰ ĐỘNG:
      - Vị trí gắp: 100% Động học nghịch (IK) từ Camera (pick_x, pick_y) Descartes
      - Vị trí thả: Trực tiếp vào Khay 1 (-160, -50, -73) hoặc Khay 2 (-26, -50, -73)
    """
    kx, ky, kz = target_box_pos  # (-73, -50, -160) hoặc (-73, -50, -26)
    khay_name = "Khay 1" if kz < -100 else "Khay 2"

    # 1. Kiểm tra giải thuật IK tại điểm gắp trên băng tải
    q1_chk, _, _ = IK(pick_x, pick_y, Z_PICK)
    if q1_chk is None:
        print(f"❌ [IK SKIP] {item_name} tại ({pick_x:.1f}, {pick_y:.1f}) mm - NGOÀI TẦM VỚI!")
        return False

    q1_p, q2_p, q3_p = IK(pick_x, pick_y, Z_PICK)
    plc_x_p, plc_y_p, plc_z_p = angles_to_plc(q1_p, q2_p, q3_p)
    print(f"\n🦾 [GẮP ĐỘNG HỌC NGHỊCH IK] {item_name} tại (X={pick_x:.1f}, Y={pick_y:.1f}, Z={Z_PICK:.1f}) mm:")
    print(f"   👉 Giải IK: q1={q1_p:.2f}°, q2={q2_p:.2f}°, q3={q3_p:.2f}°")
    print(f"   👉 Gửi sang PLC: Cẳng tay={plc_x_p:.2f}°, Vai={plc_y_p:.2f}°, Xoay đế={plc_z_p:.2f}°")

    # 1. Đến trên phôi
    robot_state.set_state(f"1. TIẾP CẬN ({item_name})")
    print(f"⏳ [1/7] Đến trên phôi: ({pick_x:.1f}, {pick_y:.1f}, {Z_APPROACH:.1f}) mm...")
    plc.move_to_xyz(pick_x, pick_y, Z_APPROACH, wait_time=1.5)

    # 2. Hạ xuống gắp (Vai chúc xuống -60°)
    robot_state.set_state(f"2. HẠ XUỐNG GẮP ({item_name})")
    print(f"⏳ [2/7] Hạ xuống mặt phôi: ({pick_x:.1f}, {pick_y:.1f}, {Z_PICK:.1f}) mm...")
    plc.move_to_xyz(pick_x, pick_y, Z_PICK, wait_time=2.5)

    # 3. Bật hút
    print(f"📍 [3/7] Bật bơm hút chân không (%Q1.0)...")
    plc.set_vacuum(True)
    time.sleep(0.8)

    # 4. Nhấc lên
    robot_state.set_state(f"3. NHẤC LÊN ({item_name})")
    print(f"⏳ [4/7] Nhấc lên cao an toàn: ({pick_x:.1f}, {pick_y:.1f}, {Z_LIFT:.1f}) mm...")
    plc.move_to_xyz(pick_x, pick_y, Z_LIFT, wait_time=2.0)

    # 5. Di chuyển sang trên Khay thả (Giữ vai ở độ cao an toàn -41.5°)
    robot_state.set_state(f"4. SANG {khay_name}")
    print(f"⏳ [5/7] Di chuyển sang {khay_name}: Cẳng tay={kx:.0f}°, Vai=-41.5°, Đế={kz:.0f}°...")
    plc.send_target_angles(kx, -41.50, kz, speed=28.0)
    time.sleep(2.5)

    # 6. Hạ vào khay & Thả phôi (Vai hạ xuống ky=-50°)
    robot_state.set_state(f"5. THẢ VÀO {khay_name}")
    print(f"⏳ [6/7] Hạ vào {khay_name}: Cẳng tay={kx:.0f}°, Vai={ky:.0f}°, Đế={kz:.0f}°...")
    plc.send_target_angles(kx, ky, kz, speed=25.0)
    time.sleep(1.2)
    plc.set_vacuum(False)
    print(f"📍 Tắt bơm hút thả phôi!")
    time.sleep(0.5)

    # Nhấc vai lên lại trên khay
    plc.send_target_angles(kx, -41.50, kz, speed=28.0)
    time.sleep(1.2)

    # 7. Về vị trí Home/Chờ trên băng tải
    robot_state.set_state("STANDBY")
    print(f"⏳ [7/7] Về vị trí Standby trên băng tải: Cẳng tay={POS_STANDBY[0]}°, Vai={POS_STANDBY[1]}°, Đế={POS_STANDBY[2]}°...")
    plc.send_target_angles(*POS_STANDBY, speed=28.0)
    print(f"🎉 Đã gắp xong {item_name} và thả vào {khay_name} thành công!\n")
    return True


# =============================================================================
# 7. PIPELINE 2 CẢM BIẾN (CB1 QUÉT PHÔI -> CB2 KÍCH GẮP)
# =============================================================================
fomo_pipeline = {
    'batches': [],
    'lock': threading.Lock(),
    'cb1_state': False,
    'cb2_state': False,
    'total_scanned': 0,
    'total_sorted': 0
}

def on_sensor_cb1_triggered():
    """
    CB1 kích hoạt (%I0.3): Quét liên tục mẻ Fomo khi trôi qua Camera để chốt trọn vẹn 4 phôi
    - Khắc phục triệt để hiện tượng chụp quá sớm khi hàng phôi sau chưa kịp vào khung hình.
    """
    print("\n📸 [CB1 - TRẠM CAMERA] Cảm biến 1 kích hoạt -> Đang quét liên tục mẻ Fomo khi trôi qua...")

    # Quét luồng camera liên tục trong tối đa 1.5 giây khi phôi trôi vào tâm camera
    # Tự động chốt khoảnh khắc thấy NHIỀU PHÔI NHẤT (chuẩn mẻ 2x2 là đủ 4 phôi)
    # Nếu cùng số lượng phôi, ưu tiên frame phôi nằm ngay giữa camera nhất (chất lượng hình tốt nhất)
    best_targets = []
    start_t = time.time()

    while time.time() - start_t < 1.5:
        with shared_vision['lock']:
            curr = list(shared_vision['detected_targets'])

        if len(curr) > len(best_targets):
            best_targets = curr
            print(f"   👁️ [Quét liên tục] Đã thấy {len(best_targets)} phôi...")
        elif len(curr) == len(best_targets) and len(curr) > 0:
            avg_dist_curr = sum(abs(t['cy'] - 240.0) for t in curr) / len(curr)
            avg_dist_best = sum(abs(t['cy'] - 240.0) for t in best_targets) / len(best_targets)
            if avg_dist_curr < avg_dist_best:
                best_targets = curr

        # Nếu đã bắt đủ 4 phôi (chuẩn mẻ 2x2) thì chốt ngay lập tức!
        if len(best_targets) >= 4:
            break

        time.sleep(0.040)  # Chu kỳ 25 FPS

    current_targets = best_targets

    # Nếu không có phôi thật, kiểm tra điểm click chuột thủ công
    if len(current_targets) == 0:
        manual_t = shared_vision.get('manual_target')
        if manual_t is not None:
            current_targets = [manual_t]
        else:
            print("⚠️ [CB1] Không phát hiện phôi nào trên băng tải -> Bỏ qua, không lưu mẻ ảo!")
            return

    with fomo_pipeline['lock']:
        batch_id = fomo_pipeline['total_scanned'] + 1
        batch_data = {
            'id': batch_id,
            'items': current_targets,
            'timestamp': time.time()
        }
        fomo_pipeline['batches'].append(batch_data)
        fomo_pipeline['total_scanned'] += 1

    print(f"📸 [CB1] ĐÃ CHỐT MẺ #{batch_id} ({len(current_targets)} phôi):")
    for idx, tg in enumerate(current_targets, start=1):
        q1, q2, q3 = tg.get('ik_angles', (0, 0, 0))
        label_str = tg.get('label', 'PHOI')
        w_mm = tg.get('width_mm', 0.0)
        l_mm = tg.get('length_mm', 0.0)
        print(f"   👉 Phôi #{idx} ({label_str} - {l_mm:.1f}x{w_mm:.1f}mm): X={tg['x_robot']:.1f} mm, Y={tg['y_robot']:.1f} mm -> IK: q1={q1:.1f}°, q2={q2:.1f}°, q3={q3:.1f}°")
    print(f"✅ [CB1] Đã lưu vào hàng đợi! Khi phôi tới CB2 (%I0.4) -> Robot sẽ gắp!\n")

def on_sensor_cb2_triggered():
    """CB2 kích hoạt (%I0.4): Phôi đã vào trạm Robot -> Kích hoạt gắp"""
    print("\n📍 [CB2 - TRẠM ROBOT] Cảm biến 2 kích hoạt -> Phôi đã vào trạm Robot!")
    if robot_state.is_busy:
        print("⚠️ [CB2] Robot đang bận chu trình gắp trước, bỏ qua tín hiệu!")
        return

    with fomo_pipeline['lock']:
        if len(fomo_pipeline['batches']) == 0:
            with shared_vision['lock']:
                curr_t = list(shared_vision['detected_targets'])
                man_t = shared_vision.get('manual_target')

            if len(curr_t) > 0:
                print(f"ℹ️ [CB2] Chưa có mẻ lưu -> Gắp trực tiếp toàn bộ {len(curr_t)} phôi đang thấy trên camera...")
                def run_direct():
                    robot_state.is_busy = True
                    try:
                        print(f"\n=======================================================")
                        print(f"📦 [CB2 TRỰC TIẾP] BẮT ĐẦU GẮP LẦN LƯỢT {len(curr_t)} PHÔI:")
                        print(f"=======================================================")
                        for idx, item in enumerate(curr_t, start=1):
                            mod_label = item.get('label', f'Phôi #{idx}')
                            khay = item.get('target_box', KHAY_1_POS)
                            khay_name = item.get('target_name', 'Khay 1')
                            print(f"\n▶️ [Phôi {idx}/{len(curr_t)}]: {mod_label} -> {khay_name} tại ({item['x_robot']:.1f}, {item['y_robot']:.1f}) mm")
                            execute_pick_and_place(item['x_robot'], item['y_robot'], khay, item_name=mod_label)
                        time.sleep(0.5)
                        plc.trigger_conveyor_continue()
                    finally:
                        robot_state.is_busy = False

                threading.Thread(target=run_direct, daemon=True).start()
                return
            elif man_t is not None:
                target = man_t
                print(f"ℹ️ [CB2] Gắp điểm thủ công click tại X={target['x_robot']:.1f}, Y={target['y_robot']:.1f} mm...")
                def run_click():
                    robot_state.is_busy = True
                    try:
                        execute_pick_and_place(target['x_robot'], target['y_robot'], KHAY_1_POS, item_name="CLICK_MANUAL")
                        time.sleep(0.5)
                        plc.trigger_conveyor_continue()
                    finally:
                        robot_state.is_busy = False
                threading.Thread(target=run_click, daemon=True).start()
                return
            else:
                print("⚠️ [CB2] Băng tải không có phôi và hàng đợi rỗng -> Robot ĐỨNG CHỜ, không gắp ảo!")
                return

        batch = fomo_pipeline['batches'].pop(0)

    items = batch['items']
    def run_batch():
        robot_state.is_busy = True
        try:
            print(f"\n=======================================================")
            print(f"📦 [CB2] BẮT ĐẦU GẮP PHÂN LOẠI MẺ FOMO #{batch['id']} ({len(items)} PHÔI):")
            print(f"=======================================================")
            for idx, item in enumerate(items, start=1):
                mod_label = item.get('label', f'Phôi #{idx}')
                khay = item.get('target_box', KHAY_1_POS)
                khay_name = item.get('target_name', 'Khay 1')
                print(f"\n▶️ [Phôi {idx}/{len(items)}]: {mod_label} -> {khay_name} tại ({item['x_robot']:.1f}, {item['y_robot']:.1f}) mm")
                execute_pick_and_place(item['x_robot'], item['y_robot'], khay, item_name=mod_label)

            with fomo_pipeline['lock']:
                fomo_pipeline['total_sorted'] += 1
            print(f"\n🎉 [CB2] ĐÃ GẮP PHÂN LOẠI XONG TOÀN BỘ MẺ #{batch['id']} ({len(items)} PHÔI)!\n")

            # Kích băng tải chạy tiếp đón mẻ Fomo mới
            time.sleep(0.5)
            print("🚀 [PLC] Đang kích tín hiệu cho băng tải tiếp tục chạy đón mẻ mới...")
            plc.trigger_conveyor_continue()
        finally:
            robot_state.is_busy = False

    threading.Thread(target=run_batch, daemon=True).start()

def plc_sensor_monitor_worker():
    """Luồng giám sát cảm biến CB1 và CB2 thời gian thực từ PLC"""
    last_cb1 = False
    last_cb2 = False
    last_cb2_time = 0.0

    while shared_vision['running']:
        if plc.connected and plc.client is not None:
            try:
                with plc.lock:
                    if not plc.client.get_connected():
                        plc.connect()
                    data = plc.client.eb_read(I_BYTE_INPUTS, 1)

                cb1_val = get_bool(data, 0, I_BIT_CB1_CAM)
                cb2_val = get_bool(data, 0, I_BIT_CB2_ROBOT)

                now = time.time()
                if cb1_val and not last_cb1:
                    on_sensor_cb1_triggered()
                if cb2_val and not last_cb2 and (now - last_cb2_time > 1.5):
                    last_cb2_time = now
                    on_sensor_cb2_triggered()

                last_cb1 = cb1_val
                last_cb2 = cb2_val
                fomo_pipeline['cb1_state'] = cb1_val
                fomo_pipeline['cb2_state'] = cb2_val
            except Exception:
                pass
        time.sleep(0.040)


# =============================================================================
# 8. LUỒNG CAMERA & NHẬN DIỆN THỊ GIÁC (OPENCV)
# =============================================================================
shared_vision = {
    'frame': None,
    'roi_rect': load_roi_config(),
    'detected_targets': [],
    'manual_target': None,
    'running': True,
    'fps': 0.0,
    'lock': threading.Lock()
}

def pixel_to_robot(px_x, px_y, img_w=640, img_h=480):
    """
    Quy đổi tọa độ Pixel sang tọa độ Robot (mm):
    1. ƯU TIÊN (Chuẩn TEST2206.py): Dùng Ma trận biến đổi phối cảnh 4 điểm (Perspective Transform)
       -> Tự động nắn thẳng góc xoay, góc nghiêng của Camera và méo hình thang băng tải.
    2. DỰ PHÒNG (Fallback): Dùng tỷ lệ tuyến tính mm/pixel nếu chưa có ma trận.
    """
    global TRANSFORM_MATRIX, CALIB_OFFSET_X, CALIB_OFFSET_Y
    if TRANSFORM_MATRIX is not None:
        try:
            pt = np.array([[[float(px_x), float(px_y)]]], dtype=np.float32)
            res = cv2.perspectiveTransform(pt, TRANSFORM_MATRIX)
            xr = float(res[0][0][0]) + CALIB_OFFSET_X
            yr = float(res[0][0][1]) + CALIB_OFFSET_Y
            return xr, yr
        except Exception:
            pass

    # Công thức tuyến tính cũ (Fallback khi chưa có ma trận):
    roi_rect = shared_vision.get('roi_rect', [ROI_X, ROI_Y, ROI_WIDTH, ROI_HEIGHT])
    center_belt_x = roi_rect[0] + (roi_rect[2] / 2.0)
    center_belt_y = roi_rect[1] + (roi_rect[3] / 2.0)

    # Chiều dọc ảnh (dy_px) tương ứng Trục X Robot (quay đế dọc theo băng tải):
    dy_px = center_belt_y - px_y
    xr = CAM_OFFSET_X + (dy_px * PIXEL_TO_MM_Y)

    # Chiều ngang ảnh (dx_px) tương ứng Trục Y Robot (vươn tay ngang qua băng tải):
    # dx_px > 0 (sang phải ảnh, gần cảm biến CB) -> Vươn ra xa về phía cảm biến (+dx_px)
    # dx_px < 0 (sang trái ảnh, gần thân robot)   -> Co lại về phía thân robot (-|dx_px|)
    dx_px = px_x - center_belt_x
    yr = CAM_OFFSET_Y + (dx_px * PIXEL_TO_MM_X)
    if dx_px < 0:
        yr += OFFSET_PICK_LEFT_Y
    else:
        yr += OFFSET_PICK_RIGHT_Y
    return xr, yr

def detect_objects_in_roi(roi_crop, rx1, ry1, img_w, img_h):
    """
    NHẬN DIỆN MẺ 4 PHÔI (LM2596 & TP4056) TRÊN BÌA FOMO TRẮNG:
    1. Tách nền băng tải PVC màu xanh lá.
    2. Phát hiện tấm bìa Fomo trắng; bên trong bìa Fomo phát hiện các module điện tử.
    3. Phân loại thông minh:
       - Module LM2596 (Board to ~43x21mm, diện tích lớn) -> Khay 2
       - Module TP4056 (Board nhỏ ~28x17mm, diện tích nhỏ) -> Khay 1
    4. Sắp xếp thứ tự gắp: Hàng trước (hạ lưu, cy lớn hơn) gắp trước, hàng sau gắp sau.
    """
    h_roi, w_roi = roi_crop.shape[:2]
    if h_roi < 30 or w_roi < 30:
        return []

    hsv = cv2.cvtColor(roi_crop, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi_crop, cv2.COLOR_BGR2GRAY)

    # 1. Lọc nền băng tải PVC xanh lá (bao gồm cả vùng bóng tối V >= 3)
    lower_green = np.array([30, 20, 3])
    upper_green = np.array([90, 255, 245])
    mask_belt = cv2.inRange(hsv, lower_green, upper_green)

    # Vùng KHÔNG PHẢI màu xanh băng tải (Bìa Fomo + Phôi)
    mask_non_belt = cv2.bitwise_not(mask_belt)

    # Xóa 8px ở 2 biên trái/phải để ngắt hoàn toàn tiếp xúc với thanh nhôm sườn
    if w_roi > 20:
        mask_non_belt[:, :8] = 0
        mask_non_belt[:, -8:] = 0

    kernel_m = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask_clean = cv2.morphologyEx(mask_non_belt, cv2.MORPH_OPEN, kernel_m, iterations=2)
    mask_clean = cv2.morphologyEx(mask_clean, cv2.MORPH_CLOSE, kernel_m, iterations=2)

    contours, _ = cv2.findContours(mask_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 2. Lọc bỏ thành nhôm định hình (dải nhôm hẹp dọc) và đốm bụi
    valid_contours = []
    for cnt in contours:
        a = cv2.contourArea(cnt)
        bx, by, bw, bh = cv2.boundingRect(cnt)
        aspect = max(bw, bh) / max(1, min(bw, bh))

        # Chỉ loại bỏ nếu là dải hẹp dọc (thanh nhôm: bh > 120, bw < 45, aspect > 3.5)
        if bh > 120 and bw < 45 and aspect > 3.5:
            continue
        # Bỏ qua các hạt nhiễu nhỏ
        if a < 1500:
            continue

        # Lọc bỏ bóng đen / nền trống (chỉ giữ vùng có độ sáng rõ rệt):
        sub_cnt = gray[by:by+bh, bx:bx+bw]
        if sub_cnt.size == 0 or sub_cnt.mean() < 40.0:
            continue

        valid_contours.append(cnt)

    # 3. Kiểm tra xem có tấm bìa Fomo trắng thật sự không (> 20.000 px2 và nền sáng)
    fomo_cnt = None
    for cnt in valid_contours:
        if cv2.contourArea(cnt) > 20000:
            fx, fy, fw, fh = cv2.boundingRect(cnt)
            sub_gray = gray[fy:fy+fh, fx:fx+fw]
            if sub_gray.size > 0 and sub_gray.mean() > 130:
                fomo_cnt = cnt
                break

    raw_modules = []

    if fomo_cnt is not None:
        # TRƯỜNG HỢP 1: Có Bìa Fomo Trắng -> Nhận diện các module điện tử TRÊN bìa Fomo
        fx, fy, fw, fh = cv2.boundingRect(fomo_cnt)
        pad = 4
        fy1_c = min(h_roi - 10, fy + pad)
        fy2_c = max(fy1_c + 10, fy + fh - pad)
        fx1_c = min(w_roi - 10, fx + pad)
        fx2_c = max(fx1_c + 10, fx + fw - pad)
        crop_fomo_gray = gray[fy1_c:fy2_c, fx1_c:fx2_c]

        if crop_fomo_gray.size > 0:
            blur_f = cv2.GaussianBlur(crop_fomo_gray, (3, 3), 0)
            _, mask_mod = cv2.threshold(blur_f, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # Xóa viền 3px của mask_mod để tránh viền mép Fomo dính vào phôi
            mask_mod[:3, :] = 0
            mask_mod[-3:, :] = 0
            mask_mod[:, :3] = 0
            mask_mod[:, -3:] = 0

            k_sub = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            mask_mod = cv2.morphologyEx(mask_mod, cv2.MORPH_OPEN, k_sub, iterations=1)
            mask_mod = cv2.morphologyEx(mask_mod, cv2.MORPH_CLOSE, k_sub, iterations=2)

            mod_cnts, _ = cv2.findContours(mask_mod, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for mc in mod_cnts:
                ma = cv2.contourArea(mc)
                if ma < 1500 or ma > (fw * fh * 0.45):
                    continue
                mx, my, mw, mh = cv2.boundingRect(mc)
                aspect = max(mw, mh) / max(1, min(mw, mh))
                if aspect > 4.0:
                    continue

                rect_m = cv2.minAreaRect(mc)
                (mcx, mcy), (mrw, mrh), mangle = rect_m
                l_px = max(mrw, mrh)
                w_px = min(mrw, mrh)
                if w_px < 15:
                    continue

                fomo_cx_full = fx + (fw / 2.0) + rx1
                fomo_cy_full = fy + (fh / 2.0) + ry1

                raw_modules.append({
                    'cx': mcx + fx1_c + rx1,
                    'cy': mcy + fy1_c + ry1,
                    'on_fomo': True,
                    'fomo_cx': fomo_cx_full,
                    'fomo_cy': fomo_cy_full,
                    'bbox': (int(mx + fx1_c + rx1), int(my + fy1_c + ry1), int(mw), int(mh)),
                    'area': ma,
                    'length_px': l_px,
                    'width_px': w_px,
                    'angle': mangle
                })

    # TRƯỜNG HỢP 2: Phôi đặt trực tiếp lên băng tải PVC
    if len(raw_modules) == 0:
        for cnt in valid_contours:
            rect = cv2.minAreaRect(cnt)
            (rcx, rcy), (rw_m, rh_m), angle = rect
            bx, by, bw, bh = cv2.boundingRect(cnt)
            l_px = max(rw_m, rh_m)
            w_px = min(rw_m, rh_m)
            l_mm = l_px * PIXEL_TO_MM_Y
            w_mm = w_px * PIXEL_TO_MM_X

            # Chống nhận diện ảo: Loại bỏ bóng tối khổng lồ (> 52mm) hoặc đốm nhỏ (< 20mm)
            if l_mm < 20.0 or l_mm > 52.0 or w_mm < 10.0 or w_mm > 28.0:
                continue

            # Lọc bóng tối trên băng tải trống: Mạch điện tử thật luôn có linh kiện sáng (mean >= 55, max >= 100)
            sub_cnt = gray[by:by+bh, bx:bx+bw]
            if sub_cnt.size == 0 or sub_cnt.mean() < 55.0 or sub_cnt.max() < 100:
                continue

            raw_modules.append({
                'cx': rcx + rx1,
                'cy': rcy + ry1,
                'bbox': (int(bx + rx1), int(by + ry1), int(bw), int(bh)),
                'area': cv2.contourArea(cnt),
                'length_px': l_px,
                'width_px': w_px,
                'angle': angle
            })

    # Giới hạn tối đa 4 phôi rõ nhất (tránh nhiễu)
    if len(raw_modules) > 4:
        raw_modules.sort(key=lambda m: m['area'], reverse=True)
        raw_modules = raw_modules[:4]

    # Sắp xếp theo chiều trôi băng tải (cy lớn hơn = hạ lưu = gắp trước):
    raw_modules.sort(key=lambda m: m['cy'], reverse=True)

    detected = []
    for idx, m in enumerate(raw_modules, start=1):
        cx_full = m['cx']
        cy_full = m['cy']

        if TRANSFORM_MATRIX is not None:
            # ƯU TIÊN: Dùng ma trận phối cảnh 4 điểm nắn thẳng trực tiếp tọa độ thực của từng phôi
            xr, yr = pixel_to_robot(cx_full, cy_full, img_w, img_h)
        elif m.get('on_fomo', False):
            # Fallback cũ: Tính tọa độ gắp tương đối theo tâm tấm Fomo:
            dx = cx_full - m['fomo_cx']
            dy = cy_full - m['fomo_cy']
            xr = CAM_OFFSET_X - (dy * PIXEL_TO_MM_Y)
            yr = CAM_OFFSET_Y + (dx * PIXEL_TO_MM_X)
            if dx < 0:
                yr += OFFSET_PICK_LEFT_Y
            else:
                yr += OFFSET_PICK_RIGHT_Y
        else:
            xr, yr = pixel_to_robot(cx_full, cy_full, img_w, img_h)

        q1, q2, q3 = IK(xr, yr, Z_PICK)

        # Kích thước mm thực tế chuẩn theo minAreaRect (bất chấp xoay nghiêng):
        dim_length_mm = m['length_px'] * PIXEL_TO_MM_Y
        dim_width_mm  = m['width_px'] * PIXEL_TO_MM_X

        # Chống nhận diện ảo: Bỏ qua nếu kích thước nằm ngoài dải phôi thật
        if dim_length_mm < 20.0 or dim_length_mm > 52.0 or dim_width_mm < 10.0 or dim_width_mm > 28.0:
            continue

        # PHÂN LOẠI THÔNG MINH THEO KÍCH THƯỚC THỰC TẾ (mm):
        # - LM2596: dài ~42.0 mm, rộng ~20.0 mm
        # - TP4056: dài ~28.0 mm, rộng ~17.0 mm
        # Ngưỡng phân định chiều dài: 35.0 mm
        is_lm2596 = (dim_length_mm > 35.0)
        if is_lm2596:
            label = f"LM2596 #{idx}"
            target_box = KHAY_2_POS
            target_name = "Khay 2"
        else:
            label = f"TP4056 #{idx}"
            target_box = KHAY_1_POS
            target_name = "Khay 1"

        detected.append({
            'x_robot': xr,
            'y_robot': yr,
            'cx': int(cx_full),
            'cy': int(cy_full),
            'bbox': m['bbox'],
            'label': label,
            'target_box': target_box,
            'target_name': target_name,
            'area': m['area'],
            'width_mm': dim_width_mm,
            'length_mm': dim_length_mm,
            'ik_angles': (q1, q2, q3) if q1 is not None else (0, 0, 0),
            'ik_valid': q1 is not None
        })

        # Tự động cắt ảnh và đẩy lên Supabase Storage
        is_ng_item = ("ng" in d['cls_name'].lower()) or ("khay 2" in target_name.lower()) or ("lỗi" in d['cls_name'].lower())
        crop_box = None
        try:
            bx1, by1, bx2, by2 = d['bbox']
            crop_box = frame[max(0, by1):min(img_h, by2), max(0, bx1):min(img_w, bx2)].copy()
        except Exception:
            pass
        if is_ng_item:
            push_inspection_async(f"Gói thuốc ({d['cls_name']})", "NG (LỖI)", True, f"X={xr:.1f}mm, Y={yr:.1f}mm", crop_frame=crop_box)

    return detected

def detect_objects_yolo(frame, rx1, ry1, rw, rh, img_w, img_h):
    """
    NHẬN DIỆN & PHÂN LOẠI PHÔI BẰNG YOLO VÀ QUY ĐỔI TỌA ĐỘ THEO CHUẨN TEST2206.py:
    1. Chạy suy luận YOLO trên khung hình ROI băng tải.
    2. Lấy bounding box (bx1, by1, bx2, by2), tính tâm phôi:
       cx = (bx1 + bx2) / 2.0 + rx1
       cy = (by1 + by2) / 2.0 + ry1
    3. Quy đổi tâm phôi (cx, cy) sang tọa độ Robot (X, Y mm) bằng pixel_to_robot (Perspective Transform).
    4. Phân loại gắp vào Khay 1 hoặc Khay 2 theo Class Name của YOLO.
    5. Sắp xếp thứ tự phôi theo chiều trôi băng tải (cy lớn hơn = hạ lưu = gắp trước).
    """
    if YOLO_MODEL is None or frame is None or frame.size == 0:
        return []

    try:
        # Suy luận YOLO trực tiếp trên toàn khung hình gốc 640x480 (khớp 100% với ảnh train không crop)
        results = YOLO_MODEL.predict(frame, conf=YOLO_CONF_THRESH, verbose=False)
    except Exception as e:
        return []

    rx2 = rx1 + rw
    ry2 = ry1 + rh

    raw_detections = []
    for r in results:
        boxes = getattr(r, 'boxes', None)
        if boxes is None or len(boxes) == 0:
            continue
        for box in boxes:
            try:
                xyxy = box.xyxy[0].cpu().numpy()
                bx1, by1, bx2, by2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])
                conf = float(box.conf[0].cpu().numpy())
                cls_id = int(box.cls[0].cpu().numpy())
                cls_name = YOLO_MODEL.names.get(cls_id, str(cls_id)) if hasattr(YOLO_MODEL, 'names') else str(cls_id)
            except Exception:
                continue

            cx_full = (bx1 + bx2) / 2.0
            cy_full = (by1 + by2) / 2.0
            bw = bx2 - bx1
            bh = by2 - by1

            # Lọc chỉ giữ các phôi nằm trong lòng vùng băng tải (ROI):
            # Bỏ qua mọi vật thể nằm ngoài bàn hoặc ngoài băng tải
            if not (rx1 - 8 <= cx_full <= rx2 + 8 and ry1 - 8 <= cy_full <= ry2 + 8):
                continue

            raw_detections.append({
                'cx': cx_full,
                'cy': cy_full,
                'bbox': (int(bx1), int(by1), int(bw), int(bh)),
                'conf': conf,
                'cls_id': cls_id,
                'cls_name': cls_name,
                'bw': bw,
                'bh': bh
            })

    # Giới hạn tối đa 4 phôi rõ nhất
    if len(raw_detections) > 4:
        raw_detections.sort(key=lambda m: m['conf'], reverse=True)
        raw_detections = raw_detections[:4]

    # Sắp xếp theo chiều trôi băng tải (cy lớn hơn = hạ lưu = gắp trước):
    raw_detections.sort(key=lambda m: m['cy'], reverse=True)

    detected = []
    for idx, d in enumerate(raw_detections, start=1):
        cx_full = d['cx']
        cy_full = d['cy']

        # Quy đổi tọa độ theo chuẩn TEST2206.py (Perspective Transform)
        xr, yr = pixel_to_robot(cx_full, cy_full, img_w, img_h)
        q1, q2, q3 = IK(xr, yr, Z_PICK)

        # Phân loại theo Class Name của YOLO
        cls_key = d['cls_name'].lower().strip()
        mapping = None
        for k, v in YOLO_CLASS_MAPPING.items():
            if k in cls_key:
                mapping = v
                break

        if mapping is not None:
            target_box = mapping['box']
            target_name = mapping['name']
        elif d['cls_id'] == 0:
            target_box = KHAY_1_POS
            target_name = "Khay 1"
        else:
            target_box = KHAY_2_POS
            target_name = "Khay 2"

        label = f"{d['cls_name']} ({d['conf']*100:.0f}%)"

        detected.append({
            'x_robot': xr,
            'y_robot': yr,
            'cx': int(cx_full),
            'cy': int(cy_full),
            'bbox': d['bbox'],
            'label': label,
            'target_box': target_box,
            'target_name': target_name,
            'area': d['bw'] * d['bh'],
            'width_mm': d['bw'] * PIXEL_TO_MM_X,
            'length_mm': d['bh'] * PIXEL_TO_MM_Y,
            'ik_angles': (q1, q2, q3) if q1 is not None else (0, 0, 0),
            'ik_valid': q1 is not None
        })

    return detected

def vision_worker():
    """Luồng đọc Camera liên tục"""
    cap = None
    try:
        from pypylon import pylon
        tl_factory = pylon.TlFactory.GetInstance()
        devices = tl_factory.EnumerateDevices()
        if len(devices) > 0:
            camera = pylon.InstantCamera(tl_factory.CreateFirstDevice())
            camera.Open()
            camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            converter = pylon.ImageFormatConverter()
            converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            print("📷 [CAMERA] Đã kết nối Basler Pylon thành công!")

            prev_t = time.time()
            while shared_vision['running']:
                if camera.IsGrabbing():
                    grab_result = camera.RetrieveResult(2000, pylon.TimeoutHandling_Return)
                    if grab_result and grab_result.GrabSucceeded():
                        img = converter.Convert(grab_result).GetArray()
                        grab_result.Release()
                        _process_frame(img)
                        curr_t = time.time()
                        shared_vision['fps'] = 1.0 / max(0.001, curr_t - prev_t)
                        prev_t = curr_t
            camera.StopGrabbing()
            camera.Close()
            return
    except Exception:
        pass

    # Fallback OpenCV USB Camera
    for idx in [0, 1]:
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            print(f"📷 [CAMERA] Dùng OpenCV VideoCapture({idx})")
            break

    if cap is None or not cap.isOpened():
        print("⚠️ [CAMERA] Không tìm thấy camera, chạy khung hình giả lập.")
        while shared_vision['running']:
            dummy = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(dummy, "CAMERA SIMULATION", (180, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            _process_frame(dummy)
            time.sleep(0.05)
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    prev_t = time.time()

    while shared_vision['running']:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.02)
            continue
        _process_frame(frame)
        curr_t = time.time()
        shared_vision['fps'] = 1.0 / max(0.001, curr_t - prev_t)
        prev_t = curr_t

    cap.release()

def _process_frame(frame):
    h, w = frame.shape[:2]
    rx, ry, rw, rh = shared_vision['roi_rect']
    rx = max(0, min(rx, w - 20))
    ry = max(0, min(ry, h - 20))
    rw = max(20, min(rw, w - rx))
    rh = max(20, min(rh, h - ry))

    if YOLO_MODEL is not None:
        targets = detect_objects_yolo(frame, rx, ry, rw, rh, w, h)
    else:
        crop = frame[ry:ry+rh, rx:rx+rw]
        targets = detect_objects_in_roi(crop, rx, ry, w, h)

    with shared_vision['lock']:
        shared_vision['frame'] = frame
        shared_vision['detected_targets'] = targets


# =============================================================================
# 9. GIAO DIỆN CHÍNH & VÒNG LẶP SỰ KIỆN
# =============================================================================
def main():
    print("=" * 70)
    print("🤖 KHỞI CHẠY HỆ THỐNG CÁNH TAY ROBOT 3-DOF (CHUẨN DESCARTES)")
    print("=" * 70)

    # 1. Kết nối PLC
    plc.connect()

    # 2. Đưa Robot về vị trí HOME / Chờ ban đầu
    print(f"🏠 Đưa Robot về vị trí Home ban đầu: {HOME_POS} mm...")
    plc.move_to_xyz(HOME_POS[0], HOME_POS[1], HOME_POS[2], speed=25.0, wait_time=1.5)

    # 3. Khởi chạy luồng Vision & Giám sát cảm biến
    threading.Thread(target=vision_worker, daemon=True).start()
    threading.Thread(target=plc_sensor_monitor_worker, daemon=True).start()

    print("\n🎮 PHÍM TẮT ĐIỀU KHIỂN:")
    print("   • [ CLICK CHUỘT ] : Click bất kỳ điểm nào trên ảnh để giải góc IK tức thời")
    print("   • [ C ]           : Kéo chuột khoanh chọn Vùng Băng Tải Xanh (Lưu tự động)")
    print("   • [ SPACE ]       : Giả lập CB2 (%I0.4) -> Kích gắp phôi ngay lập tức")
    print("   • [ 1 ]           : Giả lập CB1 (%I0.3) -> Quét phôi tại trạm Camera")
    print("   • [ G ]           : Gắp tức thời điểm Click chuột / Phôi theo Động Học Nghịch (IK)")
    print("   • [ Y ]           : Nạp lại mô hình YOLO (best.pt)")
    print("   • [ T ]           : Nạp lại Ma trận hiệu chuẩn (calibration.json)")
    print("   • [ B ]           : Bật / Tắt Bơm hút chân không (%Q1.0)")
    print("   • [ H ]           : Về vị trí Home/Chờ an toàn")
    print("   • [ Q ]           : Thoát chương trình\n")

    win_name = "HE THONG CANH TAY ROBOT 3-DOF"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 800, 600)

    roi_tool = {'selecting': False, 'dragging': False, 'p1': (0, 0), 'p2': (0, 0)}

    def on_mouse(event, x, y, flags, param):
        if roi_tool['selecting']:
            if event == cv2.EVENT_LBUTTONDOWN:
                roi_tool['dragging'] = True
                roi_tool['p1'] = (x, y)
                roi_tool['p2'] = (x, y)
            elif event == cv2.EVENT_MOUSEMOVE and roi_tool['dragging']:
                roi_tool['p2'] = (x, y)
            elif event == cv2.EVENT_LBUTTONUP and roi_tool['dragging']:
                roi_tool['dragging'] = False
                roi_tool['selecting'] = False
                x1, y1 = roi_tool['p1']
                x2, y2 = x, y
                rx = min(x1, x2)
                ry = min(y1, y2)
                rw = abs(x2 - x1)
                rh = abs(y2 - y1)
                if rw > 30 and rh > 30:
                    with shared_vision['lock']:
                        shared_vision['roi_rect'] = [rx, ry, rw, rh]
                    save_roi_config(rx, ry, rw, rh)
                    print(f"✅ [ROI] Đã chọn xong vùng băng tải: X={rx}, Y={ry}, Ngang={rw}px, Dài={rh}px!")
            return

        if event == cv2.EVENT_LBUTTONDOWN:
            xr, yr = pixel_to_robot(x, y)
            q1, q2, q3 = IK(xr, yr, Z_PICK)
            if q1 is not None:
                plc_x, plc_y, plc_z = angles_to_plc(q1, q2, q3)
                print(f"\n🖱️ [CLICK IK] Pixel=({x}, {y}) -> Robot=({xr:.1f}, {yr:.1f}, {Z_PICK:.1f}) mm")
                print(f"   👉 Góc IK: q1={q1:.2f}°, q2={q2:.2f}°, q3={q3:.2f}°")
                print(f"   👉 Trục PLC: Đế={plc_z:.2f}°, Vai={plc_y:.2f}°, Khuỷu={plc_x:.2f}°")
            else:
                print(f"\n⚠️ [CLICK] Vị trí ({xr:.1f}, {yr:.1f}) mm ngoài tầm với!")

            with shared_vision['lock']:
                shared_vision['manual_target'] = {
                    'label': 'CLICK_TEST',
                    'x_robot': xr,
                    'y_robot': yr,
                    'cx': x,
                    'cy': y,
                    'ik_angles': (q1, q2, q3) if q1 is not None else (0, 0, 0),
                    'ik_valid': q1 is not None
                }

    cv2.setMouseCallback(win_name, on_mouse)

    while True:
        frame_in = None
        targets = []
        with shared_vision['lock']:
            if shared_vision['frame'] is not None:
                frame_in = shared_vision['frame'].copy()
                targets = list(shared_vision['detected_targets'])
                roi_rect = list(shared_vision['roi_rect'])
                fps = shared_vision['fps']

        if frame_in is None:
            time.sleep(0.01)
            continue

        h_f, w_f = frame_in.shape[:2]

        # 1. Vẽ khung ROI
        rx, ry, rw, rh = roi_rect
        cv2.rectangle(frame_in, (rx, ry), (rx + rw, ry + rh), (0, 220, 255), 2)
        cv2.putText(frame_in, f"ROI BANG TAI: {rw}x{rh}px", (rx + 5, max(18, ry - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1)

        # Nếu đang kéo chuột chọn ROI
        if roi_tool['selecting']:
            if roi_tool['dragging']:
                p1 = roi_tool['p1']
                p2 = roi_tool['p2']
                cv2.rectangle(frame_in, p1, p2, (0, 255, 255), 2)
            cv2.putText(frame_in, "DANG KEO CHUOT CHON VUNG BANG TAI...", (16, h_f - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

        # 2. Vẽ các phôi nhận diện được
        for tg in targets:
            bx, by, bw, bh = tg['bbox']
            is_lm = "LM2596" in tg.get('label', '')
            box_col = (0, 140, 255) if is_lm else (255, 220, 0) # Cam cho LM2596, Cyan cho TP4056
            cv2.rectangle(frame_in, (bx, by), (bx + bw, by + bh), box_col, 2)
            cv2.circle(frame_in, (tg['cx'], tg['cy']), 4, (0, 0, 255), -1)
            khay_tag = tg.get('target_name', 'Khay')
            cv2.putText(frame_in, f"{tg['label']} -> {khay_tag}",
                        (bx, max(18, by - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, box_col, 1)
            if tg.get('ik_valid'):
                q1, q2, q3 = tg['ik_angles']
                cv2.putText(frame_in, f"IK: {q1:.0f}\xb0,{q2:.0f}\xb0,{q3:.0f}\xb0",
                            (bx, by + bh + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1)
            # Hiển thị kích thước thực tế mm và pixel đo được trực tiếp
            w_mm = tg.get('width_mm', bw * PIXEL_TO_MM_X)
            l_mm = tg.get('length_mm', bh * PIXEL_TO_MM_Y)
            cv2.putText(frame_in, f"{l_mm:.1f}x{w_mm:.1f}mm ({bw}x{bh}px)",
                        (bx, by + bh + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (120, 255, 120), 1)

        # 3. Vẽ điểm click thủ công nếu có
        man_t = shared_vision.get('manual_target')
        if man_t is not None:
            mcx, mcy = man_t['cx'], man_t['cy']
            cv2.drawMarker(frame_in, (mcx, mcy), (0, 0, 255), markerType=cv2.MARKER_CROSS, markerSize=16, thickness=2)
            cv2.putText(frame_in, f"CLICK: ({man_t['x_robot']:.1f}, {man_t['y_robot']:.1f})",
                        (mcx + 8, mcy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 255), 1)

        # 4. Vẽ bảng Dashboard OSD nhỏ gọn
        cv2.rectangle(frame_in, (10, 10), (280, 130), (20, 20, 20), -1)
        cv2.rectangle(frame_in, (10, 10), (280, 130), (80, 80, 80), 1)

        plc_str = "PLC: ONLINE" if plc.connected else "PLC: OFFLINE"
        plc_col = (0, 255, 0) if plc.connected else (0, 165, 255)
        cv2.putText(frame_in, plc_str, (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.42, plc_col, 1)
        cv2.putText(frame_in, f"{fps:.0f} FPS", (210, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)

        cv2.putText(frame_in, f"STATUS: {robot_state.current_state}", (16, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 255, 255), 1)
        cx, cy, cz = robot_state.current_xyz
        cv2.putText(frame_in, f"XYZ: {cx:.1f}, {cy:.1f}, {cz:.1f} mm", (16, 68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 255), 1)
        pump_str = "BOM: ON" if robot_state.vacuum_state else "BOM: OFF"
        pump_col = (0, 255, 0) if robot_state.vacuum_state else (150, 150, 150)
        cv2.putText(frame_in, pump_str, (16, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.40, pump_col, 1)

        calib_str = f"CALIB: 4-PT ({CALIB_OFFSET_X:+.0f},{CALIB_OFFSET_Y:+.0f})" if TRANSFORM_MATRIX is not None else "CALIB: LINEAR (OLD)"
        calib_col = (0, 255, 255) if TRANSFORM_MATRIX is not None else (180, 180, 180)
        cv2.putText(frame_in, calib_str, (16, 106), cv2.FONT_HERSHEY_SIMPLEX, 0.38, calib_col, 1)

        det_mode = "MODE: YOLO" if YOLO_MODEL is not None else "MODE: OPENCV"
        det_col = (255, 180, 0) if YOLO_MODEL is not None else (200, 200, 200)
        cv2.putText(frame_in, det_mode, (16, 122), cv2.FONT_HERSHEY_SIMPLEX, 0.36, det_col, 1)

        cv2.imshow(win_name, frame_in)
        key = cv2.waitKey(1) & 0xFF

        if key in [ord('q'), ord('Q'), 27]:
            print("\n🛑 Thoát chương trình.")
            break
        elif key in [ord('c'), ord('C')]:
            roi_tool['selecting'] = True
            print("\n🖱️ [CHỌN ROI] Hãy dùng chuột kéo khoanh vùng mặt băng tải xanh trên camera!")
        elif key == ord(' '):
            print("\n⌨️ [SPACE] Giả lập CB2 -> Kích gắp phôi!")
            on_sensor_cb2_triggered()
        elif key == ord('1'):
            print("\n⌨️ [PHÍM 1] Giả lập CB1 -> Quét phôi!")
            on_sensor_cb1_triggered()
        elif key in [ord('y'), ord('Y')]:
            print("\n🔄 [PHÍM Y] Đang nạp lại Mô hình YOLO...")
            load_yolo_model()
        elif key in [ord('t'), ord('T')]:
            print("\n🔄 [PHÍM T] Đang nạp lại Ma trận Hiệu chuẩn...")
            load_calibration_config()
        elif key in [ord('g'), ord('G')]:
            man_t = shared_vision.get('manual_target')
            with shared_vision['lock']:
                curr_targets = list(shared_vision['detected_targets'])

            target_to_pick = None
            if man_t is not None:
                target_to_pick = man_t
                print(f"\n🦾 [PHÍM G] GẮP THEO ĐỘNG HỌC NGHỊCH IK TẠI ĐIỂM CLICK: ({man_t['x_robot']:.1f}, {man_t['y_robot']:.1f}) mm...")
            elif len(curr_targets) > 0:
                target_to_pick = curr_targets[0]
                print(f"\n🦾 [PHÍM G] GẮP THEO ĐỘNG HỌC NGHỊCH IK PHÔI CAMERA: ({target_to_pick['x_robot']:.1f}, {target_to_pick['y_robot']:.1f}) mm...")
            else:
                print("\n⚠️ [PHÍM G] Hãy dùng chuột click vào 1 điểm trên camera hoặc đặt phôi vào để gắp!")

            if target_to_pick is not None:
                if robot_state.is_busy:
                    print("⚠️ Robot đang bận chu trình trước, vui lòng chờ!")
                else:
                    def run_g_pick():
                        robot_state.is_busy = True
                        try:
                            execute_pick_and_place(target_to_pick['x_robot'], target_to_pick['y_robot'], KHAY_1_POS, item_name=target_to_pick.get('label', 'IK_TEST'))
                        finally:
                            robot_state.is_busy = False
                    threading.Thread(target=run_g_pick, daemon=True).start()
        elif key in [ord('h'), ord('H')]:
            print("\n⌨️ [PHÍM H] Về vị trí Home...")
            plc.move_to_xyz(HOME_POS[0], HOME_POS[1], HOME_POS[2], wait_time=1.5)
        elif key in [ord('b'), ord('B')]:
            new_state = not robot_state.vacuum_state
            plc.set_vacuum(new_state)
            print(f"⌨️ [PHÍM B] Bơm hút: {'ON' if new_state else 'OFF'}")

    shared_vision['running'] = False
    plc.set_vacuum(False)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()