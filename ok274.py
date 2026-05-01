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

# --- IMPORT FILE LOGIC ĐÃ CẬP NHẬT 4 CLASS ---
import kiem_tra_thuoc_logic as logic 

# --- DANH MỤC MODEL ---
MODELS_CONFIG = {
    "Viên rời": r"C:\Users\admin\Downloads\thuocvienL.pt",
    "Vỉ thuốc": r"C:\Users\admin\Downloads\thuoc_yolov8s_best.pt" # Bạn hãy sửa đường dẫn này cho đúng file vỉ thuốc nhé
}
DEFAULT_PRODUCT = "Viên rời"
CAM_SOURCE = 0
BAUD_RATE = 115200
ESP32_IP = "192.168.1.100" 


# --- CẤU HÌNH ĐỒNG BỘ (Căn chỉnh thực tế tại đây) ---
# Delay riêng cho từng loại sản phẩm (đơn vị: giây)
CAPTURE_DELAY_VIEN = 0.0   # Viên rời: chụp NGAY khi cảm biến kích (không delay)
CAPTURE_DELAY_VI   = 1.2      # Vỉ thuốc: chờ 0.3s để vỉ vào đúng tâm ảnh (chỉnh theo thực tế)
PLC_SIGNAL_DURATION = 0.8  # (Giây) Thời gian giữ tín hiệu kết quả trên PLC

# Thư mục lưu trữ
BASE_DIR = r"D:\Code\captured_medicine"
NG_DIR = os.path.join(BASE_DIR, "NG_LOI")
OK_DIR = os.path.join(BASE_DIR, "OK_DAT")

os.makedirs(NG_DIR, exist_ok=True)
os.makedirs(OK_DIR, exist_ok=True)

EXCEL_FILENAME = os.path.join(BASE_DIR, "Lich_su_phan_loai.csv")

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

    def poll_plc_sensor(self):
        """Luồng quét liên tục: Kiểm tra Cảm biến và Lệnh đổi Model từ Web"""
        last_model_id = -1
        while self.vs.stopped is False:
            if self.plc_connected:
                try:
                    # GỬI TRẠNG THÁI "HỆ THỐNG ĐANG CHẠY" SANG PLC (Bit 0.3)
                    logic.write_bit_to_plc(0, 3, True)

                    # 1. KIỂM TRA LỆNH ĐỔI MODEL TỪ WEB (Đọc từ PLC Offset 8)
                    current_model_id = logic.read_product_id_from_plc()
                    if current_model_id != last_model_id and current_model_id in [1, 2]:
                        new_model_name = "Viên rời" if current_model_id == 1 else "Vỉ thuốc"
                        if new_model_name != self.current_product:
                            print(f"Hệ thống: Nhận lệnh đổi sang {new_model_name} từ Web.")
                            self.current_product = new_model_name
                            # Gọi hàm nạp model trong luồng chính của Tkinter
                            self.root.after(0, lambda: self.load_selected_model(MODELS_CONFIG[self.current_product]))
                        last_model_id = current_model_id

                    # 2. KIỂM TRA CẢM BIẾN VẬT THỂ (Trigger AI)
                    sensor_on = logic.read_sensor_from_plc()
                    if sensor_on and not self.last_sensor_state:
                        if not self.is_processing:
                            print("Hệ thống: Phát hiện sản phẩm! (Trigger từ PLC)")
                            self.is_processing = True
                            self.root.after(int(CAPTURE_DELAY * 1000), self.perform_check)
                    self.last_sensor_state = sensor_on
                    
                    # 3. GHI TRẠNG THÁI HỆ THỐNG ĐỂ DASHBOARD ĐỌC
                    status_path = os.path.join(BASE_DIR, "system_status.json")
                    with open(status_path, "w") as f:
                        json.dump({
                            "plc_online": self.plc_connected,
                            "machine_running": logic.read_system_status(),
                            "last_update": time.time()
                        }, f)

                except Exception as e:
                    print(f"Lỗi quét PLC: {e}")
                    status_path = os.path.join(BASE_DIR, "system_status.json")
                    with open(status_path, "w") as f:
                        json.dump({"plc_online": False, "machine_running": False, "last_update": time.time()}, f)
            time.sleep(0.5)

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
                    ret, frame = self.cap.read()
                    if ret and frame is not None:
                        # 1. Kiểm tra xem ảnh có bị "đứng" không (Dành cho DroidCam/Virtual Cam)
                        # Chúng ta lấy một vùng nhỏ ở giữa ảnh để so sánh cho nhanh
                        h, w = frame.shape[:2]
                        sample = frame[h//2-50:h//2+50, w//2-50:w//2+50].tobytes()
                        
                        if sample == self.last_frame_data:
                            self.stale_counter += 1
                        else:
                            self.stale_counter = 0
                            self.real_online = True # Có thay đổi pixel = Camera thật đang chạy
                        
                        self.last_frame_data = sample
                        
                        # Nếu ảnh đứng im quá 20 khung hình (khoảng 0.7 giây) -> Coi như mất kết nối
                        if self.stale_counter > 20:
                            self.real_online = False
                        
                        self.ret = self.real_online
                        self.frame = frame
                    else:
                        self.ret = False
                        time.sleep(0.1)
                else:
                    self.ret = False
                    # Nếu mất kết nối, thử mở lại sau 2 giây
                    print(">>> Camera mất kết nối, đang thử lại...")
                    self.cap.release()
                    time.sleep(2.0)
                    self.cap = cv2.VideoCapture(CAM_SOURCE)
            except Exception as e:
                self.ret = False
                print(f"Lỗi Camera: {e}")
                time.sleep(1.0)

        self.running = False
        self.cap.release()

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Hệ thống AI Phân loại Dược phẩm - Ver 1.0")
        self.root.geometry("1400x850")
        self.root.configure(bg=COLOR_BG)

        # --- Kết nối PLC S7-1200 
        self.plc_connected = logic.connect_to_plc()
        if self.plc_connected:
            # Bật băng tải ngay khi khởi động
            logic.set_conveyor_state(True)
            print("Hệ thống: Đã kích hoạt băng tải sẵn sàng.")
        else:
             print("Cảnh báo: Không thể kết nối tới PLC. Chế độ Tự động sẽ không hoạt động.")


        # --- Load model AI mặc định ---
        self.current_product = DEFAULT_PRODUCT
        self.current_model_id = 1 if DEFAULT_PRODUCT == "Viên rời" else 2 # Khởi tạo ID model
        self.load_selected_model(MODELS_CONFIG[self.current_product])

        # --- Camera (Sử dụng luồng siêu tốc để giảm trễ) ---
        self.vs = CameraStream(CAM_SOURCE)
        
        # --- Trạng thái ---
        self.current_frame = None
        self.is_paused = False
        self.is_processing = False
        self.last_sensor_state = False
        self.total_count = 0

        # --- Đếm riêng từng loại sản phẩm (gửi xuống PLC để ESP32 đọc) ---
        self.vien_ok = 0  # Viên rời đạt
        self.vien_ng = 0  # Viên rời lỗi
        self.vi_ok   = 0  # Vỉ thuốc đạt
        self.vi_ng   = 0  # Vỉ thuốc lỗi

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
            
            # --- Gửi mã sản phẩm xuống PLC để ESP32 hiển thị tên ---
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
            
            # --- GỬI MÃ SẢN PHẨM XUỐNG PLC ĐỂ ĐỒNG BỘ WEB ---
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
                    # KỂ CẢ KHI PLC CHƯA KẾT NỐI, VẪN PHẢI CẬP NHẬT JSON ĐỂ WEB BIẾT CAM ĐANG ON
                    self.write_status_to_json(False, False)
                    time.sleep(2)
                    continue

            try:
                # --- KIỂM TRA LỆNH TỪ WEB DASHBOARD ---
                cmd_path = os.path.join(BASE_DIR, "command.json")
                if os.path.exists(cmd_path):
                    try:
                        with open(cmd_path, "r") as f:
                            cmd_data = json.load(f)
                        if cmd_data.get("cmd") == "set_model":
                            target_id = cmd_data.get("value")
                            print(f">>> NHẬN LỆNH ĐỔI MODEL TỪ WEB: {target_id}")
                            # Thực hiện gửi tới PLC
                            logic.send_product_id_to_plc(target_id)
                            # Cập nhật giao diện local
                            model_name = "Viên rời" if target_id == 1 else "Vỉ thuốc"
                            self.root.after(0, lambda n=model_name: self.combo_product.set(n))
                            self.root.after(0, self.on_product_change)
                        # Xử lý xong thì xóa file lệnh
                        os.remove(cmd_path)
                    except Exception as e:
                        print(f"Lỗi xử lý lệnh từ Web: {e}")

                # --- ĐỌC CẢM BIẾN ---
                current_sensor = logic.read_sensor_trigger()
                system_active = logic.read_system_status()
                
                # Cập nhật trạng thái lên giao diện (Sử dụng try-except để tránh treo)
                try:
                    status_color = COLOR_GREEN if system_active else COLOR_RED
                    status_text = "HỆ THỐNG: ĐANG CHẠY" if system_active else "HỆ THỐNG: ĐANG DỪNG"
                    self.root.after(0, lambda s=status_text, c=status_color: self.lbl_plc_status.config(text=f"PLC: OK | {s}", fg=c))
                except:
                    pass

                # Nếu hệ thống ON
                if system_active:

                    # Phát hiện sườn lên (OFF → ON): Trigger chụp ảnh
                    rising_edge = (current_sensor == True and self.last_sensor_state == False)

                    if rising_edge:
                        print(f"--- Cảm biến: ON (sườn lên) ---")
                        if not self.is_processing:
                            print("Hệ thống: Phát hiện sản phẩm! (Trigger từ PLC)")

                            # --- ĐỒNG BỘ: Chọn delay theo loại sản phẩm ---
                            if self.current_product == "Vỉ thuốc":
                                delay = CAPTURE_DELAY_VI
                            else:
                                delay = CAPTURE_DELAY_VIEN

                            if delay > 0:
                                print(f"Hệ thống: [{self.current_product}] Đang chờ {delay}s trước khi chụp...")
                                time.sleep(delay)

                            # Đẩy lệnh xử lý về luồng chính
                            self.root.after(0, self.perform_check)
                        else:
                            print("Hệ thống: Đang bận xử lý, bỏ qua trigger này.")

                    # LUÔN cập nhật last_sensor_state sau mỗi vòng (quan trọng!)
                    self.last_sensor_state = current_sensor

                    # --- KIỂM TRA LỆNH ĐỔI MODEL TỪ WEB/PLC (Kiểm tra liên tục) ---
                    plc_product_id = logic.read_product_id_from_plc() 
                    expected_id = 1 if self.current_product == "Viên rời" else 2
                    
                    if plc_product_id > 0 and plc_product_id != expected_id:
                        new_name = "Viên rời" if plc_product_id == 1 else "Vỉ thuốc"
                        print(f"Hệ thống: Nhận lệnh đổi sang {new_name} từ Web/PLC")
                        self.current_product = new_name
                        self.root.after(0, lambda n=new_name: self.combo_product.set(n))
                        self.root.after(0, lambda p=MODELS_CONFIG[new_name]: self.load_selected_model(p))
                
                # --- GHI CHÚ QUAN TRỌNG ---
                # Vì ESP32 hiện tại đã TỰ ĐỘNG kết nối Modbus TCP trực tiếp với PLC (đúng yêu cầu đồ án),
                # nên Python không cần (và không nên) gửi dữ liệu sang ESP32 nữa để tránh làm chậm hệ thống.
                pass

                # --- GHI TRẠNG THÁI HỆ THỐNG CHO WEB DASHBOARD ---
                self.write_status_to_json(self.plc_connected, system_active)

            except Exception as e:
                self.plc_connected = False
                logic.disconnect_plc()
                self.lbl_plc_status.config(text="PLC: MẤT KẾT NỐI", fg=COLOR_RED)
                print(f"Lỗi đọc PLC: {e}")
                self.write_status_to_json(False, False)
            
            time.sleep(0.05)

    def write_status_to_json(self, plc_status, machine_status):
        """Hàm ghi file JSON an toàn (Atomic Write) để Dashboard không bị đọc file trống"""
        try:
            status_path = os.path.join(BASE_DIR, "system_status.json")
            temp_path = status_path + ".tmp"
            
            # Ghi vào file tạm trước
            with open(temp_path, "w") as f:
                json.dump({
                    "plc_online": plc_status,
                    "machine_running": machine_status,
                    "cam_online": getattr(self, 'cam_connected', False),
                    "current_model_id": getattr(self, 'current_model_id', 1),
                    "last_update": time.time()
                }, f)
            
            # Ghi xong file tạm mới thực hiện ĐỔI TÊN thành file chính (Cực kỳ an toàn)
            if os.path.exists(status_path):
                os.remove(status_path)
            os.rename(temp_path, status_path)
            
        except Exception as e:
            # print(f"Lỗi ghi JSON: {e}")
            pass

    def setup_ui(self):
        # Layout chính
        self.frame_left = tk.Frame(self.root, bg=COLOR_BG)
        self.frame_left.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        self.frame_right = tk.Frame(self.root, bg=COLOR_FRAME, width=450)
        self.frame_right.pack(side="right", fill="y", padx=10, pady=10)
        self.frame_right.pack_propagate(False)

        # --- Bên trái: Camera ---
        tk.Label(self.frame_left, text="HỆ THỐNG GIÁM SÁT BĂNG TẢI THUỐC", font=self.font_title, bg=COLOR_BG).pack(pady=10)
        # --- Khu vực chọn sản phẩm (Recipes) ---
        recipe_frame = tk.LabelFrame(self.frame_left, text=" CÔNG THỨC SẢN PHẨM ", font=self.font_header, bg=COLOR_BG, fg=COLOR_BLUE)
        recipe_frame.pack(pady=10, fill="x", padx=50)
        
        tk.Label(recipe_frame, text="Chọn sản phẩm:", font=self.font_body, bg=COLOR_BG).pack(side="left", padx=20, pady=15)
        self.combo_product = ttk.Combobox(recipe_frame, values=list(MODELS_CONFIG.keys()), font=self.font_body, state="readonly", width=25)
        self.combo_product.set(self.current_product)
        self.combo_product.pack(side="left", padx=10)
        self.combo_product.bind("<<ComboboxSelected>>", self.on_product_change)

        self.lbl_webcam = tk.Label(self.frame_left, bg="black", width=800, height=600)
        self.lbl_webcam.pack()

        frame_btn = tk.Frame(self.frame_left, bg=COLOR_BG)
        frame_btn.pack(pady=20)

        self.btn_snapshot = tk.Button(frame_btn, text="KIỂM TRA NGAY", bg=COLOR_BLUE, fg="white",
                                     font=("Arial",14,"bold"), width=18, height=2, command=self.action_manual_check)
        self.btn_snapshot.pack(side="left", padx=10)

        self.btn_history = tk.Button(frame_btn, text="XEM LỊCH SỬ (.CSV)", bg="#FFA500", fg="white",
                                    font=("Arial",14,"bold"), width=18, height=2, command=self.open_excel_file)
        self.btn_history.pack(side="left", padx=10)

        # --- Bên phải: Kết quả Phân tích ---
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

        # Trạng thái PLC
        self.lbl_plc_status = tk.Label(self.frame_right, text=f"PLC: {'ĐÃ KẾT NỐI' if self.plc_connected else 'MẤT KẾT NỐI'}",
                                       font=self.font_header, bg=COLOR_FRAME, fg=COLOR_GREEN if self.plc_connected else COLOR_RED)
        self.lbl_plc_status.pack(pady=10)

    def action_manual_check(self):
        if not self.is_processing:
            self.perform_check()

    def get_sharpness(self, image):
        """Tính độ sắc nét của ảnh bằng thuật toán Laplacian"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()

    def perform_check(self):
        """Chụp nhanh nhiều tấm và chọn tấm nét nhất để xử lý AI"""
        if self.current_frame is None: return

        self.is_processing = True
        self.is_paused = True 
        
        # --- CHIẾN THUẬT: Chụp siêu tốc 3 tấm (Vì băng tải đã dừng) ---
        frames = []
        for _ in range(1):
            ret, f = self.vs.read()
            if ret:
                frames.append(f.copy())
            time.sleep(0.00) # Trễ cực nhỏ 10ms

        if not frames:
            self.reset_system()
            return

        # --- Lọc lấy tấm ảnh nét nhất ---
        best_frame = max(frames, key=self.get_sharpness)
        
        # --- Tự động làm sắc nét ảnh bằng OpenCV (Sharpen) ---
        import numpy as np
        kernel = np.array([[0, -1, 0], 
                           [-1, 5,-1], 
                           [0, -1, 0]])
        best_frame = cv2.filter2D(best_frame, -1, kernel)
        
        # Chạy việc xử lý trong một luồng riêng
        threading.Thread(target=self.worker_process, args=(best_frame,), daemon=True).start()

    def worker_process(self, frame):
        """Luồng xử lý AI và PLC ngầm"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_img_name = f"pill_{timestamp}.jpg"
        temp_path = os.path.join(BASE_DIR, temp_img_name)
        
        try:
            cv2.imwrite(temp_path, frame)
            
            # --- AUTO-CROP LẤY DATA TRAIN CHO BẠN ---
            train_dir = os.path.join(BASE_DIR, "Data_Train_Nhoe")
            os.makedirs(train_dir, exist_ok=True)
            crop_path = os.path.join(train_dir, f"crop_{temp_img_name}")
            cropped_frame = logic.apply_static_crop(frame)
            cv2.imwrite(crop_path, cropped_frame)

            # 1. Gọi logic AI (Phần này nặng nhất sẽ chạy ngầm)
            annotated, info, conclusion, is_ng, details = logic.process_image(temp_path, self.model, self.class_names)
            
            # 2. Gửi tín hiệu PLC ngầm (Phần này cũng có thể gây trễ mạng)
            if self.plc_connected:
                try:
                    is_ok = not is_ng # Nếu không phải NG thì là OK
                    logic.send_result_to_plc(is_error=is_ng, is_ok=is_ok)
                    print(f"PLC nhận tín hiệu: {'LỖI (Đỏ)' if is_ng else 'ĐẠT (Xanh)'}")
                except Exception as e:
                    print(f"Lỗi gửi PLC: {e}")

            # 3. Sau khi xong, đẩy kết quả về giao diện chính
            self.root.after(0, lambda: self.finish_check_ui(annotated, info, conclusion, is_ng, details, timestamp))

        except Exception as e:
            print(f"Lỗi luồng xử lý: {e}")
            self.root.after(0, self.reset_system)
        finally:
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass

    def finish_check_ui(self, annotated, info, conclusion, is_ng, details, timestamp):
        """Cập nhật kết quả lên màn hình (Chạy trên luồng chính)"""
        fg_color = COLOR_RED if is_ng else COLOR_GREEN
        self.lbl_info.config(text=info, fg=fg_color)
        self.lbl_status.config(text=conclusion, fg=fg_color)
        
        self.txt_details.delete('1.0', tk.END)
        for d in details:
            self.txt_details.insert(tk.END, f"• {d}\n")

        if annotated is not None:
            # Giữ nguyên tỷ lệ khung hình (Aspect Ratio) để không bị méo/nhòe
            h, w = annotated.shape[:2]
            scale = min(400 / w, 300 / h)
            new_w, new_h = int(w * scale), int(h * scale)
            
            img_res = cv2.resize(annotated, (new_w, new_h), interpolation=cv2.INTER_AREA)
            img_res = cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB)
            img_res = ImageTk.PhotoImage(Image.fromarray(img_res))
            self.lbl_result_image.config(image=img_res)
            self.lbl_result_image.imgtk = img_res

            # Lưu ảnh kết quả
            save_folder = NG_DIR if is_ng else OK_DIR
            cv2.imwrite(os.path.join(save_folder, f"pill_{timestamp}.jpg"), annotated)

        # Lưu lịch sử
        self.save_to_csv(timestamp, conclusion, is_ng, details)

        # --- CậP NHẬT ĐẾM RIÊNG Và GHI XUỐNG PLC CHO ESP32 ĐỌC ---
        if self.plc_connected:
            try:
                if self.current_product == "Viên rời":
                    if is_ng:
                        self.vien_ng += 1
                    else:
                        self.vien_ok += 1
                    logic.send_product_specific_counts("Viên rời", self.vien_ok, self.vien_ng)
                elif self.current_product == "Vỉ thuốc":
                    if is_ng:
                        self.vi_ng += 1
                    else:
                        self.vi_ok += 1
                    logic.send_product_specific_counts("Vỉ thuốc", self.vi_ok, self.vi_ng)
            except Exception as e:
                print(f"Lỗi ghi thống kê xuống PLC: {e}")

        # Chờ một khoảng thời gian ngắn để PLC nhận tín hiệu rồi reset
        ms_duration = int(PLC_SIGNAL_DURATION * 1000)
        self.root.after(ms_duration, self.reset_system)

    def save_to_csv(self, timestamp, conclusion, is_ng, details):
        """Hàm lưu lịch sử kiểm tra vào file CSV cho Dashboard"""
        try:
            file_exists = os.path.isfile(EXCEL_FILENAME)
            
            det_str = ", ".join(details)
            full_result = f"{conclusion} - {det_str}" if details else conclusion
            
            # Chuyển timestamp từ 20260427_233232 sang dạng đọc được HH:MM:SS
            try:
                dt = datetime.datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
                time_str = dt.strftime("%H:%M:%S")
                date_str = dt.strftime("%Y-%m-%d")
                display_time = f"{date_str} {time_str}"
            except:
                display_time = timestamp
            
            with open(EXCEL_FILENAME, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    # 4 cột phải khớp với JS: log[1]=Sản phẩm, log[2]=Kết quả, log[3]=Thời gian
                    writer.writerow(['STT', 'Sản phẩm', 'Kết quả', 'Thời gian'])
                
                self.total_count = getattr(self, 'total_count', 0) + 1
                # Lưu is_ng vào kết quả để dashboard đếm chính xác
                ng_marker = "[NG]" if is_ng else "[OK]"
                writer.writerow([self.total_count, self.current_product, f"{ng_marker} {full_result}", display_time])
                print(f">>> ĐÃ LƯU: [{self.total_count}] {'NG' if is_ng else 'OK'} | {self.current_product} | {time_str}")
        except Exception as e:
            print(f"Lỗi lưu CSV: {e}")

    def open_excel_file(self):
        if os.path.exists(EXCEL_FILENAME):
            os.startfile(EXCEL_FILENAME)
        else:
            messagebox.showinfo("Thông báo", "Chưa có dữ liệu lịch sử.")

    def reset_system(self):
        self.is_paused = False
        self.is_processing = False
        
        # --- RESET BIT PLC VỀ FALSE ---
        if self.plc_connected:
            try:
                # Tắt cả 2 đèn OK và NG
                logic.send_result_to_plc(is_error=False, is_ok=False)
                print("Hệ thống: Đã reset tín hiệu đèn (OK/NG về False)")
            except Exception as e:
                print(f"Lỗi Reset PLC: {e}")

        # Giữ nguyên nhãn "SẴN SÀNG" để chờ lượt tiếp theo
        self.lbl_status.config(text="ĐANG QUÉT...", fg=COLOR_BLUE)

    def update_frame(self):
        if not self.is_paused:
            ret, frame = self.vs.read()
            self.cam_connected = ret
            if ret:
                self.current_frame = frame.copy()
                display_frame = cv2.resize(frame, (800, 600))
                display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                img = ImageTk.PhotoImage(Image.fromarray(display_frame))
                self.lbl_webcam.config(image=img)
                self.lbl_webcam.imgtk = img
        self.root.after(20, self.update_frame)

    def on_closing(self):
        self.vs.release()
        self.root.destroy()
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()