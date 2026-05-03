import cv2
import numpy as np
from ultralytics import YOLO
import snap7
from snap7.util import set_bool
import threading

# Khóa để đồng bộ luồng khi truy cập PLC
plc_lock = threading.Lock()

# ==============================
# CẤU HÌNH PLC S7-1200
# ==============================
PLC_IP = '192.168.1.50'  # Thay bằng IP thực tế của PLC
PLC_RACK = 0
PLC_SLOT = 1
DB_NUMBER = 1           # Số thứ tự của Data Block (ví dụ DB1)
START_OFFSET = 0        # Địa chỉ Offset bắt đầu
BIT_OFFSET = 0          # Bit 0 (tương ứng DB1.DBX0.0) - Gửi kết quả
SENSOR_BIT_OFFSET = 1   # Bit 1 (tương ứng DB1.DBX0.1) - Đọc cảm biến
CONVEYOR_BIT_OFFSET = 2 # Bit 2 (tương ứng DB1.DBX0.2) - Điều khiển băng tải
SYSTEM_ACTIVE_BIT_OFFSET = 3 # Bit 3 (tương ứng DB1.DBX0.3) - Trạng thái hệ thống (Start/Stop)
OK_BIT_OFFSET = 4       # Bit 4 (tương ứng DB1.DBX0.4) - Tín hiệu sản phẩm ĐẠT
CAM_ONLINE_BIT_OFFSET = 5 # Bit 5 (tương ứng DB1.DBX0.5) - Trạng thái Camera từ PC

# --- ĐỊA CHỈ LƯU SỐ LƯỢNG (DẠNG WORD/INT) ---
OK_COUNT_OFFSET    = 2   # DB1.DBW2  - Tổng OK
NG_COUNT_OFFSET    = 4   # DB1.DBW4  - Tổng NG
TOTAL_COUNT_OFFSET = 6   # DB1.DBW6  - Tổng tất cả
PRODUCT_ID_OFFSET  = 8   # DB1.DBW8  - Mã sản phẩm (1=Viên, 2=Vỉ)

# --- THỐNG KÊ RIÊNG TỮNG LOẠI SẢN PHẨM ---
# (DB1 cần đủ 20 byte - kiểm tra trong TIA Portal)
VIEN_OK_OFFSET = 10  # DB1.DBW10 - Viên rời OK
VIEN_NG_OFFSET = 12  # DB1.DBW12 - Viên rời NG
VI_OK_OFFSET   = 14  # DB1.DBW14 - Vỉ thuốc OK
VI_NG_OFFSET   = 16  # DB1.DBW16 - Vỉ thuốc NG
REMOTE_CONTROL_OFFSET = 18  # DB1.DBW18 - Chế độ điều khiển (1=Remote, 0=Local)

# Khởi tạo kết nối PLC
plc_client = snap7.client.Client()

def connect_to_plc():
    try:
        if not plc_client.get_connected():
            plc_client.connect(PLC_IP, PLC_RACK, PLC_SLOT)
        
        # Kiểm tra thực tế bằng cách thử đọc 1 byte. 
        # Nếu rút dây mạng, hàm db_read sẽ văng lỗi ngay lập tức.
        if plc_client.get_connected():
            plc_client.db_read(DB_NUMBER, 0, 1) 
            return True
        return False
    except Exception as e:
        # Nếu có lỗi (do rút dây), đảm bảo ngắt kết nối hẳn để lần sau connect lại
        disconnect_plc()
        print(f"--- LỖI KẾT NỐI PLC THỰC TẾ: {e} ---")
        print(f"--- LỖI KẾT NỐI PLC CHI TIẾT: {e} ---")
        if "CPU : Address out of range" in str(e):
            print(">>> Gợi ý: Hãy kiểm tra xem bạn đã tắt 'Optimized block access' cho DB1 chưa.")
        elif "Security" in str(e) or "Refused" in str(e) or "ISO" in str(e):
            print(">>> Gợi ý: Hãy kiểm tra xem bạn đã bật 'Permit access with PUT/GET' trong PLC chưa.")
        return False

def disconnect_plc():
    """Bắt buộc ngắt kết nối để làm sạch socket khi mất mạng"""
    try:
        plc_client.disconnect()
    except:
        pass

def read_sensor_trigger():
    """Đọc trạng thái cảm biến (Trigger) từ PLC"""
    with plc_lock:
        try:
            if not plc_client.get_connected():
                raise Exception("Mất kết nối PLC ngầm")
            # Đọc 1 byte từ DB bắt đầu từ START_OFFSET
            data = plc_client.db_read(DB_NUMBER, START_OFFSET, 1)
            # Lấy giá trị của bit cảm biến (Bit 1)
            return snap7.util.get_bool(data, 0, SENSOR_BIT_OFFSET)
        except Exception as e:
            print(f"Lỗi đọc cảm biến PLC: {e}")
            raise e
    return False

def send_product_id_to_plc(product_id):
    """Gửi mã sản phẩm xuống PLC (1=Viên, 2=Vỉ) để đồng bộ với Web"""
    with plc_lock:
        try:
            if plc_client.get_connected():
                # Ghi vào DB1.DBW8 (PRODUCT_ID_OFFSET = 8)
                data = bytearray(2)
                snap7.util.set_int(data, 0, product_id)
                plc_client.db_write(DB_NUMBER, PRODUCT_ID_OFFSET, data)
                # print(f"PLC: Đã đồng bộ mã sản phẩm ID={product_id}")
        except Exception as e:
            print(f"Lỗi gửi ProductID xuống PLC: {e}")
            
def read_system_status():
    """Đọc trạng thái hệ thống (Start/Stop) từ PLC"""
    with plc_lock:
        try:
            if not plc_client.get_connected():
                raise Exception("Mất kết nối PLC ngầm")
            data = plc_client.db_read(DB_NUMBER, START_OFFSET, 1)
            return snap7.util.get_bool(data, 0, SYSTEM_ACTIVE_BIT_OFFSET)
        except Exception as e:
            print(f"Lỗi khi đọc trạng thái hệ thống: {e}")
            raise e
    return False

def send_result_to_plc(is_error, is_ok=False, num_ok=-1, num_ng=-1, num_total=-1):
    """Gửi tín hiệu và số lượng xuống PLC"""
    with plc_lock:
        try:
            if plc_client.get_connected():
                # 1. Gửi các Bit trạng thái (Đèn, Xi lanh) - Byte 0
                data_bits = plc_client.db_read(DB_NUMBER, START_OFFSET, 1)
                set_bool(data_bits, 0, BIT_OFFSET, is_error)
                set_bool(data_bits, 0, OK_BIT_OFFSET, is_ok)
                plc_client.db_write(DB_NUMBER, START_OFFSET, data_bits)

                # 2. Gửi các con số (Word - 2 bytes mỗi số) - Bắt đầu từ Byte 2
                if num_ok != -1:
                    ok_bytes = bytearray(2)
                    snap7.util.set_int(ok_bytes, 0, num_ok)
                    plc_client.db_write(DB_NUMBER, OK_COUNT_OFFSET, ok_bytes)

                if num_ng != -1:
                    ng_bytes = bytearray(2)
                    snap7.util.set_int(ng_bytes, 0, num_ng)
                    plc_client.db_write(DB_NUMBER, NG_COUNT_OFFSET, ng_bytes)

                if num_total != -1:
                    total_bytes = bytearray(2)
                    snap7.util.set_int(total_bytes, 0, num_total)
                    plc_client.db_write(DB_NUMBER, TOTAL_COUNT_OFFSET, total_bytes)
                
                # print(f"PLC Sync: OK={num_ok}, NG={num_ng}, Total={num_total}")
        except Exception as e:
            print(f"Lỗi khi gửi dữ liệu xuống PLC: {e}")


def read_product_id_from_plc():
    """Đọc mã sản phẩm từ PLC (1=Viên, 2=Vỉ)"""
    with plc_lock:
        try:
            if plc_client.get_connected():
                data = plc_client.db_read(DB_NUMBER, PRODUCT_ID_OFFSET, 2)
                return snap7.util.get_int(data, 0)
        except:
            pass
    return 0



def send_product_specific_counts(product_name, ok_count, ng_count):
    """
    Ghi số lượng OK/NG riêng từng loại sản phẩm lên PLC để ESP32 đọc.
    - product_name: 'Viên rời' hoặc 'Vỉ thuốc'
    - ok_count: số lượng đạt của loại sản phẩm đó
    - ng_count: số lượng lỗi của loại sản phẩm đó
    """
    with plc_lock:
        try:
            if not plc_client.get_connected():
                return

            if product_name == "Viên rời":
                # Ghi vào DB1.DBW10 (Viên OK) và DB1.DBW12 (Viên NG)
                ok_bytes = bytearray(2)
                snap7.util.set_int(ok_bytes, 0, ok_count)
                plc_client.db_write(DB_NUMBER, VIEN_OK_OFFSET, ok_bytes)

                ng_bytes = bytearray(2)
                snap7.util.set_int(ng_bytes, 0, ng_count)
                plc_client.db_write(DB_NUMBER, VIEN_NG_OFFSET, ng_bytes)

            elif product_name == "Vỉ thuốc":
                # Ghi vào DB1.DBW14 (Vỉ OK) và DB1.DBW16 (Vỉ NG)
                ok_bytes = bytearray(2)
                snap7.util.set_int(ok_bytes, 0, ok_count)
                plc_client.db_write(DB_NUMBER, VI_OK_OFFSET, ok_bytes)

                ng_bytes = bytearray(2)
                snap7.util.set_int(ng_bytes, 0, ng_count)
                plc_client.db_write(DB_NUMBER, VI_NG_OFFSET, ng_bytes)

        except Exception as e:
            print(f"Lỗi ghi thống kê riêng xuống PLC: {e}")

def set_conveyor_state(is_running):
    """Bật/Tắt băng tải"""
    with plc_lock:
        try:
            if plc_client.get_connected():
                data = plc_client.db_read(DB_NUMBER, START_OFFSET, 1)
                set_bool(data, 0, CONVEYOR_BIT_OFFSET, is_running)
                plc_client.db_write(DB_NUMBER, START_OFFSET, data)
                print(f"Băng tải: {'CHẠY' if is_running else 'DỪNG'}", flush=True)
        except Exception as e:
            print(f"Lỗi khi điều khiển băng tải: {e}", flush=True)

def send_camera_status_to_plc(is_online):
    """Gửi trạng thái Camera từ PC xuống PLC để ESP32 đọc"""
    with plc_lock:
        try:
            if plc_client.get_connected():
                data = plc_client.db_read(DB_NUMBER, START_OFFSET, 1)
                set_bool(data, 0, CAM_ONLINE_BIT_OFFSET, is_online)
                plc_client.db_write(DB_NUMBER, START_OFFSET, data)
        except:
            pass

def write_bit_to_plc(byte_offset, bit_offset, value):
    """Ghi giá trị một bit (True/False) vào PLC tại vị trí mong muốn"""
    with plc_lock:
        try:
            if plc_client.get_connected():
                # Đọc byte hiện tại từ PLC để không ghi đè các bit khác
                data = plc_client.db_read(DB_NUMBER, byte_offset, 1)
                # Thiết lập giá trị bit mong muốn (0-7)
                snap7.util.set_bool(data, 0, bit_offset, value)
                # Ghi byte đã sửa đổi trở lại PLC
                plc_client.db_write(DB_NUMBER, byte_offset, data)
        except Exception as e:
            # Không print lỗi quá nhiều để tránh làm chậm hệ thống
            pass

def read_iot_data():
    """Đọc dữ liệu thống kê từ DB2 (Data Block số 2)"""
    with plc_lock:
        try:
            if plc_client.get_connected():
                # Đọc 8 byte từ DB2 bắt đầu từ offset 0
                raw_data = plc_client.db_read(2, 0, 8) 
                tong = snap7.util.get_int(raw_data, 0)
                ok = snap7.util.get_int(raw_data, 2)
                ng = snap7.util.get_int(raw_data, 4)
                stt = snap7.util.get_int(raw_data, 6)
                return tong, ok, ng, stt
        except Exception as e:
            pass
    return 0, 0, 0, 0

# ==============================
# DANH MỤC CLASS & CẤU HÌNH YOLO
# ==============================

# --- CLASS MODEL VIÊN RỜI (Các nhãn bị coi là LỖI) ---
DANH_MUC_LOI_VIEN = ['di_vat', 'di vat', 'vo', 'nut', 'hong', 'error', 'ng', 'vat the la']

# --- CLASS MODEL VỈ THUỐC ---
# Class này là vỉ BÌNH THƯỜNG (OK) - không phải lỗi
VI_THUOC_OK_CLASS   = 'vi_thuoc'
# Các class này là LỖI trên vỉ
VI_THUOC_NG_CLASSES = ['thieu_vien', 'nut_vo', 'di_vat']

# Tên hiển thị thân thiện cho từng loại lỗi
VI_THUOC_NG_LABELS = {
    'thieu_vien': 'Thiếu viên',
    'nut_vo'    : 'Nứt/Vỡ viên',
    'di_vat'    : 'Dị vật',
}

# --- SỐ VIÊN CHUẨN CHO MỖI VỈ (Model hiện tại nhận diện nguyên vỉ là 1 vật thể) ---
SO_VIEN_CHUAN_VI = 1

CONF_THRESHOLD = 0.5
def apply_static_crop(frame):
    h, w = frame.shape[:2]
    # Mở rộng vùng quét để tránh mất viên ở rìa vỉ
    x1, x2 = int(w * 0.15), int(w * 0.85)
    y1, y2 = int(h * 0.05), int(h * 0.95)
    cropped = frame[y1:y2, x1:x2]
    return cropped

def load_model(model_path):
    print(f"Đang tải model từ: {model_path}...")
    model = YOLO(model_path)
    class_names = model.names
    print("Danh sách nhãn nhận diện:", class_names)
    return model, class_names

# ==============================
# XỬ LÝ FRAME & KẾT NỐI LOGIC
# ==============================
def process_frame(frame, model, class_names, conf_threshold=None):
    if conf_threshold is None:
        conf_threshold = CONF_THRESHOLD
        
    frame_to_detect = apply_static_crop(frame)
    # Sử dụng conf_threshold truyền vào để lọc ngay từ bước detect của YOLO
    results = model(frame_to_detect, imgsz=640, conf=conf_threshold, verbose=False)
    result = results[0]
    annotated = result.plot()

    status_text = "Không thấy sản phẩm"
    result_code = "CHỜ VẬT THỂ"
    is_error = False
    details = []
    
    num_ok = 0
    num_ng = 0
    loi_chi_tiet = []
    loi_hien_thi = []

    # Biến đếm riêng cho vỉ thuốc
    count_vi_thuoc   = 0  # Số slot/viên detect được trên vỉ (dùng để phát hiện vỉ bị cắt)
    count_thieu_vien = 0  # Số ô bị thiếu viên (pill trong slot bị lấy ra)
    count_nut_vo     = 0  # Số viên nứt/vỡ
    count_di_vat     = 0  # Số dị vật

    # --- Nhận diện tự động: Model vỉ hay model viên rời? ---
    # Nếu class_names chứa 'vi_thuoc' => đây là model vỉ thuốc
    all_classes = [v.lower().strip() for v in class_names.values()]
    is_vi_thuoc_model = VI_THUOC_OK_CLASS in all_classes

    if result.boxes is not None and len(result.boxes) > 0:
        for box in result.boxes:
            raw_label = class_names[int(box.cls[0])]
            label = raw_label.lower().strip()
            conf = float(box.conf[0])
            
            # Đã lọc conf ở hàm model() phía trên, nhưng kiểm tra lại cho chắc chắn
            if conf < conf_threshold:
                continue

            if is_vi_thuoc_model:
                # ===== LOGIC MODEL VỈ THUỐC =====
                if label == VI_THUOC_OK_CLASS:
                    count_vi_thuoc += 1  # Đếm số slot/viên nhìn thấy trên vỉ
                elif label == 'thieu_vien':
                    count_vi_thuoc   += 1  # Vẫn là 1 slot, nhưng bị lấy viên ra
                    count_thieu_vien += 1
                    num_ng += 1
                elif label == 'nut_vo':
                    count_vi_thuoc += 1
                    count_nut_vo += 1
                    num_ng += 1
                elif label == 'di_vat':
                    count_di_vat += 1
                    num_ng += 1
            else:
                # ===== LOGIC MODEL VIÊN RỜI =====
                # Sửa logic: So sánh khớp hoàn toàn nhãn lỗi để tránh nhầm lẫn
                is_ng_class = label in [err.lower().strip() for err in DANH_MUC_LOI_VIEN]
                if is_ng_class:
                    num_ng += 1
                    if raw_label not in loi_chi_tiet:
                        loi_chi_tiet.append(raw_label)
                        loi_hien_thi.append(raw_label)
                else:
                    num_ok += 1

        # --- Xây dựng kết quả cho VỈ THUỐC ---
        if is_vi_thuoc_model:
            loi_list = []  # Danh sách mô tả lỗi

            # 1️⃣ Kiểm tra các lỗi vật lý (Nếu model phát hiện ra các nhãn lỗi)
            if count_thieu_vien > 0:
                loi_list.append(f"Thiếu viên trong ô: {count_thieu_vien} ô")
            if count_nut_vo > 0:
                loi_list.append(f"Nứt/Vỡ: {count_nut_vo} viên")
            if count_di_vat > 0:
                loi_list.append(f"Dị vật: {count_di_vat} chỗ")

            # 2️⃣ Phán định cuối cùng: Chỉ cần thấy vỉ và không có lỗi vật lý là đạt
            if loi_list:
                status_text = f"LỖI VỈ: {' | '.join(loi_list).upper()}"
                result_code  = "NG - " + " | ".join(loi_list)
                is_error = True
                details = [f"Phát hiện vỉ có lỗi: {len(loi_list)} loại lỗi"] + [f"  • {l}" for l in loi_list]
            elif count_vi_thuoc > 0:
                status_text = "VỈ THUỐC ĐẠT CHUẨN"
                result_code  = "SẢN PHẨM OK"
                is_error = False
                num_ok = 1 # Đánh dấu 1 vỉ OK
                details = ["Vỉ thuốc đầy đủ, không phát hiện lỗi"]
            else:
                status_text = "Không thấy vỉ thuốc"
                result_code = "CHỜ VẬT THỂ"
                is_error = False
                details = ["Đang quét vùng trống..."]
        else:
            if num_ng > 0:
                status_text = f"PHÁT HIỆN: {', '.join(loi_hien_thi).upper()}"
                result_code  = f"NG ({num_ng} LỖI)"
                is_error = True
            else:
                status_text = f"ĐẠT: {num_ok} VIÊN THUỐC"
                result_code  = "SẢN PHẨM OK"
                is_error = False
            details = [f"OK: {num_ok}", f"Lỗi: {num_ng} ({', '.join(loi_hien_thi)})"]

    # --- GHI CHÚ: Tín hiệu PLC được điều khiển từ main1.py để đảm bảo tính đồng bộ dữ liệu tổng ---
    # is_ok_pulse = not is_error
    # num_total = num_ok + num_ng
    # send_result_to_plc(is_error, is_ok_pulse, num_ok, num_ng, num_total)

    return annotated, status_text, result_code, is_error, details, num_ok, num_ng

# ==============================
# CHƯƠNG TRÌNH CHÍNH (VÍ DỤ CHẠY CAMERA)
# ==============================
import unicodedata

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])

if __name__ == "__main__":
    model, names = load_model(r"C:\Users\admin\Downloads\thuocvienL.pt")
    connect_to_plc() # Kết nối PLC khi bắt đầu
    
    # Đổi sang camera số 1 (giống trong main1.py) để tránh màn hình xanh do camera ảo ở số 0
    cap = cv2.VideoCapture(1)
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        
        annotated_frame, status, code, err, detail, n_ok, n_ng = process_frame(frame, model, names)
        
        # Loại bỏ dấu tiếng Việt để cv2.putText hiển thị không bị lỗi font (???)
        status_no_accent = remove_accents(status)
        
        # Hiển thị kết quả lên màn hình
        cv2.putText(annotated_frame, f"{status_no_accent}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255) if err else (0,255,0), 2)
        cv2.imshow("He thong phan loai thuoc", annotated_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    cap.release()
    plc_client.disconnect() # Ngắt kết nối khi tắt
    cv2.destroyAllWindows()
    # ==============================
# XỬ LÝ ẢNH ĐƠN (Thêm lại để hết lỗi)

# ==============================
# XỬ LÝ ẢNH ĐƠN
# ==============================
def process_image(image_path, model, class_names, conf_threshold=None):
    """Hàm này dùng để kiểm tra thử 1 file ảnh từ ổ cứng"""
    frame = cv2.imread(image_path)
    if frame is None:
        return None, "Lỗi đọc ảnh", "LỖI FILE", True, ["Không tìm thấy file"], 0, 1
    
    return process_frame(frame, model, class_names, conf_threshold=conf_threshold)