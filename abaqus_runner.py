"""Chạy phân tích Abaqus cho file *_IMPERFECTION.inp — check, submit, build kết quả."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from abaqus_config import (
    resolve_abaqus_command,
    run_abaqus_subprocess,
    start_abaqus_subprocess,
)
from abaqus_job_settings import (
    cae_configure_riks_steps_snippet,
    cae_job_constructor_snippet,
    cli_job_resource_args,
    parse_abaqus_available_cpus,
    patch_inp_riks_no_max_lpf,
    resolve_job_num_cpus,
    set_job_cpu_override,
)
from abaqus_postprocess import OdbPostprocessResult, run_odb_rf3_postprocess
from file_io import write_abaqus_script, write_text

IMPFECTION_SUFFIXES = ("_IMPERFECTION", "-IMPERFECTION", "_IMPFECTION", "-IMPFECTION")
DATACHECK_TIMEOUT = 900
ANALYSIS_MAX_WAIT_SECONDS = 7200  # giới hạn tối đa — xong sớm thì lấy sớm
POLL_INTERVAL_SECONDS = 2
ODB_STABLE_POLLS = 5  # ~10s dung lượng .odb không đổi
FINAL_VERIFY_DELAY_SECONDS = 2  # kiểm tra lại lần cuối trước khi báo xong
WAIT_STATUS_LOG_SECONDS = 6  # in trạng thái chi tiết khi chờ solver
SUBMIT_GRACE_SECONDS = 15  # chờ .sta xuất hiện sau submit (background thoát ngay)
ODB_OUTPUT_SUFFIX = "-TL"  # file .odb deliverable: {job}-TL.odb


@dataclass
class AbaqusRunResult:
    job_name: str
    odb_path: Path
    result_file: Path
    script_path: Path | None = None
    postprocess: OdbPostprocessResult | None = None
    rf3_report_paths: list[Path] = field(default_factory=list)
    rf3_xydata_paths: list[Path] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "Phân tích Abaqus hoàn tất — build xong",
            f"→ {self.odb_path.name}",
            f"→ {self.result_file.name}",
        ]
        for report in self.rf3_report_paths:
            lines.append(f"→ {report.name}")
        for xydata in self.rf3_xydata_paths:
            lines.append(f"→ {xydata.name}")
        if self.postprocess and self.postprocess.summary_path:
            lines.append(f"→ {self.postprocess.summary_path.name}")
        if self.script_path:
            lines.append(f"→ {self.script_path.name}")
        if self.postprocess and self.postprocess.script_path:
            lines.append(f"→ {self.postprocess.script_path.name}")
        return "\n".join(lines)


def deliverable_odb_path(work_dir: Path, job_name: str) -> Path:
    """Đường dẫn file .odb output có hậu tố -TL."""
    return work_dir.resolve() / f"{job_name}{ODB_OUTPUT_SUFFIX}.odb"


def publish_odb_output(source_odb: Path, job_name: str) -> Path:
    """Sao chép .odb gốc từ Abaqus sang {job}-TL.odb sau khi build xong."""
    source_odb = source_odb.resolve()
    dest = deliverable_odb_path(source_odb.parent, job_name)
    shutil.copy2(source_odb, dest)
    return dest


def sanitize_job_name(name: str, *, max_len: int = 38) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
    cleaned = cleaned.strip("_") or "Job"
    return cleaned[:max_len]


def _read_inp_heading_value(inp_path: Path, key: str) -> str | None:
    try:
        with inp_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for i, line in enumerate(handle):
                if i > 30:
                    break
                marker = f"{key}:"
                if marker in line:
                    segment = line.split(marker, 1)[1]
                    if key == "Job name" and "Model name:" in segment:
                        segment = segment.split("Model name:", 1)[0]
                    return segment.strip()
    except OSError:
        pass
    return None


def derive_job_name(inp_path: Path) -> str:
    job = _read_inp_heading_value(inp_path, "Job name")
    if job:
        return sanitize_job_name(job)
    stem = inp_path.stem
    if stem.endswith("_IMPERFECTION"):
        stem = stem[: -len("_IMPERFECTION")]
    return sanitize_job_name(stem)


def derive_model_name(inp_path: Path, job_name: str) -> str:
    model = _read_inp_heading_value(inp_path, "Model name")
    if model:
        return sanitize_job_name(model, max_len=64)
    return sanitize_job_name(job_name, max_len=64)


def _inp_cli_arg(inp_path: Path) -> str:
    """Đường dẫn .inp tuyệt đối — tránh lệch cwd trên Windows."""
    return str(inp_path.resolve())


def discover_job_name(work_dir: Path, hint: str) -> str:
    """Tìm tên job thực tế từ .sta/.lck/.odb trong thư mục (Abaqus đôi khi khác hint)."""
    work_dir = work_dir.resolve()
    hint = sanitize_job_name(hint)

    if (work_dir / f"{hint}.sta").is_file():
        return hint

    candidates: list[Path] = []
    for pattern in ("*.sta", "*.lck", "*.odb"):
        candidates.extend(work_dir.glob(pattern))

    if not candidates:
        return hint

    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    return newest.stem


def _submit_log_path(work_dir: Path) -> Path:
    return work_dir.resolve() / "abaqus_submit.log"


def _read_submit_log_tail(work_dir: Path, lines: int = 30) -> str:
    path = _submit_log_path(work_dir)
    if not path.is_file():
        return ""
    try:
        tail = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:]
        return "\n".join(tail).strip()
    except OSError:
        return ""


def find_imperfection_inp(output_dir: Path, inp_source: Path) -> Path | None:
    output_dir = output_dir.resolve()
    stem = inp_source.stem

    for suffix in IMPFECTION_SUFFIXES:
        candidate = output_dir / f"{stem}{suffix}{inp_source.suffix}"
        if candidate.is_file():
            return candidate

    for pattern in ("*IMPFECTION*.inp", "*IMPERFECTION*.inp"):
        matches = sorted(output_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]

    return None


def _inp_contains_marker(inp_path: Path, marker: str, *, scan_bytes: int = 5_000_000) -> bool:
    target = marker.upper()
    read = 0
    try:
        with inp_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                read += len(line)
                if target in line.upper():
                    return True
                if read >= scan_bytes:
                    break
    except OSError:
        return False
    return False


def validate_imperfection_inp(inp_path: Path) -> list[str]:
    """Kiểm tra file .inp trước khi submit — trả về danh sách lỗi (rỗng = OK)."""
    errors: list[str] = []
    inp_path = inp_path.resolve()

    if not inp_path.is_file():
        return [f"Không tìm thấy file: {inp_path}"]

    if inp_path.stat().st_size == 0:
        errors.append(f"File rỗng: {inp_path.name}")

    name_upper = inp_path.name.upper()
    if "IMPFECTION" not in name_upper and "IMPERFECTION" not in name_upper:
        errors.append(f"Tên file không phải imperfection: {inp_path.name}")

    for marker in ("*Heading", "*Node"):
        if not _inp_contains_marker(inp_path, marker, scan_bytes=500_000):
            errors.append(f"Thiếu keyword {marker} trong file .inp")

    if not _inp_contains_marker(inp_path, "*Element", scan_bytes=50_000_000):
        errors.append("Thiếu keyword *Element trong file .inp")

    if not _inp_contains_marker(inp_path, "*Step", scan_bytes=50_000_000):
        errors.append("Thiếu *Step — file .inp có thể chưa đủ nội dung phân tích")

    return errors


def _notify(on_progress, message: str):
    print(message, flush=True)
    if on_progress:
        on_progress(message)


def _read_job_log_tail(work_dir: Path, job_name: str, lines: int = 25) -> str:
    for name in (f"{job_name}.dat", f"{job_name}.msg", f"{job_name}.log"):
        path = work_dir / name
        if not path.is_file():
            continue
        try:
            tail = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:]
            if tail:
                return "\n".join(tail)
        except OSError:
            continue
    return ""


def _read_sta_tail(work_dir: Path, job_name: str, lines: int = 8) -> str:
    sta = work_dir / f"{job_name}.sta"
    if not sta.is_file():
        return ""
    try:
        return "\n".join(sta.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:])
    except OSError:
        return ""


def _list_job_artifacts(work_dir: Path, job_name: str) -> str:
    """Liệt kê file liên quan job trong thư mục làm việc (debug khi thiếu .odb)."""
    work_dir = work_dir.resolve()
    patterns = (
        f"{job_name}.*",
        "*IMPERFECTION*.odb",
        "*IMPFECTION*.odb",
        "*.odb",
        f"{job_name}*.sta",
        f"{job_name}*.dat",
    )
    found: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in sorted(work_dir.glob(pattern)):
            if path.name in seen:
                continue
            seen.add(path.name)
            found.append(path.name)
    return ", ".join(found) if found else "(không có file .odb/.sta/.dat)"


def find_odb_path(work_dir: Path, job_name: str) -> Path | None:
    """Tìm file .odb — ưu tiên đúng tên job, sau đó .odb mới nhất trong thư mục."""
    work_dir = work_dir.resolve()
    primary = work_dir / f"{job_name}.odb"
    if primary.is_file() and primary.stat().st_size > 0:
        return primary

    candidates = [
        p
        for p in work_dir.glob("*.odb")
        if p.is_file() and p.stat().st_size > 0
    ]
    if not candidates:
        return None

    job_lower = job_name.lower()
    for path in candidates:
        if path.stem.lower() == job_lower:
            return path

    stem_hint = job_name.split("_IMPERFECTION")[0].lower()
    for path in candidates:
        if stem_hint and stem_hint in path.stem.lower():
            return path

    return max(candidates, key=lambda p: p.stat().st_mtime)


def get_sta_status(work_dir: Path, job_name: str) -> str | None:
    """Đọc trạng thái từ {job}.sta — COMPLETED | FAILED | None (đang chạy)."""
    sta = work_dir / f"{job_name}.sta"
    if not sta.is_file():
        return None

    try:
        lines = [
            line.strip()
            for line in sta.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip()
        ]
    except OSError:
        return None

    if not lines:
        return None

    recent = [line.upper() for line in lines[-8:]]
    if any(
        token in line
        for line in recent[-3:]
        for token in ("ERROR", "ABORT", "TERMINATED", "FAILED")
    ):
        return "FAILED"

    if any("RUNNING" in line or "SUBMITTED" in line for line in recent[-3:]):
        return None

    # Chỉ tin COMPLETED khi dòng cuối .sta ghi rõ đã xong (tránh step giữa chừng).
    last = recent[-1]
    if "COMPLETED" in last and "RUNNING" not in last:
        return "COMPLETED"

    return None


def _job_lock_active(work_dir: Path, job_name: str) -> bool:
    """Abaqus tạo .lck khi job còn chạy — còn file này thì chưa xong."""
    work_dir = work_dir.resolve()
    for name in (f"{job_name}.lck", "abaqus.rpy.lock"):
        if (work_dir / name).is_file():
            return True
    return False


def get_completion_status(work_dir: Path, job_name: str) -> str | None:
    """Trả về COMPLETED chỉ khi .sta ghi COMPLETED (không đoán từ .odb đang ghi)."""
    return get_sta_status(work_dir, job_name)


def _odb_file_size(odb: Path | None) -> int | None:
    if odb is None:
        return None
    try:
        return odb.stat().st_size if odb.is_file() else None
    except OSError:
        return None


def _is_odb_fully_written(
    odb: Path | None,
    *,
    last_size: int | None,
    stable_polls: int,
) -> tuple[bool, int | None, int]:
    """
    .odb chỉ coi là xong khi dung lượng không tăng qua ODB_STABLE_POLLS lần poll.
    Trả về (ready, new_size, new_stable_polls).
    """
    size = _odb_file_size(odb)
    if size is None or size <= 0:
        return False, size, 0

    if last_size is not None and size == last_size:
        stable_polls += 1
    else:
        stable_polls = 0

    ready = stable_polls >= ODB_STABLE_POLLS - 1
    return ready, size, stable_polls


def _is_build_fully_finished(
    work_dir: Path,
    job_name: str,
    odb: Path | None,
    *,
    last_odb_size: int | None,
    odb_stable_polls: int,
    process: subprocess.Popen | None,
) -> tuple[bool, int | None, int, str]:
    """
    Chỉ True khi solver thật sự xong:
    .sta COMPLETED (dòng cuối) + không còn .lck + .odb ổn định + tiến trình Abaqus đã thoát.
    Trả về (ready, new_size, new_stable_polls, reason_if_not_ready).
    """
    if get_sta_status(work_dir, job_name) != "COMPLETED":
        return False, last_odb_size, odb_stable_polls, "chờ .sta COMPLETED"

    if _job_lock_active(work_dir, job_name):
        return False, last_odb_size, 0, "job còn file .lck (đang chạy)"

    if odb is None:
        return False, last_odb_size, 0, "chờ file .odb"

    ready, size, stable_polls = _is_odb_fully_written(
        odb,
        last_size=last_odb_size,
        stable_polls=odb_stable_polls,
    )
    if not ready:
        return False, size, stable_polls, f".odb chưa ổn định ({_format_size(odb)})"

    if process is not None and process.poll() is None:
        return False, size, stable_polls, "tiến trình Abaqus chưa kết thúc"

    return True, size, stable_polls, ""


def _verify_build_finished(work_dir: Path, job_name: str, odb: Path) -> bool:
    """Xác minh lần cuối: .sta, .lck, dung lượng .odb không đổi sau vài giây."""
    if get_sta_status(work_dir, job_name) != "COMPLETED":
        return False
    if _job_lock_active(work_dir, job_name):
        return False
    if not odb.is_file():
        return False

    try:
        size_before = odb.stat().st_size
    except OSError:
        return False

    if size_before <= 0:
        return False

    time.sleep(FINAL_VERIFY_DELAY_SECONDS)

    if get_sta_status(work_dir, job_name) != "COMPLETED":
        return False
    if _job_lock_active(work_dir, job_name):
        return False

    try:
        size_after = odb.stat().st_size
    except OSError:
        return False

    return size_after == size_before and size_after > 0


def _analysis_completed(work_dir: Path, job_name: str) -> bool:
    if get_sta_status(work_dir, job_name) != "COMPLETED":
        return False
    if _job_lock_active(work_dir, job_name):
        return False
    return find_odb_path(work_dir, job_name) is not None


def _analysis_failed(work_dir: Path, job_name: str) -> bool:
    return get_completion_status(work_dir, job_name) == "FAILED"


def _parse_sta_progress_line(line: str) -> str:
    """Rút increment / arc length từ dòng .sta (giống CAE Viewer)."""
    text = line.strip()
    if not text:
        return ""

    upper = text.upper()
    if "INCREMENT" in upper:
        parts: list[str] = []
        inc = re.search(r"INCREMENT\s+(\d+)", upper)
        if inc:
            parts.append(f"Increment {inc.group(1)}")
        arc = re.search(r"ARC\s+LENGTH\s*=\s*([\d.E+\-]+)", text, re.IGNORECASE)
        if arc:
            parts.append(f"Arc Length = {arc.group(1)}")
        if "COMPLETED" in upper:
            parts.append("COMPLETED")
        if parts:
            return ", ".join(parts)

    cols = text.split()
    if len(cols) >= 2 and cols[0].isdigit() and cols[1].isdigit():
        return f"Step {cols[0]}, Inc {cols[1]}"

    if upper.startswith("STEP") or "TOTAL TIME" in upper:
        return ""

    return text[:120]


def _read_sta_progress(work_dir: Path, job_name: str) -> str:
    sta = work_dir / f"{job_name}.sta"
    if not sta.is_file():
        return ""
    try:
        lines = [
            line.strip()
            for line in sta.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip()
        ]
    except OSError:
        return ""

    for line in reversed(lines[-12:]):
        parsed = _parse_sta_progress_line(line)
        if parsed:
            return parsed
    return ""


def _build_wait_status_message(
    work_dir: Path,
    job_name: str,
    odb: Path | None,
    *,
    pending_reason: str = "",
) -> str:
    """Tóm tắt trạng thái chờ — increment, .sta, .odb."""
    parts: list[str] = []

    progress = _read_sta_progress(work_dir, job_name)
    if progress:
        parts.append(progress)

    sta_status = get_sta_status(work_dir, job_name)
    if sta_status:
        parts.append(f".sta {sta_status}")
    elif not (work_dir / f"{job_name}.sta").is_file():
        parts.append(".sta chưa có")
    else:
        parts.append(".sta RUNNING")

    if odb is not None and odb.is_file():
        parts.append(f".odb {_format_size(odb)}")
    else:
        parts.append(".odb chưa có")

    if _job_lock_active(work_dir, job_name):
        parts.append(".lck")

    if pending_reason:
        parts.append(pending_reason)

    return " | ".join(parts)


def _drain_subprocess(process: subprocess.Popen | None, *, grace_seconds: float = 30):
    if process is None or process.poll() is not None:
        return
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _job_has_solver_artifacts(work_dir: Path, job_name: str) -> bool:
    work_dir = work_dir.resolve()
    active = discover_job_name(work_dir, job_name)
    if get_sta_status(work_dir, active) is not None:
        return True
    if _job_lock_active(work_dir, active):
        return True
    if find_odb_path(work_dir, active) is not None:
        return True
    return bool(list(work_dir.glob("*.sta")) or list(work_dir.glob("*.lck")))


def _raise_if_process_failed(process: subprocess.Popen | None, work_dir: Path, job_name: str, step_label: str):
    """Báo lỗi nếu tiến trình submit thoát mà không có dấu hiệu solver (.sta/.lck/.odb)."""
    if process is None:
        return
    rc = process.poll()
    if rc is None:
        return
    if _job_has_solver_artifacts(work_dir, job_name):
        return

    active_job = discover_job_name(work_dir, job_name)
    err_parts: list[str] = []
    if rc != 0:
        err_parts.append(f"Exit code: {rc}")
    submit_tail = _read_submit_log_tail(work_dir)
    if submit_tail:
        err_parts.append(f"--- abaqus_submit.log ---\n{submit_tail}")
    log_tail = _read_job_log_tail(work_dir, active_job)
    if log_tail:
        err_parts.append(f"--- job log ---\n{log_tail}")

    listing = sorted(p.name for p in work_dir.iterdir() if p.is_file())[:25]
    files_hint = ", ".join(listing) if listing else "(không có file)"
    detail = "\n\n".join(err_parts) if err_parts else "Không có log Abaqus."
    raise RuntimeError(
        f"{step_label} thoát sớm — chưa thấy .sta/.odb.\n"
        f"Thư mục poll: {work_dir.resolve()}\n"
        f"Job (hint): {job_name}\n"
        f"File trong thư mục: {files_hint}\n\n{detail}"
    )


def _raise_if_failed(result, work_dir: Path, job_name: str, step_label: str):
    if result.returncode == 0 and not _analysis_failed(work_dir, job_name):
        return
    err = (result.stderr or result.stdout or "").strip()
    log_tail = _read_job_log_tail(work_dir, job_name)
    if log_tail:
        err = (err + "\n\n--- Abaqus log ---\n" + log_tail).strip()
    raise RuntimeError(err or f"{step_label} thất bại (job={job_name})")


def _format_size(path: Path) -> str:
    if not path.is_file():
        return "—"
    size = path.stat().st_size
    if size >= 1_048_576:
        return f"{size / 1_048_576:.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def build_result_summary(
    work_dir: Path,
    job_name: str,
    inp_path: Path,
    *,
    status: str = "COMPLETED",
    odb_path: Path | None = None,
    rf3_report_paths: list[Path] | None = None,
    rf3_xydata_paths: list[Path] | None = None,
) -> Path:
    """Ghi file tóm tắt kết quả phân tích Abaqus."""
    work_dir = work_dir.resolve()
    odb = odb_path or find_odb_path(work_dir, job_name) or (work_dir / f"{job_name}.odb")
    result_file = work_dir / f"{job_name}_RESULT.txt"
    sta_tail = _read_sta_tail(work_dir, job_name)
    dat_tail = _read_job_log_tail(work_dir, job_name, lines=15)

    lines = [
        "Abaqus Analysis Result",
        "=" * 40,
        f"Status      : {status}",
        f"Completed   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Job         : {job_name}",
        f"Input       : {inp_path.name}",
        f"ODB         : {odb.name} ({_format_size(odb)})",
        f"Work dir    : {work_dir}",
        "",
    ]

    if rf3_report_paths:
        lines.append("RF3 reports (sum per node set):")
        for report in rf3_report_paths:
            lines.append(f"  - {report.name}")
        lines.append("")

    if rf3_xydata_paths:
        lines.append("XY data (sum RF3):")
        for xydata in rf3_xydata_paths:
            lines.append(f"  - {xydata.name}")
        lines.append("")

    if sta_tail:
        lines.extend(["--- .sta (cuối file) ---", sta_tail, ""])

    if dat_tail:
        lines.extend(["--- .dat/.msg (cuối file) ---", dat_tail, ""])

    write_text(result_file, "\n".join(lines).rstrip() + "\n")
    return result_file


def build_abaqus_analysis_script(
    inp_path: Path,
    *,
    work_dir: Path,
    job_name: str,
    model_name: str,
) -> str:
    """Script CAE dự phòng — import .inp, submit, chờ COMPLETED."""
    work_path = str(work_dir.resolve()).replace("\\", "/")
    inp_name = inp_path.name
    cpus = resolve_job_num_cpus()

    return f"""# -*- coding: mbcs -*-
# Generated - run: abaqus cae noGUI=abaqus_run_imperfection.py
from abaqus import *
from abaqusConstants import *
import os
import sys

os.chdir(r'{work_path}')
inp_file = r'{inp_name}'
model_name = '{model_name}'
job_name = '{job_name}'

if not os.path.isfile(inp_file):
    sys.exit('ERROR: Khong tim thay file input: ' + inp_file)

if model_name in mdb.models.keys():
    del mdb.models[model_name]
if job_name in mdb.jobs.keys():
    del mdb.jobs[job_name]

print('CHECK: Import model tu file .inp...')
mdb.ModelFromInputFile(name=model_name, inputFileName=inp_file)
{cae_configure_riks_steps_snippet()}
{cae_job_constructor_snippet(model_var="model_name", job_var="job_name")}
print('CONFIGURE job: memory=75%, cpus={cpus}, mp_mode=THREADS')

print('CHECK: writeInput consistencyChecking=ON...')
mdb.jobs[job_name].writeInput(consistencyChecking=ON)

print('SUBMIT: Gui job phan tich...')
mdb.jobs[job_name].submit(consistencyChecking=ON)
mdb.jobs[job_name].waitForCompletion()

status = mdb.jobs[job_name].status
if status != COMPLETED:
    sys.exit('ERROR: Job status = ' + str(status))
print('DONE: Job COMPLETED -> ' + job_name + '.odb')
"""


def _run_cli_datacheck(
    cmd: str,
    job_name: str,
    inp_path: Path,
    work_dir: Path,
    on_progress,
    *,
    cpus: int | None = None,
):
    _notify(on_progress, f"Bước 2: CHECK datacheck — job={job_name}")
    args = [
        f"job={job_name}",
        f"input={_inp_cli_arg(inp_path)}",
        "datacheck=continue",
        *cli_job_resource_args(cpus),
    ]
    _notify(on_progress, f"Bước 2: Lệnh: {cmd} {' '.join(args)}")
    result = run_abaqus_subprocess(cmd, args, cwd=work_dir, timeout=DATACHECK_TIMEOUT)
    _raise_if_failed(result, work_dir, job_name, "Datacheck")


def _run_cli_submit(
    cmd: str,
    job_name: str,
    inp_path: Path,
    work_dir: Path,
    on_progress,
    *,
    cpus: int | None = None,
) -> subprocess.Popen:
    _notify(on_progress, f"Bước 2: SUBMIT phân tích — job={job_name}")
    log_file = _submit_log_path(work_dir)
    args = [
        f"job={job_name}",
        f"input={_inp_cli_arg(inp_path)}",
        *cli_job_resource_args(cpus),
        "ask=off",
        "background",
    ]
    _notify(on_progress, f"Bước 2: Lệnh: {cmd} {' '.join(args)}")
    _notify(on_progress, f"Bước 2: Poll thư mục → {work_dir.resolve()}")
    _notify(on_progress, "Bước 2: Đã submit — tự kiểm tra .sta/.odb, xong sớm thì lấy ngay…")
    return start_abaqus_subprocess(cmd, args, cwd=work_dir, log_file=log_file)


def _maybe_lower_cpus_from_error(err_text: str, current_cpus: int, on_progress) -> bool:
    limit = parse_abaqus_available_cpus(err_text)
    if limit is None or limit >= current_cpus:
        return False
    set_job_cpu_override(limit)
    _notify(
        on_progress,
        f"Bước 2: Abaqus chỉ cho {limit} CPU — giảm từ {current_cpus}, thử lại…",
    )
    return True


def _run_cli_analysis_with_cpu_retries(
    cmd: str,
    job_name: str,
    inp_path: Path,
    work_dir: Path,
    on_progress,
) -> str:
    """Datacheck + submit + chờ — tự giảm cpus nếu Abaqus báo vượt giới hạn."""
    set_job_cpu_override(None)
    last_error: RuntimeError | None = None

    for attempt in range(3):
        cpus = resolve_job_num_cpus()
        try:
            _run_cli_datacheck(
                cmd, job_name, inp_path, work_dir, on_progress, cpus=cpus
            )
            analysis_proc = _run_cli_submit(
                cmd, job_name, inp_path, work_dir, on_progress, cpus=cpus
            )
            return _wait_for_completion(
                work_dir, job_name, on_progress, process=analysis_proc
            )
        except RuntimeError as exc:
            last_error = exc
            err_text = f"{exc}\n{_read_submit_log_tail(work_dir)}"
            if attempt < 2 and _maybe_lower_cpus_from_error(err_text, cpus, on_progress):
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Phân tích Abaqus thất bại sau khi giảm CPU")


def _run_cae_script(
    cmd: str,
    script_path: Path,
    work_dir: Path,
    job_name: str,
    on_progress,
) -> subprocess.Popen:
    _notify(on_progress, f"Bước 2: Chạy script CAE → {script_path.name}")
    return start_abaqus_subprocess(
        cmd,
        ["cae", f"noGUI={script_path}"],
        cwd=work_dir,
        log_file=_submit_log_path(work_dir),
    )


def _wait_for_completion(
    work_dir: Path,
    job_name: str,
    on_progress,
    process: subprocess.Popen | None = None,
):
    work_dir = work_dir.resolve()
    job_name = sanitize_job_name(job_name)
    active_job = job_name
    _notify(
        on_progress,
        f"Bước 2: Theo dõi tiến trình — poll {active_job}.sta / .odb mỗi {POLL_INTERVAL_SECONDS}s…",
    )
    deadline = time.time() + ANALYSIS_MAX_WAIT_SECONDS
    submit_grace_end = time.time() + SUBMIT_GRACE_SECONDS
    last_log = 0.0
    last_status = ""
    last_odb_size: int | None = None
    odb_stable_polls = 0
    reported_discovered = False
    warned_no_sta = False

    while time.time() < deadline:
        discovered = discover_job_name(work_dir, job_name)
        if discovered != active_job:
            active_job = discovered
            if not reported_discovered:
                _notify(on_progress, f"Bước 2: Phát hiện job Abaqus → {active_job}")
                reported_discovered = True

        sta_status = get_sta_status(work_dir, active_job)
        if sta_status == "FAILED":
            _drain_subprocess(process)
            log_tail = _read_job_log_tail(work_dir, active_job)
            raise RuntimeError(f"Job thất bại (ERROR/ABORT trong .sta).\n{log_tail}".strip())

        odb = find_odb_path(work_dir, active_job)

        ready, last_odb_size, odb_stable_polls, pending_reason = _is_build_fully_finished(
            work_dir,
            active_job,
            odb,
            last_odb_size=last_odb_size,
            odb_stable_polls=odb_stable_polls,
            process=process,
        )

        extra_reason = ""
        if ready and odb is not None:
            if _verify_build_finished(work_dir, active_job, odb):
                _drain_subprocess(process)
                _notify(
                    on_progress,
                    f"Bước 2: Build xong → {odb.name} ({_format_size(odb)})",
                )
                return active_job

            odb_stable_polls = 0
            last_odb_size = None
            extra_reason = ".odb vẫn đang ghi — chờ ổn định hoàn toàn"
        elif pending_reason:
            extra_reason = pending_reason

        now = time.time()
        status = _build_wait_status_message(
            work_dir, active_job, odb, pending_reason=extra_reason
        )
        if status and (
            status != last_status
            or (sta_status != "COMPLETED" and now - last_log >= WAIT_STATUS_LOG_SECONDS)
        ):
            _notify(on_progress, f"Bước 2: {status}")
            last_status = status
            last_log = now

        if (
            not warned_no_sta
            and now >= submit_grace_end
            and not _job_has_solver_artifacts(work_dir, active_job)
        ):
            listing = sorted(p.name for p in work_dir.iterdir() if p.is_file())[:20]
            _notify(
                on_progress,
                f"Bước 2: Sau {SUBMIT_GRACE_SECONDS}s vẫn chưa có .sta — kiểm tra {work_dir}\n"
                f"    File: {', '.join(listing) if listing else '(trống)'}",
            )
            warned_no_sta = True

        if process is not None and process.poll() is not None and now >= submit_grace_end:
            _raise_if_process_failed(process, work_dir, active_job, "Phân tích Abaqus")

        time.sleep(POLL_INTERVAL_SECONDS)

    _drain_subprocess(process)
    active_job = discover_job_name(work_dir, job_name)
    if not _analysis_completed(work_dir, active_job):
        log_tail = _read_job_log_tail(work_dir, active_job)
        artifacts = _list_job_artifacts(work_dir, active_job)
        sta = get_sta_status(work_dir, active_job)
        odb = find_odb_path(work_dir, active_job)
        extra = ""
        if sta == "COMPLETED" and odb is not None:
            extra = f"\n.sta đã COMPLETED nhưng {odb.name} ({_format_size(odb)}) vẫn đang tăng dung lượng."
        raise RuntimeError(
            f"Quá thời gian chờ tối đa ({ANALYSIS_MAX_WAIT_SECONDS // 3600}h) — chưa có .odb hoàn chỉnh.\n"
            f"File trong thư mục: {artifacts}{extra}\n\n{log_tail}".strip()
        )


def run_abaqus_analysis(
    inp_path: Path,
    *,
    work_dir: Path | None = None,
    script_output: Path | None = None,
    job_name: str | None = None,
    abaqus_cmd: str | None = None,
    on_progress=None,
) -> AbaqusRunResult:
    """
    Sau Bước 2:
    1. Kiểm tra file IMPERFECTION
    2. Datacheck + submit (hoặc script CAE dự phòng)
    3. Chờ COMPLETED
    4. Ghi file {job}_RESULT.txt
    """
    inp_path = inp_path.resolve()
    validation_errors = validate_imperfection_inp(inp_path)
    if validation_errors:
        raise ValueError("File IMPERFECTION không hợp lệ:\n" + "\n".join(validation_errors))

    inp_work_dir = inp_path.parent.resolve()
    if work_dir is not None and Path(work_dir).resolve() != inp_work_dir:
        _notify(
            on_progress,
            f"Bước 2: Poll .sta/.odb tại thư mục chứa .inp → {inp_work_dir}",
        )
    work_dir = inp_work_dir
    job_name = sanitize_job_name(job_name or derive_job_name(inp_path))
    model_name = derive_model_name(inp_path, job_name)
    cmd = resolve_abaqus_command(abaqus_cmd)
    script_path: Path | None = None

    _notify(on_progress, f"Bước 2: Abaqus → {cmd}")
    _notify(on_progress, f"Bước 2: File → {inp_path.name}  |  Job → {job_name}")
    cpus = resolve_job_num_cpus()
    _notify(
        on_progress,
        f"Bước 2: Job settings — memory 75%, {cpus} CPU(s), Threads, bỏ max load proportional factor",
    )

    if patch_inp_riks_no_max_lpf(inp_path):
        _notify(on_progress, "Bước 2: Đã chỉnh .inp — *Static, riks không giới hạn maxLPF")

    analysis_proc: subprocess.Popen | None = None
    try:
        job_name = _run_cli_analysis_with_cpu_retries(
            cmd, job_name, inp_path, work_dir, on_progress
        )
    except RuntimeError as cli_error:
        _notify(on_progress, f"Bước 2: CLI lỗi, thử script CAE — {cli_error}")
        script_path = (script_output or work_dir / "abaqus_run_imperfection.py").resolve()
        script_content = build_abaqus_analysis_script(
            inp_path,
            work_dir=work_dir,
            job_name=job_name,
            model_name=model_name,
        )
        write_abaqus_script(script_path, script_content)
        _notify(on_progress, f"Bước 2: Đã ghi script → {script_path.name}")
        analysis_proc = _run_cae_script(cmd, script_path, work_dir, job_name, on_progress)
        job_name = _wait_for_completion(work_dir, job_name, on_progress, process=analysis_proc)

    odb = find_odb_path(work_dir, job_name)
    if odb is None or not _verify_build_finished(work_dir, job_name, odb):
        artifacts = _list_job_artifacts(work_dir, job_name)
        raise RuntimeError(
            f"Build chưa hoàn tất — không thể xác nhận file .odb (job={job_name}).\n"
            f"File trong thư mục: {artifacts}"
        )

    odb_tl = publish_odb_output(odb, job_name)
    _notify(on_progress, f"Bước 2: Đã xuất {odb_tl.name}")

    postprocess: OdbPostprocessResult | None = None
    rf3_report_paths: list[Path] = []
    rf3_xydata_paths: list[Path] = []
    try:
        postprocess = run_odb_rf3_postprocess(
            odb_tl,
            work_dir=work_dir,
            job_name=job_name,
            abaqus_cmd=abaqus_cmd,
            on_progress=on_progress,
        )
        rf3_report_paths = postprocess.report_paths
        rf3_xydata_paths = postprocess.xydata_output_paths
    except Exception as exc:
        _notify(on_progress, f"Bước 3: Post-process RF3 thất bại — {exc}")

    result_file = build_result_summary(
        work_dir,
        job_name,
        inp_path,
        status="COMPLETED",
        odb_path=odb_tl,
        rf3_report_paths=rf3_report_paths,
        rf3_xydata_paths=rf3_xydata_paths,
    )
    _notify(on_progress, f"Bước 2: Đã ghi file kết quả → {result_file.name}")

    return AbaqusRunResult(
        job_name=job_name,
        odb_path=odb_tl,
        result_file=result_file,
        script_path=script_path,
        postprocess=postprocess,
        rf3_report_paths=rf3_report_paths,
        rf3_xydata_paths=rf3_xydata_paths,
    )


__all__ = [
    "AbaqusRunResult",
    "deliverable_odb_path",
    "publish_odb_output",
    "find_imperfection_inp",
    "get_completion_status",
    "get_sta_status",
    "run_abaqus_analysis",
    "validate_imperfection_inp",
]
