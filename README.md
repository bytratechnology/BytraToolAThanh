# Phần mềm tự động hoá

Xử lý imperfections tiết diện cho mô hình Abaqus — đọc file `.inp`, tính tham số, chạy incorporation và xuất kết quả.

## Yêu cầu

- Python 3.10+

## Chạy từ mã nguồn

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Quy trình sử dụng

1. **Bước 1:** Chọn file `.inp`, Excel/MATLAB mẫu, thư mục output → xử lý node, tạo Matrix và file MATLAB.
2. **Bước 2:** Nhập tham số (IT, HWL, HWD, tiết diện, slenderness…) → tính D/T/Nl/Nd → chạy incorporation → ghi file `.inp` kết quả (`*_IMPERFECTION.inp`).

## Build cài đặt

| Nền tảng | Lệnh | Kết quả |
|----------|------|---------|
| macOS | `bash build_mac.sh` | `dist/PhanMemTuDongHoa-macOS.zip` |
| Windows | `build_windows.bat` | `dist\PhanMemTuDongHoa-Windows.zip` |

Chi tiết cài đặt: [HUONG_DAN_CAI_DAT.txt](HUONG_DAN_CAI_DAT.txt)

## GitHub Actions

Workflow **Build Release (macOS + Windows)** (`.github/workflows/build-release.yml`):

- Chạy thủ công: **Actions** → **Build Release (macOS + Windows)** → **Run workflow**
- Hoặc push tag `v*` (ví dụ `v1.0.0`)

Tải file zip từ mục **Artifacts** sau khi workflow hoàn tất.

## Cấu trúc chính

```
main.py              # Pipeline bước 1
gui.py               # Giao diện
inputs.py            # Công thức tính D, T, Nl, Nd
incorporation.py     # Logic incorporation (Python)
matlab_writer.py     # Ghi tham số vào file .m
inp_writer.py        # Ghi tọa độ vào file .inp kết quả
A_THANH/             # File mẫu (.inp, .xlsx, .m)
```

## Liên hệ

Dương Trung Kiên — 0968 384 643
