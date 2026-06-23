"""Tìm, lưu và chạy lệnh Abaqus — tự phát hiện khi cài trên Windows."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from app_runtime import application_dir

CONFIG_FILE_NAME = "abaqus_path.txt"


def config_file_path() -> Path:
    """File cấu hình luôn nằm cạnh .exe / thư mục app (không phụ thuộc cwd)."""
    return application_dir() / CONFIG_FILE_NAME


def _read_config_lines() -> list[str]:
    path = config_file_path()
    if not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def is_valid_abaqus_command(command: str) -> bool:
    expanded = os.path.expandvars(os.path.expanduser(command.strip()))
    if not expanded:
        return False
    path = Path(expanded)
    if path.is_file():
        return True
    return shutil.which(expanded) is not None


def load_saved_abaqus_command() -> str | None:
    for line in _read_config_lines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if is_valid_abaqus_command(text):
            return text
    return None


def save_abaqus_command(command: str) -> Path:
    command = command.strip()
    if not command:
        raise ValueError("Đường dẫn Abaqus không được để trống.")
    if not is_valid_abaqus_command(command):
        raise FileNotFoundError(f"Không tìm thấy file/lệnh Abaqus:\n{command}")

    path = config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "# Duong dan Abaqus — Windows: abaqus.bat trong thu muc SIMULIA\\Commands\n"
        f"{command}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _windows_search_roots() -> list[Path]:
    roots: list[Path] = [
        Path(r"C:\SIMULIA"),
        Path(r"C:\Program Files\SIMULIA"),
        Path(r"C:\Program Files\Dassault Systemes"),
        Path(r"C:\Program Files (x86)\SIMULIA"),
        Path(r"C:\Program Files (x86)\Dassault Systemes"),
    ]
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        value = os.environ.get(key, "").strip()
        if value:
            roots.append(Path(value) / "SIMULIA")
            roots.append(Path(value) / "Dassault Systemes")
    return [root for root in roots if root.is_dir()]


def _registry_abaqus_candidates() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []

    found: list[str] = []
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Dassault Systemes"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Dassault Systemes"),
    ]
    for hive, subkey in keys:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, i)
                        i += 1
                        with winreg.OpenKey(key, name) as sub:
                            try:
                                install_dir, _ = winreg.QueryValueEx(sub, "InstallDir")
                                bat = Path(str(install_dir)) / "Commands" / "abaqus.bat"
                                if bat.is_file():
                                    found.append(str(bat))
                            except OSError:
                                pass
                    except OSError:
                        break
        except OSError:
            continue
    return found


def search_abaqus_candidates() -> list[str]:
    """Quét các vị trí cài Abaqus phổ biến trên Windows."""
    found: list[str] = []
    seen: set[str] = set()

    def add(candidate: Path | str | None):
        if not candidate:
            return
        text = str(candidate).strip()
        if not text or text in seen:
            return
        if is_valid_abaqus_command(text):
            seen.add(text)
            found.append(text)

    add(load_saved_abaqus_command())

    env_path = os.environ.get("ABAQUS_CMD", "").strip()
    if env_path:
        add(env_path)

    abaqus_home = os.environ.get("ABAQUS_HOME", "").strip()
    if abaqus_home:
        home = Path(os.path.expandvars(abaqus_home))
        add(home / "Commands" / "abaqus.bat")

    add(shutil.which("abaqus"))

    if sys.platform == "win32":
        for reg_path in _registry_abaqus_candidates():
            add(reg_path)
        for root in _windows_search_roots():
            add(root / "Commands" / "abaqus.bat")
            for bat in root.glob("**/Commands/abaqus.bat"):
                add(bat)
    elif sys.platform == "darwin":
        for app in sorted(Path("/Applications").glob("Abaqus*.app"), reverse=True):
            add(app / "Contents" / "MacOS" / "abaqus")

    return found


def find_abaqus_command() -> str | None:
    candidates = search_abaqus_candidates()
    return candidates[0] if candidates else None


def auto_configure_abaqus(explicit: str | None = None) -> str | None:
    """
    Tự tìm Abaqus khi mở app / trước khi chạy phân tích.
    Nếu tìm được → lưu vào abaqus_path.txt cạnh .exe.
    """
    if explicit and explicit.strip() and is_valid_abaqus_command(explicit):
        try:
            save_abaqus_command(explicit.strip())
        except OSError:
            pass
        return explicit.strip()

    found = find_abaqus_command()
    if found:
        try:
            save_abaqus_command(found)
        except OSError:
            pass
    return found


def resolve_abaqus_command(explicit: str | None = None) -> str:
    cmd = auto_configure_abaqus(explicit)
    if cmd:
        return cmd

    hints = [
        "Không tìm thấy Abaqus trên máy này.",
        "Cài Abaqus (SIMULIA) hoặc bấm 「Tìm tự động」/ chọn abaqus.bat trong app.",
        f"File cấu hình: {config_file_path()}",
        "Ví dụ Windows: C:\\SIMULIA\\Commands\\abaqus.bat",
    ]
    raise FileNotFoundError("\n".join(hints))


def build_abaqus_subprocess_args(command: str, args: list[str]) -> list[str]:
    command = os.path.expandvars(os.path.expanduser(command.strip()))
    path = Path(command)
    if path.is_file() and sys.platform == "win32" and path.suffix.lower() in {".bat", ".cmd"}:
        return ["cmd", "/c", str(path), *args]
    if path.is_file():
        return [str(path), *args]
    return [command, *args]


def run_abaqus_subprocess(
    command: str,
    args: list[str],
    *,
    cwd: Path | str,
    timeout: int,
) -> subprocess.CompletedProcess:
    argv = build_abaqus_subprocess_args(command, args)
    return subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
