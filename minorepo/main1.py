print("=== PHẦN MỀM KIỂM TRA DƯỢC PHẨM ĐANG KHỞI ĐỘNG... ===")
import cv2
import tkinter as tk
from tkinter import font, messagebox, ttk
from PIL import Image, ImageTk
import os
import datetime
import serial
import time
import csv
import threading
import requests
import json
import snap7
import psycopg2
from dotenv import load_dotenv

# --- ĐƯỜNG DẪN GỐC ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load biến môi trường từ file .env
load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_URL = os.getenv("SUPABASE_API_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- IMPORT FILE LOGIC ĐÃ CẬP NHẬT 4 CLASS ---
print(">>> Đang nạp module logic...")
import kiem_tra_thuoc_logic as logic 
print(">>> Nạp module thành công.")

# --- DANH MỤC MODEL ---2
MODELS_CONF_THRESHOLD = 0.5  
MODELS_CONFIG = {
    "Viên rời": os.path.join(BASE_DIR, "source", "thuocvienL.pt"),
    "Vỉ thuốc": os.path.join(BASE_DIR, "source", "thuoc_yolov8s_best.pt")
}
DEFAULT_PRODUCT = "Viên rời"
CAM_SOURCE ="http://192.168.1.110:4747/video"
BAUD_RATE = 115200
ESP32_IP = "192.168.1.100" 


# --- CẤU HÌNH ĐỒNG BỘ (Căn chỉnh thực tế tại đây) ---
# Delay riêng cho từng loại sản phẩm (đơn vị: giây)
CAPTURE_DELAY_VIEN = 0.0   # Viên rời: chụp NGAY khi cảm biến kích (không delay)
CAPTURE_DELAY_VI   = 0.85      # Vỉ thuốc: chờ 1.1s để vỉ vào đúng tâm ảnh (đã hiệu chuẩn)
PLC_SIGNAL_DURATION = 0.8  # (Giây) Thời gian giữ tín hiệu kết quả trên PLC

# Thư mục lưu trữ chuyên nghiệp
HISTORY_DIR = os.path.join(BASE_DIR, "captured_history")
NG_DIR = os.path.join(HISTORY_DIR, "NG")
OK_DIR = os.path.join(HISTORY_DIR, "OK")

os.makedirs(NG_DIR, exist_ok=True)
os.makedirs(OK_DIR, exist_ok=True)

EXCEL_FILENAME = os.path.join(HISTORY_DIR, "Lich_su_phan_loai.csv")


# ==============================
# MÀU GIAO DIỆN
# ==============================
COLOR_BG ="#FFFACD"
COLOR_FRAME ="#D1F2EB"
COLOR_RED = "#FF0000"
COLOR_GREEN = "#00B050"
COLOR_BLUE = "#0078FF"

# ==============================
# LỚP ĐỌC CAMERA SIÊU TỐC (GIẢM TRỄ)
# ==============================
class CameraStream:
    def __init__(self, source):
        self.cap = cv2.VideoCapture(source)
            
        # Ép độ phân giải cao (Full HD 1080p) để ảnh sắc nét, không bị mờ
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        
        # Tối ưu buffer OpenCV
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ret, self.frame = self.cap.read()
        self.running = True
        self.stopped = False
        
        # --- BIẾN ĐỂ KIỂM TRA CAMERA THỰC TẾ ---
        self.last_frame_data = None
        self.stale_counter = 0
        self.real_online = False 
        
        self.thread = threading.Thread(target=self.update, daemon=True)
        self.thread.start()

    def read(self):
        return self.ret, self.frame

    def release(self):
        self.running = False
        self.stopped = True
        self.cap.release()

    def update(self):
        while self.running:
            try:
                if self.cap.isOpened():
                    # grab() chỉ đẩy khung hình vào hàng đợi, cực nhanh và giúp xả buffer
                    if not self.cap.grab():
                        self.real_online = False
                        self.ret = False
                        time.sleep(0.1)
                        continue
                        
                    # Chúng ta vẫn cần đọc frame để kiểm tra tính online của camera
                    # nhưng sẽ làm với tần suất thấp hơn hoặc tối ưu hơn
                    ret, frame = self.cap.retrieve()
                    if ret and frame is not None:
                        # Kiểm tra camera online (pixel change)
                        h, w = frame.shape[:2]
                        sample = frame[h//2-5:h//2+5, w//2-5:w//2+5].tobytes()
                        if sample == self.last_frame_data:
                            self.stale_counter += 1
                        else:
                            self.stale_counter = 0
                            self.real_online = True
                        
                        self.last_frame_data = sample
                        if self.stale_counter > 50: # Tăng ngưỡng vì grab chạy rất nhanh
                            self.real_online = False
                            
                        self.ret = self.real_online
                        self.frame = frame
                    else:
                        self.real_online = False
                        self.ret = False
                else:
                    self.real_online = False
                    self.ret = False
                    time.sleep(1.0)
                    self.cap = cv2.VideoCapture(CAM_SOURCE)
            except:
                time.sleep(1.0)

    def read(self):
        # Khi App cần ảnh, ta lấy ảnh mới nhất từ luồng
        return self.ret, self.frame

        self.running = False
        self.cap.release()

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Hệ thống AI Phân loại Dược phẩm - Ver 1.0 (PRO)")
        self.root.geometry("1400x850")
        self.root.configure(bg=COLOR_BG)

        # --- Kết nối PLC S7-1200 
        print(f">>> Đang kết nối tới PLC tại địa chỉ: {logic.PLC_IP}...")
        self.plc_connected = logic.connect_to_plc()
        if self.plc_connected:
            # Bật băng tải ngay khi khởi động
            logic.set_conveyor_state(True)
            print(">>> Hệ thống: KẾT NỐI PLC THÀNH CÔNG. Đã bật băng tải.")
        else:
             print(">>> Cảnh báo: KHÔNG THỂ KẾT NỐI TỚI PLC. Chế độ Tự động sẽ không hoạt động.")


        # --- KHÔI PHỤC DỮ LIỆU TỪ PLC KHI KHỞI ĐỘNG ---
        self.vien_ok = 0; self.vien_ng = 0; self.vi_ok = 0; self.vi_ng = 0
        self.total_count = 0
        self.current_product = DEFAULT_PRODUCT

        if self.plc_connected:
            try:
                with logic.plc_lock:
                    raw_total = logic.plc_client.db_read(logic.DB_NUMBER, 2, 8)
                    raw_detail = logic.plc_client.db_read(logic.DB_NUMBER, 10, 8)
                
                # Khôi phục mã sản phẩm trước để load đúng model
                plc_prod_id = snap7.util.get_int(raw_total, 6)
                if plc_prod_id in [1, 2]:
                    self.current_product = "Viên rời" if plc_prod_id == 1 else "Vỉ thuốc"
                
                self.total_count = snap7.util.get_int(raw_total, 4)
                self.vien_ok = snap7.util.get_int(raw_detail, 0)
                self.vien_ng = snap7.util.get_int(raw_detail, 2)
                self.vi_ok   = snap7.util.get_int(raw_detail, 4)
                self.vi_ng   = snap7.util.get_int(raw_detail, 6)
                print(f">>> Đã khôi phục dữ liệu PLC: {self.current_product} | OK={self.vien_ok}, NG={self.vien_ng}")
            except: pass

        # --- Load model AI dựa trên sản phẩm đã khôi phục ---
        self.current_model_id = 1 if self.current_product == "Viên rời" else 2
        self.load_selected_model(MODELS_CONFIG[self.current_product])

        # --- Camera (Sử dụng luồng siêu tốc để giảm trễ) ---
        self.vs = CameraStream(CAM_SOURCE)
        
        # --- Trạng thái ---
        self.current_frame = None
        self.is_paused = False
        self.is_processing = False
        self.last_sensor_state = False
        self.last_remote_change_time = 0 # Thời điểm cuối cùng đổi model từ Web


        # --- UI Fonts ---
        self.font_title = font.Font(family="Arial", size=22, weight="bold")
        self.font_header = font.Font(family="Arial", size=12, weight="bold")
        self.font_status = font.Font(family="Arial", size=24, weight="bold")
        self.font_body = font.Font(family="Arial", size=11)

        self.setup_ui()
        self.update_frame()

        # --- Khởi chạy luồng quét cảm biến (Multithreading) ---
        self.sensor_thread = threading.Thread(target=self.poll_plc_sensor, daemon=True)
        self.sensor_thread.start()

    def load_selected_model(self, path):
        """Hàm nạp model AI và cập nhật danh sách nhãn"""
        try:
            if hasattr(self, 'lbl_info'):
                self.lbl_info.config(text="ĐANG NẠP MODEL...", fg=COLOR_RED)
                self.root.update_idletasks()
            
            self.model, self.class_names = logic.load_model(path)
            
            if hasattr(self, 'lbl_info'):
                self.lbl_info.config(text=f"Đã nạp: {self.current_product}", fg=COLOR_GREEN)
            
            # --- Gửi mã sản phẩm xuống PLC để ThingsBoard hiển thị ID ---
            product_id = 1 if self.current_product == "Viên rời" else 2
            logic.send_product_id_to_plc(product_id)
            
        except Exception as e:
            print(f"Lỗi nạp model: {e}")

    def on_product_change(self, event=None):
        """Xử lý khi người dùng chọn sản phẩm khác trên Menu"""
        new_product = self.combo_product.get()
        if new_product != self.current_product:
            self.current_product = new_product
            print(f"Hệ thống: Đang chuyển sang sản phẩm {new_product}...")
            
            # Tải model mới
            model_path = MODELS_CONFIG[new_product]
            self.load_selected_model(model_path)
            
            # --- GỬI MÃ SẢN PHẨM XUỐNG PLC ĐỂ ĐỒNG BỘ THINGSBOARD ---
            product_id = 1 if new_product == "Viên rời" else 2
            logic.send_product_id_to_plc(product_id)

    def poll_plc_sensor(self):
        """Luồng chạy ngầm để đọc cảm biến PLC liên tục mà không làm treo giao diện"""
        print("Hệ thống: Đã khởi động luồng quét cảm biến.")
        while True:
            # Nếu mất kết nối, thử kết nối lại sau mỗi 2 giây
            if not self.plc_connected:
                self.plc_connected = logic.connect_to_plc()
                if self.plc_connected:
                    self.lbl_plc_status.config(text="PLC: ĐÃ KẾT NỐI", fg=COLOR_GREEN)
                    logic.set_conveyor_state(True)
                else:
                    self.write_status_to_json(False, False)
                    time.sleep(2)
                    continue

            try:
                # --- KIỂM TRA LỆNH TỪ WEB DASHBOARD (SUPABASE) ---
                # --- KIỂM TRA LỆNH TỪ WEB DASHBOARD (SUPABASE) ---
                DEBUG_LOG = r"d:\cms\minorepo\debug_log.txt"
                try:
                    with psycopg2.connect(DB_URL) as conn:
                        with conn.cursor() as cur:
                            cur.execute("SELECT current_model_id FROM system_status WHERE id = 1")
                            row = cur.fetchone()
                            if row:
                                remote_id = row[0]
                                local_id = 1 if self.current_product == "Viên rời" else 2
                                # Log nhịp tim mỗi vòng lặp
                                with open(DEBUG_LOG, "a") as f_log: f_log.write(f"[{time.ctime()}] Polling: Remote={remote_id}, Local={local_id}\n")
                                
                                if remote_id != local_id:
                                    log_msg = f"[{time.ctime()}] WEB CMD: Remote={remote_id}, Local={local_id}. SWITCHING..."
                                    print(log_msg)
                                    with open(DEBUG_LOG, "a") as f_log: f_log.write(log_msg + "\n")
                                    
                                    model_name = "Viên rời" if remote_id == 1 else "Vỉ thuốc"
                                    # Cập nhật UI và nạp model mới
                                    self.root.after(0, lambda n=model_name: self.combo_product.set(n))
                                    self.current_product = model_name
                                    self.load_selected_model(MODELS_CONFIG[model_name])
                                    # Đồng bộ xuống PLC
                                    logic.send_product_id_to_plc(remote_id)
                                    self.last_remote_change_time = time.time()
                except Exception as e:
                    print(f"Lỗi đọc lệnh từ Supabase: {e}")

                # --- ĐỒNG BỘ COUNTER TỪ PLC (Hỗ trợ Reset từ ThingsBoard) ---
                # Nếu PLC trả về 0 (đã bị reset), ta phải reset biến Python tương ứng
                # DB1.DBW10=VienOK, DBW12=VienNG, DBW14=ViOK, DBW16=ViNG
                # Ta đọc 8 byte từ offset 10
                with logic.plc_lock:
                    raw_counts = logic.plc_client.db_read(logic.DB_NUMBER, 10, 8)
                
                plc_vien_ok = snap7.util.get_int(raw_counts, 0)
                plc_vien_ng = snap7.util.get_int(raw_counts, 2)
                plc_vi_ok   = snap7.util.get_int(raw_counts, 4)
                plc_vi_ng   = snap7.util.get_int(raw_counts, 6)

                # ĐỒNG BỘ AN TOÀN: Chỉ Reset khi thấy PLC bị xóa về 0 (Manual Reset từ Dashboard)
                # Hoặc cập nhật Python nếu PLC lớn hơn (đảm bảo tính nhất quán sau khi khởi động lại)
                if plc_vien_ok == 0 and self.vien_ok > 0: 
                    print(">>> PLC: Reset counter Viên rời.")
                    self.vien_ok = 0
                elif plc_vien_ok > self.vien_ok:
                    self.vien_ok = plc_vien_ok

                if plc_vien_ng == 0 and self.vien_ng > 0: 
                    self.vien_ng = 0
                elif plc_vien_ng > self.vien_ng:
                    self.vien_ng = plc_vien_ng

                if plc_vi_ok == 0 and self.vi_ok > 0: 
                    print(">>> PLC: Reset counter Vỉ thuốc.")
                    self.vi_ok = 0
                elif plc_vi_ok > self.vi_ok:
                    self.vi_ok = plc_vi_ok

                if plc_vi_ng == 0 and self.vi_ng > 0: 
                    self.vi_ng = 0
                elif plc_vi_ng > self.vi_ng:
                    self.vi_ng = plc_vi_ng
                
                # Cập nhật tổng
                self.total_count = self.vien_ok + self.vien_ng + self.vi_ok + self.vi_ng

                # --- ĐỌC CẢM BIẾN & TRẠNG THÁI HỆ THỐNG ---
                current_sensor = logic.read_sensor_trigger()
                system_active = logic.read_system_status()
                
                try:
                    status_color = COLOR_GREEN if system_active else COLOR_RED
                    status_text = "HỆ THỐNG: ĐANG CHẠY" if system_active else "HỆ THỐNG: ĐANG DỪNG"
                    self.root.after(0, lambda s=status_text, c=status_color: self.lbl_plc_status.config(text=f"PLC: OK | {s}", fg=c))
                except: pass

                if system_active:
                    rising_edge = (current_sensor == True and self.last_sensor_state == False)
                    if rising_edge:
                        if not self.is_processing:
                            self.is_processing = True # Khóa ngay lập tức để tránh trigger trùng trong lúc chờ delay
                            print(f">>> CẢM BIẾN KÍCH HOẠT (Bit 0.1)! Bắt đầu kiểm tra mẫu: {self.current_product}", flush=True)
                            delay = CAPTURE_DELAY_VI if self.current_product == "Vỉ thuốc" else CAPTURE_DELAY_VIEN
                            
                            # Xử lý delay không chặn luồng (Non-blocking delay)
                            self.root.after(int(delay * 1000), self.perform_check)
                    self.last_sensor_state = current_sensor

                    # Kiểm tra lệnh đổi model từ PLC (Chỉ để log và ép PLC theo Web)
                    if time.time() - self.last_remote_change_time > 5:
                        plc_product_id = logic.read_product_id_from_plc() 
                        expected_id = 1 if self.current_product == "Viên rời" else 2
                        if plc_product_id > 0 and plc_product_id != expected_id:
                            # print(f"PLC lệch Model: PLC={plc_product_id}, Web={expected_id}. Đang sửa lại...")
                            logic.send_product_id_to_plc(expected_id)
                
                # --- GHI TRẠNG THÁI HỆ THỐNG CHO WEB DASHBOARD & PLC ---
                # Chỉ đẩy lên Supabase mỗi 2 giây để tránh quá tải thread
                if not hasattr(self, 'last_supabase_update') or time.time() - self.last_supabase_update > 2:
                    self.write_status_to_json(self.plc_connected, system_active)
                    self.last_supabase_update = time.time()
                
                logic.send_camera_status_to_plc(getattr(self, 'cam_connected', False))

            except Exception as e:
                self.plc_connected = False
                logic.disconnect_plc()
                self.lbl_plc_status.config(text="PLC: MẤT KẾT NỐI", fg=COLOR_RED)
                self.write_status_to_json(False, False)
                self.last_supabase_update = time.time()
            
            time.sleep(0.1)

    def write_status_to_json(self, plc_status, machine_status):
        try:
            status_path = os.path.join(BASE_DIR, "system_status.json")
            temp_path = status_path + ".tmp"
            with open(temp_path, "w") as f:
                json.dump({
                    "plc_online": plc_status,
                    "machine_running": machine_status,
                    "cam_online": getattr(self, 'cam_connected', False),
                    "current_model_id": 1 if self.current_product == "Viên rời" else 2,
                    "current_product": self.current_product,
                    "last_update": time.time()
                }, f)
            if os.path.exists(status_path): os.remove(status_path)
            os.rename(temp_path, status_path)
            
            # ĐẨY TRẠNG THÁI LÊN SUPABASE
            self.push_status_to_supabase(plc_status, machine_status)
        except: pass

    def push_status_to_supabase(self, plc_online, machine_running):
        if not DB_URL or "MAT_KHAU" in DB_URL: return
        def run():
            try:
                conn = psycopg2.connect(DB_URL)
                cur = conn.cursor()
                cur.execute("SET TIME ZONE 'Asia/Ho_Chi_Minh';")
                # Thử cập nhật thêm các cột số lượng nếu có trong bảng system_status
                cur.execute("""
                    INSERT INTO system_status (id, plc_online, machine_running, cam_online, last_update,
                                             vien_ok, vien_ng, vi_ok, vi_ng, current_model_id)
                    VALUES (1, %s, %s, %s, NOW(), %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET 
                        plc_online = EXCLUDED.plc_online,
                        machine_running = EXCLUDED.machine_running,
                        cam_online = EXCLUDED.cam_online,
                        last_update = EXCLUDED.last_update,
                        vien_ok = EXCLUDED.vien_ok,
                        vien_ng = EXCLUDED.vien_ng,
                        vi_ok = EXCLUDED.vi_ok,
                        vi_ng = EXCLUDED.vi_ng,
                        current_model_id = EXCLUDED.current_model_id;
                """, (plc_online, machine_running, getattr(self, 'cam_connected', False), 
                       self.vien_ok, self.vien_ng, self.vi_ok, self.vi_ng,
                       1 if self.current_product == "Viên rời" else 2))
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                # Nếu bảng chưa có các cột mới, chạy lệnh cũ để không lỗi
                try:
                    conn = psycopg2.connect(DB_URL)
                    cur = conn.cursor()
                    cur.execute("SET TIME ZONE 'Asia/Ho_Chi_Minh';")
                    cur.execute("""
                        INSERT INTO system_status (id, plc_online, machine_running, cam_online, last_update, current_model_id)
                        VALUES (1, %s, %s, %s, NOW(), %s)
                        ON CONFLICT (id) DO UPDATE SET 
                            plc_online = EXCLUDED.plc_online,
                            machine_running = EXCLUDED.machine_running,
                            cam_online = EXCLUDED.cam_online,
                            last_update = EXCLUDED.last_update,
                            current_model_id = EXCLUDED.current_model_id;
                    """, (plc_online, machine_running, getattr(self, 'cam_connected', False),
                           1 if self.current_product == "Viên rời" else 2))
                    conn.commit()
                    cur.close()
                    conn.close()
                except: pass
        threading.Thread(target=run, daemon=True).start()

    def upload_to_supabase_storage(self, file_path, file_name):
        """Tải ảnh lên Supabase Storage và trả về Public URL"""
        if not SUPABASE_API_URL or not SUPABASE_KEY or "YOUR" in SUPABASE_KEY:
            return None
            
        url = f"{SUPABASE_API_URL}/storage/v1/object/inspection-images/{file_name}"
        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "image/jpeg"
        }
        try:
            with open(file_path, "rb") as f:
                res = requests.post(url, headers=headers, data=f)
                if res.status_code == 200:
                    # Trả về link public (Đảm bảo Bucket 'inspection-images' đã được chỉnh Public)
                    return f"{SUPABASE_API_URL}/storage/v1/object/public/inspection-images/{file_name}"
                else:
                    print(f"Lỗi Upload Storage: {res.status_code} - {res.text}", flush=True)
        except Exception as e:
            print(f"Lỗi Upload: {e}", flush=True)
        return None

    def push_inspection_to_supabase(self, product, result, is_ng, details, num_ok=0, num_ng=0, image_url=None):
        if not DB_URL or "MAT_KHAU" in DB_URL: return
        def run():
            try:
                conn = psycopg2.connect(DB_URL)
                cur = conn.cursor()
                cur.execute("SET TIME ZONE 'Asia/Ho_Chi_Minh';")
                cur.execute("""
                    INSERT INTO inspections (product_name, result, is_ng, details, num_ok, num_ng, image_url, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW());
                """, (product, result, is_ng, " | ".join(details), num_ok, num_ng, image_url))
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                print(f"Lỗi đẩy kết quả lên Supabase: {e}", flush=True)
        threading.Thread(target=run, daemon=True).start()

    def setup_ui(self):
        self.frame_left = tk.Frame(self.root, bg=COLOR_BG)
        self.frame_left.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.frame_right = tk.Frame(self.root, bg=COLOR_FRAME, width=450)
        self.frame_right.pack(side="right", fill="y", padx=10, pady=10)
        self.frame_right.pack_propagate(False)

        tk.Label(self.frame_left, text="HỆ THỐNG PHÂN LOẠI DƯỢC PHẨM", font=self.font_title, bg=COLOR_BG).pack(pady=10)
        recipe_frame = tk.LabelFrame(self.frame_left, text=" CÔNG THỨC SẢN PHẨM ", font=self.font_header, bg=COLOR_BG, fg=COLOR_BLUE)
        recipe_frame.pack(pady=10, fill="x", padx=50)
        # tk.Label(recipe_frame, text="Chọn sản phẩm:", font=self.font_body, bg=COLOR_BG).pack(side="left", padx=20, pady=15)
        # self.combo_product = ttk.Combobox(recipe_frame, values=list(MODELS_CONFIG.keys()), font=self.font_body, state="readonly", width=25)
        # self.combo_product.set(self.current_product)
        # self.combo_product.pack(side="left", padx=10)
        # self.combo_product.bind("<<ComboboxSelected>>", self.on_product_change)

        self.lbl_webcam = tk.Label(self.frame_left, bg="black", width=800, height=600)
        self.lbl_webcam.pack()

        # frame_btn = tk.Frame(self.frame_left, bg=COLOR_BG)
        # frame_btn.pack(pady=20)
        # tk.Button(frame_btn, text="KIỂM TRA NGAY", bg=COLOR_BLUE, fg="white", font=("Arial",14,"bold"), width=18, height=2, command=self.action_manual_check).pack(side="left", padx=10)
        # tk.Button(frame_btn, text="XEM LỊCH SỬ (.CSV)", bg="#FFA500", fg="white", font=("Arial",14,"bold"), width=18, height=2, command=self.open_excel_file).pack(side="left", padx=10)

        tk.Label(self.frame_right, text="KẾT QUẢ PHÂN TÍCH AI", font=self.font_header, bg=COLOR_FRAME).pack(pady=10)
        self.lbl_result_image = tk.Label(self.frame_right, bg="gray", width=400, height=300)
        self.lbl_result_image.pack(pady=5)
        self.lbl_info = tk.Label(self.frame_right, text="Sẵn sàng quét...", font=self.font_body, bg=COLOR_FRAME)
        self.lbl_info.pack(pady=5)
        self.lbl_status = tk.Label(self.frame_right, text="CHỜ VẬT THỂ", font=self.font_status, bg=COLOR_FRAME, fg=COLOR_BLUE)
        self.lbl_status.pack(pady=10)
        tk.Label(self.frame_right, text="CHI TIẾT LỖI:", font=self.font_header, bg=COLOR_FRAME).pack(anchor="w", padx=25)
        self.txt_details = tk.Text(self.frame_right, height=8, width=48, font=self.font_body)
        self.txt_details.pack(pady=5, padx=20)
        self.lbl_plc_status = tk.Label(self.frame_right, text="PLC: ...", font=self.font_header, bg=COLOR_FRAME)
        self.lbl_plc_status.pack(pady=10)

    def action_manual_check(self):
        if not self.is_processing: self.perform_check()

    def get_sharpness(self, image):
        return cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()

    def perform_check(self):
        if self.current_frame is None: 
            self.is_processing = False # Giải phóng nếu không có frame
            return
        self.is_paused = True 
        ret, f = self.vs.read()
        if not ret: 
            self.reset_system()
            return
        best_frame = f.copy()
        # Loại bỏ filter làm sắc nét để tránh tạo nhiễu giả cho AI
        # import numpy as np
        # kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
        # best_frame = cv2.filter2D(best_frame, -1, kernel)
        threading.Thread(target=self.worker_process, args=(best_frame,), daemon=True).start()

    def worker_process(self, frame):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_img_name = f"pill_{timestamp}.jpg"
        temp_path = os.path.join(BASE_DIR, temp_img_name)
        try:
            cv2.imwrite(temp_path, frame)
            annotated, info, conclusion, is_ng, details, n_ok, n_ng = logic.process_image(temp_path, self.model, self.class_names, conf_threshold=MODELS_CONF_THRESHOLD)
            if self.plc_connected:
                # Cập nhật số lượng cục bộ dựa trên số lượng AI đếm được
                if self.current_product == "Viên rời":
                    self.vien_ok += n_ok
                    self.vien_ng += n_ng
                else:
                    # Đối với vỉ, ta đếm theo Đơn vị vỉ (1 vỉ OK hoặc 1 vỉ NG)
                    if is_ng: self.vi_ng += 1
                    else: self.vi_ok += 1
                
                try:
                    # Gửi số tổng và số chi tiết lên PLC
                    total_ok = self.vien_ok + self.vi_ok
                    total_ng = self.vien_ng + self.vi_ng
                    total_all = total_ok + total_ng
                    print(f"PLC: Gửi tín hiệu {'LỖI (NG)' if is_ng else 'ĐẠT (OK)'} | Total={total_all}", flush=True)
                    
                    # Gửi Tổng OK, Tổng NG và Tổng Tất cả xuống PLC
                    logic.send_result_to_plc(is_error=is_ng, is_ok=not is_ng, num_ok=total_ok, num_ng=total_ng, num_total=total_all)
                    
                    # Cập nhật số lượng riêng của loại đang chạy lên PLC
                    logic.send_product_specific_counts(self.current_product, 
                        self.vien_ok if self.current_product == "Viên rời" else self.vi_ok,
                        self.vien_ng if self.current_product == "Viên rời" else self.vi_ng)
                except: pass
            
            # ĐẨY KẾT QUẢ LÊN SUPABASE (Sẽ đẩy sau khi có ảnh ở finish_check_ui)
            # self.push_inspection_to_supabase(self.current_product, conclusion, is_ng, details)

            self.root.after(0, lambda: self.finish_check_ui(annotated, info, conclusion, is_ng, details, timestamp, n_ok, n_ng))
        except Exception as e:
            print(f"Lỗi xử lý: {e}", flush=True)
            self.root.after(0, self.reset_system)
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)

    def finish_check_ui(self, annotated, info, conclusion, is_ng, details, timestamp, n_ok, n_ng):
        fg_color = COLOR_RED if is_ng else COLOR_GREEN
        self.lbl_info.config(text=info, fg=fg_color)
        self.lbl_status.config(text=conclusion, fg=fg_color)
        self.txt_details.delete('1.0', tk.END)
        for d in details: self.txt_details.insert(tk.END, f"• {d}\n")
        if annotated is not None:
            h, w = annotated.shape[:2]
            scale = min(400 / w, 300 / h)
            img_res = cv2.resize(annotated, (int(w*scale), int(h*scale)))
            img_res = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB)))
            self.lbl_result_image.config(image=img_res)
            self.lbl_result_image.imgtk = img_res
            
            # --- LƯU ẢNH CỤC BỘ VÀ UPLOAD SUPABASE ---
            file_name = f"pill_{timestamp}.jpg"
            local_path = os.path.join(NG_DIR if is_ng else OK_DIR, file_name)
            cv2.imwrite(local_path, annotated)
            
            # Upload lên Storage (Chạy ngầm để không đơ UI)
            def upload_task():
                img_url = self.upload_to_supabase_storage(local_path, file_name)
                # Sau khi có URL, mới đẩy data lên Database
                self.push_inspection_to_supabase(self.current_product, conclusion, is_ng, details, n_ok, n_ng, img_url)
            
            threading.Thread(target=upload_task, daemon=True).start()
        
        self.save_to_csv(timestamp, conclusion, is_ng, details)
        
        # Đã cập nhật số lượng trong worker_process để đẩy lên PLC nhanh hơn
        
        self.root.after(int(PLC_SIGNAL_DURATION * 1000), self.reset_system)

    def save_to_csv(self, timestamp, conclusion, is_ng, details):
        try:
            file_exists = os.path.isfile(EXCEL_FILENAME)
            dt = datetime.datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
            display_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            with open(EXCEL_FILENAME, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists: writer.writerow(['STT', 'Sản phẩm', 'Kết quả', 'Thời gian'])
                writer.writerow([self.total_count, self.current_product, f"{'[NG]' if is_ng else '[OK]'} {conclusion}", display_time])
        except: pass

    def open_excel_file(self):
        if os.path.exists(EXCEL_FILENAME): os.startfile(EXCEL_FILENAME)

    def reset_system(self):
        self.is_paused = False
        self.is_processing = False
        if self.plc_connected:
            try: logic.send_result_to_plc(is_error=False, is_ok=False)
            except: pass
        self.lbl_status.config(text="ĐANG QUÉT...", fg=COLOR_BLUE)

    def update_frame(self):
        if not self.is_paused:
            ret, frame = self.vs.read()
            self.cam_connected = ret
            if ret:
                self.current_frame = frame.copy()
                img = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(cv2.resize(frame, (800, 600)), cv2.COLOR_BGR2RGB)))
                self.lbl_webcam.config(image=img)
                self.lbl_webcam.imgtk = img
        self.root.after(20, self.update_frame)

    def on_closing(self):
        print("Hệ thống: Đang tắt ứng dụng và dọn dẹp kết nối...")
        try:
            # 1. Báo Camera Offline xuống PLC trước khi tắt để ESP32 báo về ThingsBoard
            logic.send_camera_status_to_plc(False)
            # 2. Dừng băng tải để an toàn
            logic.set_conveyor_state(False)
            # 3. Ngắt kết nối PLC sạch sẽ
            logic.disconnect_plc()
        except:
            pass
            
        self.vs.release()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()