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

# Load biến môi trường từ file .env
load_dotenv()
DB_URL = os.getenv("SUPABASE_URL")

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
        self.root.title("Hệ thống AI Phân loại Dược phẩm - Ver 1.0 (PRO)")
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
                    self.write_status_to_json(False, False)
                    time.sleep(2)
                    continue

            try:
                # --- KIỂM TRA LỆNH TỪ WEB DASHBOARD (COMMAND.JSON) ---
                cmd_path = os.path.join(BASE_DIR, "command.json")
                if os.path.exists(cmd_path):
                    try:
                        with open(cmd_path, "r") as f:
                            cmd_data = json.load(f)
                        if cmd_data.get("cmd") == "set_model":
                            target_id = cmd_data.get("value")
                            print(f">>> NHẬN LỆNH ĐỔI MODEL TỪ WEB: {target_id}")
                            logic.send_product_id_to_plc(target_id)
                            model_name = "Viên rời" if target_id == 1 else "Vỉ thuốc"
                            self.root.after(0, lambda n=model_name: self.combo_product.set(n))
                            self.root.after(0, self.on_product_change)
                        os.remove(cmd_path)
                    except Exception as e:
                        print(f"Lỗi xử lý lệnh từ Web: {e}")

                # --- ĐỒNG BỘ COUNTER TỪ PLC (Hỗ trợ Reset từ ThingsBoard) ---
                # Nếu PLC trả về 0 (đã bị reset), ta phải reset biến Python tương ứng
                # DB1.DBW10=VienOK, DBW12=VienNG, DBW14=ViOK, DBW16=ViNG
                # Ta đọc 8 byte từ offset 10
                raw_counts = logic.plc_client.db_read(logic.DB_NUMBER, 10, 8)
                plc_vien_ok = snap7.util.get_int(raw_counts, 0)
                plc_vien_ng = snap7.util.get_int(raw_counts, 2)
                plc_vi_ok   = snap7.util.get_int(raw_counts, 4)
                plc_vi_ng   = snap7.util.get_int(raw_counts, 6)

                if plc_vien_ok == 0 and self.vien_ok > 0: self.vien_ok = 0
                if plc_vien_ng == 0 and self.vien_ng > 0: self.vien_ng = 0
                if plc_vi_ok == 0 and self.vi_ok > 0: self.vi_ok = 0
                if plc_vi_ng == 0 and self.vi_ng > 0: self.vi_ng = 0

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
                            delay = CAPTURE_DELAY_VI if self.current_product == "Vỉ thuốc" else CAPTURE_DELAY_VIEN
                            if delay > 0: time.sleep(delay)
                            self.root.after(0, self.perform_check)
                    self.last_sensor_state = current_sensor

                    # Kiểm tra lệnh đổi model từ PLC
                    plc_product_id = logic.read_product_id_from_plc() 
                    expected_id = 1 if self.current_product == "Viên rời" else 2
                    if plc_product_id > 0 and plc_product_id != expected_id:
                        new_name = "Viên rời" if plc_product_id == 1 else "Vỉ thuốc"
                        self.current_product = new_name
                        self.root.after(0, lambda n=new_name: self.combo_product.set(n))
                        self.root.after(0, lambda p=MODELS_CONFIG[new_name]: self.load_selected_model(p))
                
                # --- GHI TRẠNG THÁI HỆ THỐNG CHO WEB DASHBOARD & PLC ---
                self.write_status_to_json(self.plc_connected, system_active)
                logic.send_camera_status_to_plc(getattr(self, 'cam_connected', False))

            except Exception as e:
                self.plc_connected = False
                logic.disconnect_plc()
                self.lbl_plc_status.config(text="PLC: MẤT KẾT NỐI", fg=COLOR_RED)
                self.write_status_to_json(False, False)
            
            time.sleep(0.05)

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
                cur.execute("""
                    INSERT INTO system_status (id, plc_online, machine_running, cam_online, current_model_id, last_update)
                    VALUES (1, %s, %s, %s, %s, NOW())
                    ON CONFLICT (id) DO UPDATE SET 
                        plc_online = EXCLUDED.plc_online,
                        machine_running = EXCLUDED.machine_running,
                        cam_online = EXCLUDED.cam_online,
                        current_model_id = EXCLUDED.current_model_id,
                        last_update = EXCLUDED.last_update;
                """, (plc_online, machine_running, getattr(self, 'cam_connected', False), 1 if self.current_product == "Viên rời" else 2))
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                print(f"Lỗi đẩy trạng thái lên Supabase: {e}")
        threading.Thread(target=run, daemon=True).start()

    def push_inspection_to_supabase(self, product, result, is_ng, details):
        if not DB_URL or "MAT_KHAU" in DB_URL: return
        def run():
            try:
                conn = psycopg2.connect(DB_URL)
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO inspections (product_name, result, is_ng, details)
                    VALUES (%s, %s, %s, %s);
                """, (product, result, is_ng, " | ".join(details)))
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                print(f"Lỗi đẩy kết quả lên Supabase: {e}")
        threading.Thread(target=run, daemon=True).start()

    def setup_ui(self):
        self.frame_left = tk.Frame(self.root, bg=COLOR_BG)
        self.frame_left.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.frame_right = tk.Frame(self.root, bg=COLOR_FRAME, width=450)
        self.frame_right.pack(side="right", fill="y", padx=10, pady=10)
        self.frame_right.pack_propagate(False)

        tk.Label(self.frame_left, text="HỆ THỐNG AI PHÂN LOẠI DƯỢC PHẨM", font=self.font_title, bg=COLOR_BG).pack(pady=10)
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
        tk.Button(frame_btn, text="KIỂM TRA NGAY", bg=COLOR_BLUE, fg="white", font=("Arial",14,"bold"), width=18, height=2, command=self.action_manual_check).pack(side="left", padx=10)
        tk.Button(frame_btn, text="XEM LỊCH SỬ (.CSV)", bg="#FFA500", fg="white", font=("Arial",14,"bold"), width=18, height=2, command=self.open_excel_file).pack(side="left", padx=10)

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
        if self.current_frame is None: return
        self.is_processing = True
        self.is_paused = True 
        ret, f = self.vs.read()
        if not ret: 
            self.reset_system()
            return
        best_frame = f.copy()
        import numpy as np
        kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
        best_frame = cv2.filter2D(best_frame, -1, kernel)
        threading.Thread(target=self.worker_process, args=(best_frame,), daemon=True).start()

    def worker_process(self, frame):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_img_name = f"pill_{timestamp}.jpg"
        temp_path = os.path.join(BASE_DIR, temp_img_name)
        try:
            cv2.imwrite(temp_path, frame)
            annotated, info, conclusion, is_ng, details = logic.process_image(temp_path, self.model, self.class_names)
            if self.plc_connected:
                # Cập nhật số lượng cục bộ ngay lập tức
                if is_ng:
                    if self.current_product == "Viên rời": self.vien_ng += 1
                    else: self.vi_ng += 1
                else:
                    if self.current_product == "Viên rời": self.vien_ok += 1
                    else: self.vi_ok += 1
                
                try:
                    # Gửi số tổng và số chi tiết lên PLC
                    total_ok = self.vien_ok + self.vi_ok
                    total_ng = self.vien_ng + self.vi_ng
                    logic.send_result_to_plc(is_error=is_ng, is_ok=not is_ng, num_ok=total_ok, num_ng=total_ng)
                    logic.send_product_specific_counts(self.current_product, 
                        self.vien_ok if self.current_product == "Viên rời" else self.vi_ok,
                        self.vien_ng if self.current_product == "Viên rời" else self.vi_ng)
                except: pass
            
            # ĐẨY KẾT QUẢ LÊN SUPABASE
            self.push_inspection_to_supabase(self.current_product, conclusion, is_ng, details)

            self.root.after(0, lambda: self.finish_check_ui(annotated, info, conclusion, is_ng, details, timestamp))
        except Exception as e:
            print(f"Lỗi xử lý: {e}")
            self.root.after(0, self.reset_system)
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)

    def finish_check_ui(self, annotated, info, conclusion, is_ng, details, timestamp):
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
            cv2.imwrite(os.path.join(NG_DIR if is_ng else OK_DIR, f"pill_{timestamp}.jpg"), annotated)
        
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
                self.total_count += 1
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