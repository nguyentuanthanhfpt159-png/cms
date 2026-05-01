# Script chạy local cho dự án Pharma Monitor
# Chạy script này bằng cách gõ: .\run_local.ps1

Write-Host "--- ĐANG KHỞI ĐỘNG BACKEND (FLASK) ---" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd fe/api; python index.py"

Write-Host "--- ĐANG KHỞI ĐỘNG FRONTEND (NEXT.JS) ---" -ForegroundColor Green
cd fe
npm run dev
