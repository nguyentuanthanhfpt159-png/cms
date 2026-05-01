#include <WiFi.h>
#include <WebServer.h>
#include <ModbusIP_ESP32.h>

// --- CẤU HÌNH WIFI & PLC ---
const char* ssid = "TEN_WIFI_CUA_BAN";
const char* password = "MAT_KHAU_WIFI";
IPAddress plcIP(192, 168, 0, 1); // Thay bằng IP của PLC S7-1200

ModbusIP mb;
WebServer server(80);

// Biến lưu dữ liệu
uint16_t data[4] = {0, 0, 0, 0}; // [Tổng, OK, NG, Trạng thái]

// --- GIAO DIỆN WEB (HTML/CSS/JS) ---
const char PAGE_MAIN[] PROGMEM = R"=====(
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>IoT Pharma Monitor</title>
  <style>
    body { font-family: sans-serif; background: #121212; color: white; text-align: center; padding-top: 50px; }
    .container { display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; }
    .card { background: #1e1e1e; padding: 20px; border-radius: 15px; width: 150px; border-bottom: 5px solid #00ff00; }
    .card.total { border-color: #007bff; }
    .card.ng { border-color: #ff0000; }
    .val { font-size: 40px; font-weight: bold; margin: 10px 0; }
    .status { font-size: 20px; margin-top: 30px; padding: 10px; border-radius: 5px; display: inline-block; }
  </style>
</head>
<body>
  <h1>HỆ THỐNG GIÁM SÁT SẢN XUẤT</h1>
  <div class="container">
    <div class="card total"><div>TỔNG</div><div class="val" id="total">0</div></div>
    <div class="card"><div>THUỐC OK</div><div class="val" id="ok">0</div></div>
    <div class="card ng"><div>THUỐC NG</div><div class="val" id="ng">0</div></div>
  </div>
  <div id="stt_box" class="status">Đang kết nối...</div>

  <script>
    setInterval(() => {
      fetch('/api').then(r => r.json()).then(d => {
        document.getElementById('total').innerText = d[0];
        document.getElementById('ok').innerText = d[1];
        document.getElementById('ng').innerText = d[2];
        let s = document.getElementById('stt_box');
        if(d[3] == 1) { s.innerText = "HỆ THỐNG: ĐANG CHẠY"; s.style.background = "green"; }
        else { s.innerText = "HỆ THỐNG: ĐANG DỪNG"; s.style.background = "orange"; }
      });
    }, 1000);
  </script>
</body>
</html>
)=====";

void setup() {
  Serial.begin(115200);
  
  // 1. Kết nối WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi OK! IP ESP32: ");
  Serial.println(WiFi.localIP());

  // 2. Cấu hình Modbus
  mb.client();

  // 3. Cấu hình Web Server
  server.on("/", []() { server.send(200, "text/html", PAGE_MAIN); });
  server.on("/api", []() {
    String j = "[" + String(data[0]) + "," + String(data[1]) + "," + String(data[2]) + "," + String(data[3]) + "]";
    server.send(200, "application/json", j);
  });
  server.begin();
}

void loop() {
  mb.task();
  server.handleClient();

  static uint32_t lastRead = 0;
  if (millis() - lastRead > 1000) { // Mỗi 1 giây đọc PLC 1 lần
    lastRead = millis();
    if (mb.isConnected(plcIP)) {
      mb.readHreg(plcIP, 0, data, 4); // Đọc 4 thanh ghi từ offset 0
    } else {
      mb.connect(plcIP);
    }
  }
}
