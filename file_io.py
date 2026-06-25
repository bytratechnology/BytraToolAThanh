"""Ghi file an toàn trên Windows (tránh WinError 32 khi file đang bị khóa)."""

import os
import shutil
import stat
import sys
import time
from pathlib import Path

MAX_RETRIES = 5
RETRY_DELAY = 0.5
TREE_MAX_RETRIES = 12
TREE_RETRY_DELAY = 0.75


def locked_file_message(path) -> str:
    name = Path(path).name.lower()
    path_str = str(path)
    if name == "_work" or path_str.endswith("_work"):
        hint = (
            "đóng MATLAB / Excel / Notepad đang mở file trong thư mục _work "
            "(hoặc đợi vài giây rồi chạy lại)"
        )
    elif name.endswith((".xlsx", ".xls")):
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


def _chmod_writable_and_retry(func, path, _exc_info):
    """Windows: bỏ read-only rồi thử xóa lại (MATLAB/Excel đôi khi để file read-only)."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise


def remove_tree(path, *, retries: int | None = None, delay: float | None = None) -> None:
    """Xóa cây thư mục — retry khi WinError 32 (file đang bị khóa trên Windows)."""
    path = Path(path)
    if not path.exists():
        return

    max_retries = retries if retries is not None else (
        TREE_MAX_RETRIES if sys.platform == "win32" else MAX_RETRIES
    )
    base_delay = delay if delay is not None else (
        TREE_RETRY_DELAY if sys.platform == "win32" else RETRY_DELAY
    )

    last_err: BaseException | None = None
    for attempt in range(max_retries):
        try:
            shutil.rmtree(path, onerror=_chmod_writable_and_retry)
            return
        except OSError as exc:
            if not _is_file_locked_error(exc):
                raise
            last_err = exc
            if attempt < max_retries - 1:
                time.sleep(base_delay * (attempt + 1))

    raise PermissionError(locked_file_message(path)) from last_err
