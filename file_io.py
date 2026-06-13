"""Ghi file an toàn trên Windows (tránh WinError 32 khi file đang bị khóa)."""

import os
import shutil
import time
from pathlib import Path

MAX_RETRIES = 5
RETRY_DELAY = 0.5


def locked_file_message(path) -> str:
    name = Path(path).name.lower()
    if name.endswith((".xlsx", ".xls")):
        hint = "đóng Microsoft Excel (hoặc file Excel đang mở trong thư mục output)"
    elif name.endswith(".inp"):
        hint = "đóng Abaqus / Notepad đang mở file .inp"
    elif name.endswith(".m"):
        hint = "đóng MATLAB Editor đang mở file .m"
    else:
        hint = "đóng chương trình đang mở file này (Notepad, Excel, v.v.)"

    return (
        f"Không thể ghi file:\n{path}\n\n"
        f"Vui lòng {hint}, rồi chạy lại Bước 1."
    )


def _is_file_locked_error(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 32:
        return True
    return "being used by another process" in str(exc)


def run_with_retry(action, path, *, retries=MAX_RETRIES):
    last_err = None
    for attempt in range(retries):
        try:
            return action()
        except (PermissionError, OSError) as exc:
            if not _is_file_locked_error(exc):
                raise
            last_err = exc
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY)
    raise PermissionError(locked_file_message(path)) from last_err


def write_text(path, content, encoding="utf-8"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")

    def do_write():
        tmp.write_text(content, encoding=encoding)
        os.replace(tmp, path)

    try:
        run_with_retry(do_write, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def replace_file(tmp_path, final_path):
    tmp_path = Path(tmp_path)
    final_path = Path(final_path)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    run_with_retry(lambda: os.replace(tmp_path, final_path), final_path)
