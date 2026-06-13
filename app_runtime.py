"""Đường dẫn khi chạy từ mã nguồn hoặc file .exe (PyInstaller)."""

import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def application_dir() -> Path:
    """Thư mục chứa file .exe hoặc thư mục dự án (ghi kết quả)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    """Thư mục chứa tài nguyên đóng gói (file mẫu A_THANH)."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return application_dir()
