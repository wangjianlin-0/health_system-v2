$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Push-Location frontend
try {
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name WeiBuXinZhi `
    --paths business_logic --collect-submodules app --collect-submodules ai_model `
    --collect-all openecg --collect-all opendsp --collect-all onnxruntime `
    --collect-submodules uvicorn --hidden-import tkinter `
    --add-data 'frontend/dist;frontend/dist' --add-data 'business_logic/db;business_logic/db' `
    --add-data 'csv/ptbxl_00001_lead_II_500Hz_10s.csv;csv' `
    --add-data 'csv/LICENSE-PTBXL.txt;csv' desktop_launcher.py
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed' }
