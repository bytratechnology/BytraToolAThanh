import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from incorporation import run_incorporation_python
from inp_writer import write_myfile_to_inp
from paths import DEFAULT_PATHS, ProjectPaths

MATLAB_PATH_FILE = Path("matlab_path.txt")


def find_matlab_executable():
    """Tìm MATLAB: file cấu hình → PATH → /Applications."""
    if MATLAB_PATH_FILE.exists():
        custom = MATLAB_PATH_FILE.read_text(encoding="utf-8").strip()
        if custom and Path(custom).is_file():
            return custom

    env_path = os.environ.get("MATLAB_EXE", "").strip()
    if env_path and Path(env_path).is_file():
        return env_path

    matlab = shutil.which("matlab")
    if matlab:
        return matlab

    apps = Path("/Applications")
    candidates = sorted(apps.glob("MATLAB*.app"), reverse=True)
    for app in candidates:
        exe = app / "bin" / "matlab"
        if exe.is_file():
            return str(exe)

    return None


def _notify(on_progress, message: str):
    print(message, flush=True)
    if on_progress:
        on_progress(message)


def _run_matlab_binary(exe, paths: ProjectPaths, timeout, on_progress=None):
    work_dir = paths.work_dir.resolve()
    script_name = paths.matlab_script_name
    _notify(on_progress, f"Bước 2: Đang chạy MATLAB ({script_name}.m)...")
    result = subprocess.run(
        [exe, "-batch", f"run('{script_name}')"],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(err or "MATLAB chạy thất bại")

    if not paths.myfile_output.exists():
        raise RuntimeError(
            f"MATLAB chạy xong nhưng không tạo {paths.myfile_output}"
        )

    matlab_msg = (result.stdout or "").strip() or "Đã chạy MATLAB thành công."
    _notify(on_progress, f"Bước 2: {matlab_msg}")
    inp_msg = _write_inp(paths, on_progress)
    return f"{matlab_msg}\n{inp_msg}"


def _run_incorporation(paths: ProjectPaths, on_progress=None) -> str:
    _notify(on_progress, "Bước 2: Đang chạy incorporation (Python)...")
    py_msg = run_incorporation_python(
        work_dir=paths.work_dir,
        matrix_file=paths.matrix_output,
        m_file=paths.matlab_output,
        output_file=paths.myfile_output,
    )
    _notify(on_progress, f"Bước 2: {py_msg}")
    inp_msg = _write_inp(paths, on_progress)
    return f"{py_msg}\n{inp_msg}"


def _write_inp(paths: ProjectPaths, on_progress=None) -> str:
    _notify(
        on_progress,
        f"Bước 2: Đang ghi tọa độ vào {paths.inp_result.name} (*Node đầu → *Element)...",
    )
    paths.ensure_output_dir()
    msg = write_myfile_to_inp(
        inp_source=paths.inp_source,
        myfile_path=paths.myfile_output,
        inp_output=paths.inp_result,
    )
    _notify(on_progress, f"Bước 2: {msg}")
    if sys.platform == "win32":
        time.sleep(0.75)
    if paths.cleanup_work_dir():
        _notify(on_progress, "Bước 2: Đã xóa file tạm, chỉ giữ file .inp kết quả.")
    else:
        _notify(
            on_progress,
            f"Bước 2: Cảnh báo — chưa xóa được {paths.work_dir.name} "
            "(file đang bị khóa bởi MATLAB/Excel; có thể xóa thủ công sau).",
        )
    return msg


def run_matlab_script(
    paths: ProjectPaths | None = None,
    matlab_exe=None,
    timeout=600,
    prefer_python=False,
    on_progress=None,
):
    """
    Chạy file .m:
    - Có MATLAB → dùng MATLAB
    - Không có → chạy bằng Python (incorporation.py)
    """
    paths = (paths or DEFAULT_PATHS).resolve()

    if not paths.matlab_output.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {paths.matlab_output}")

    if not prefer_python:
        exe = matlab_exe or find_matlab_executable()
        if exe:
            try:
                return _run_matlab_binary(exe, paths, timeout, on_progress)
            except Exception as exc:
                _notify(on_progress, f"Bước 2: MATLAB lỗi, chuyển sang Python — {exc}")
                msg = _run_incorporation(paths, on_progress)
                return f"{msg}\n(MATLAB lỗi, đã dùng Python: {exc})"

    return _run_incorporation(paths, on_progress)
