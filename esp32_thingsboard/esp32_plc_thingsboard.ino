/*
 * ============================================================
 *  ESP32: HỆ THỐNG IoT GIÁM SÁT & ĐIỀU KHIỂN PLC (BẢN CHUẨN)
 *  - Giám sát: OK, NG, Tổng, Trạng thái Power/Camera/PLC
 *  - Điều khiển: Nút Switch (Khóa/Mở) & Nút Tròn (Bật máy từ xa)
 * ============================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ============================================================
//  ⚙️  CẤU HÌNH
// ============================================================
const char* ssid     = "Bon Chi Em 2.4GHZ";
const char* password = "01989897";
IPAddress plcIP(192, 168, 1, 50);

const char* TB_HOST  = "thingsboard.cloud";
const char* TB_TOKEN = "RbdItkwcixlgcBlXFdFo"; 

WiFiClient plcClient; WiFiClient mqttWifiClient;
PubSubClient mqttClient(mqttWifiClient);

uint16_t data[9] = {0, 0, 0, 0, 0, 0, 0, 0, 0}; 
unsigned long lastRead = 0, lastPublish = 0, lastRetry = 0;

// ============================================================
//  HÀM GHI MODBUS (Register 9 tương ứng DB1.DBW18)
// ============================================================
void writeModbusRegister(uint16_t regAddr, uint16_t value) {
  if (!plcClient.connected() && !plcClient.connect(plcIP, 502)) return;
  
  uint8_t req[] = {0, 3, 0, 0, 0, 6, 255, 6, (uint8_t)(regAddr >> 8), (uint8_t)(regAddr & 0xFF), (uint8_t)(value >> 8), (uint8_t)(value & 0xFF)};
  plcClient.write(req, 12);
  
  unsigned long timeout = millis();
  while (plcClient.available() < 12 && millis() - timeout < 500);
  while (plcClient.available()) {
    plcClient.read(); 
  }
  
  Serial.printf(">>> Modbus Write: Reg %d = %d\n", regAddr, value);
}

// ============================================================
//  HÀM XỬ LÝ LỆNH TỪ WEB (RPC)
// ============================================================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String responseTopic = String(topic); responseTopic.replace("request", "response");
  StaticJsonDocument<200> doc; deserializeJson(doc, payload, length);
  String method = doc["method"];
  
  if (method == "setValue") {
    bool params = doc["params"];
    writeModbusRegister(9, params ? 1 : 0);
  } 
  else if (method == "remoteStart") {
    writeModbusRegister(9, 2); delay(500); writeModbusRegister(9, 1);
  }
  else if (method == "resetP1") {
    writeModbusRegister(9, 3); delay(500); writeModbusRegister(9, 1);
  }
  else if (method == "resetP2") {
    writeModbusRegister(9, 4); delay(500); writeModbusRegister(9, 1);
  }
  
  mqttClient.publish(responseTopic.c_str(), "{}");
}

// ============================================================
//  HÀM ĐỌC DỮ LIỆU PLC
// ============================================================
void readModbusRaw() {
  if (!plcClient.connected()) {
    if (!plcClient.connect(plcIP, 502)) { Serial.println(">>> PLC Offline!"); return; }
  }
  uint8_t req[] = {0, 1, 0, 0, 0, 6, 255, 3, 0, 0, 0, 9};
  plcClient.write(req, 12);
  unsigned long timeout = millis();
  while (plcClient.available() < 27 && millis() - timeout < 500);
  if (plcClient.available() >= 27) {
    uint8_t res[27]; for (int i = 0; i < 27; i++) res[i] = plcClient.read();
    if (res[7] == 0x03) { for (int i = 0; i < 9; i++) data[i] = (res[9 + i*2] << 8) | res[10 + i*2]; }
  } else { while(plcClient.available()) plcClient.read(); plcClient.stop(); }
}

// ============================================================
//  HÀM GỬI TELEMETRY LÊN THINGSBOARD
// ============================================================
void publishToThingsBoard() {
  if (!mqttClient.connected()) return;

  uint16_t bits = data[0];
  uint16_t prod_id = data[4]; // 1: Viên, 2: Vỉ

  bool sys_active = (bits >> 11) & 0x01; // Bit 11 là Hệ thống
  bool cam_online = (bits >> 13) & 0x01; // Bit 13 là Camera
  
  // Lấy số liệu từng loại từ PLC
  uint16_t ok1 = data[5]; uint16_t ng1 = data[6];
  uint16_t ok2 = data[7]; uint16_t ng2 = data[8];

  // Logic hiển thị thông minh: Ưu tiên loại đang chạy
  uint16_t ok_hien_thi = (prod_id == 1) ? ok1 : (prod_id == 2) ? ok2 : (ok1 + ok2);
  uint16_t ng_hien_thi = (prod_id == 1) ? ng1 : (prod_id == 2) ? ng2 : (ng1 + ng2);

  StaticJsonDocument<1024> doc;
  doc["total_ok"]    = ok_hien_thi; 
  doc["total_ng"]    = ng_hien_thi; 
  doc["total_all"]   = ok_hien_thi + ng_hien_thi;
  doc["sys_active"]  = sys_active ? 1 : 0;
  doc["cam_online"]  = cam_online ? 1 : 0;
  doc["plc_online"]  = plcClient.connected() ? 1 : 0;
  doc["product_id"]  = prod_id;
  doc["product_name"] = (prod_id == 1) ? "Vien roi" : (prod_id == 2) ? "Vi thuoc" : "Chua ro";

  // Dữ liệu chi tiết cho biểu đồ
  doc["ok1"] = ok1; doc["ng1"] = ng1;
  doc["ok2"] = ok2; doc["ng2"] = ng2;

  char payload[1024]; 
  serializeJson(doc, payload);
  mqttClient.publish("v1/devices/me/telemetry", payload);
  
  // In log cực chi tiết để debug
  Serial.printf(">>> ProdID:%d | OK1:%d | OK2:%d | CurrentOK:%d\n", prod_id, ok1, ok2, ok_hien_thi);
}

void connectToThingsBoard() {
  if (millis() - lastRetry > 5000) {
    lastRetry = millis();
    Serial.print(">>> Connecting ThingsBoard...");
    if (mqttClient.connect("ESP32_Pharma_Final", TB_TOKEN, NULL)) {
      Serial.println(" OK!"); mqttClient.subscribe("v1/devices/me/rpc/request/+");
    } else { Serial.println(" Fail, retry in 5s"); }
  }
}

void setup() {
  Serial.begin(115200);
  IPAddress local_IP(192, 168, 1, 100), gateway(192, 168, 1, 1), subnet(255, 255, 255, 0), dns(8, 8, 8, 8);
  WiFi.config(local_IP, gateway, subnet, dns);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\n>>> WiFi OK!");
  mqttClient.setServer(TB_HOST, 1883); mqttClient.setCallback(mqttCallback);
}

void loop() {
  if (!mqttClient.connected()) connectToThingsBoard();
  else mqttClient.loop();
  
  if (millis() - lastRead > 1000) { lastRead = millis(); readModbusRaw(); }
  if (millis() - lastPublish > 3000) { lastPublish = millis(); publishToThingsBoard(); }
}
