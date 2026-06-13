# Phần mềm tự động hoá

Xử lý imperfections tiết diện cho mô hình Abaqus.

## Chạy từ mã nguồn

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build

- **macOS:** `bash build_mac.sh` → `dist/PhanMemTuDongHoa-macOS.zip`
- **Windows:** `build_windows.bat` → `dist\PhanMemTuDongHoa-Windows.zip`

Chi tiết: xem `HUONG_DAN_CAI_DAT.txt`.

## GitHub Actions

Workflow **Build Release (macOS + Windows)** build cả hai nền tảng khi chạy thủ công hoặc push tag `v*`.
