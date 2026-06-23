"""Chạy phân tích Abaqus cho file *_IMPERFECTION.inp — check, submit, build kết quả."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from abaqus_config import (
    resolve_abaqus_command,
    run_abaqus_subprocess,
    start_abaqus_subprocess,
)
from file_io import write_text

IMPFECTION_SUFFIXES = ("_IMPERFECTION", "-IMPERFECTION", "_IMPFECTION", "-IMPFECTION")
CPUS = 2
MEMORY = "90%"
DATACHECK_TIMEOUT = 900
ANALYSIS_MAX_WAIT_SECONDS = 7200  # giới hạn tối đa — xong sớm thì lấy sớm
POLL_INTERVAL_SECONDS = 2
ODB_STABLE_POLLS = 5  # ~10s dung lượng .odb không đổi
FINAL_VERIFY_DELAY_SECONDS = 2  # kiểm tra lại lần cuối trước khi báo xong
ODB_OUTPUT_SUFFIX = "-TL"  # file .odb deliverable: {job}-TL.odb


@dataclass
class AbaqusRunResult:
    job_name: str
    odb_path: Path
    result_file: Path
    script_path: Path | None = None

    def summary(self) -> str:
        lines = [
            f"Phân tích Abaqus hoàn tất — build xong",
            f"→ {self.odb_path.name}",
            f"→ {self.result_file.name}",
        ]
        if self.script_path:
            lines.append(f"→ {self.script_path.name}")
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


def _read_sta_progress(work_dir: Path, job_name: str) -> str:
    tail = _read_sta_tail(work_dir, job_name, lines=2).strip()
    if not tail:
        return ""
    return tail.splitlines()[-1].strip()[:100]


def _drain_subprocess(process: subprocess.Popen | None, *, grace_seconds: float = 30):
    if process is None or process.poll() is not None:
        return
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _raise_if_process_failed(process: subprocess.Popen | None, work_dir: Path, job_name: str, step_label: str):
    """Không báo lỗi theo exit code — chỉ tin .sta FAILED / .lck / .odb ổn định."""
    return


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

    return f"""# -*- coding: mbcs -*-
# Generated — chạy: abaqus cae noGUI=abaqus_run_imperfection.py
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

mdb.Job(
    atTime=None,
    contactPrint=OFF,
    description='IMPERFECTION auto submit',
    echoPrint=OFF,
    explicitPrecision=SINGLE,
    getMemoryFromAnalysis=True,
    historyPrint=OFF,
    memory=90,
    memoryUnits=PERCENTAGE,
    model=model_name,
    modelPrint=OFF,
    multiprocessingMode=DEFAULT,
    name=job_name,
    nodalOutputPrecision=SINGLE,
    numCpus={CPUS},
    numDomains={CPUS},
    numGPUs=0,
    numThreadsPerMpiProcess=1,
    queue=None,
    resultsFormat=ODB,
    scratch='',
    type=ANALYSIS,
    userSubroutine='',
    waitHours=0,
    waitMinutes=0,
)

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


def _run_cli_datacheck(cmd: str, job_name: str, inp_path: Path, work_dir: Path, on_progress):
    _notify(on_progress, f"Bước 2: CHECK datacheck — job={job_name}, input={inp_path.name}")
    args = [
        f"job={job_name}",
        f"input={inp_path.name}",
        "datacheck=continue",
        f"cpus={CPUS}",
        f"memory={MEMORY}",
    ]
    _notify(on_progress, f"Bước 2: Lệnh: {cmd} {' '.join(args)}")
    result = run_abaqus_subprocess(cmd, args, cwd=work_dir, timeout=DATACHECK_TIMEOUT)
    _raise_if_failed(result, work_dir, job_name, "Datacheck")


def _run_cli_submit(cmd: str, job_name: str, inp_path: Path, work_dir: Path, on_progress) -> subprocess.Popen:
    _notify(on_progress, f"Bước 2: SUBMIT phân tích — job={job_name}")
    args = [
        f"job={job_name}",
        f"input={inp_path.name}",
        f"cpus={CPUS}",
        f"memory={MEMORY}",
        "ask=off",
    ]
    _notify(on_progress, f"Bước 2: Lệnh: {cmd} {' '.join(args)}")
    _notify(on_progress, "Bước 2: Đã submit — tự kiểm tra .sta/.odb, xong sớm thì lấy ngay…")
    return start_abaqus_subprocess(cmd, args, cwd=work_dir)


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
    )


def _wait_for_completion(
    work_dir: Path,
    job_name: str,
    on_progress,
    process: subprocess.Popen | None = None,
):
    _notify(on_progress, f"Bước 2: Theo dõi tiến trình — poll {job_name}.sta / .odb mỗi {POLL_INTERVAL_SECONDS}s…")
    deadline = time.time() + ANALYSIS_MAX_WAIT_SECONDS
    last_log = 0.0
    last_progress = ""
    last_odb_size: int | None = None
    odb_stable_polls = 0
    last_odb_notice = ""

    while time.time() < deadline:
        sta_status = get_sta_status(work_dir, job_name)
        if sta_status == "FAILED":
            _drain_subprocess(process)
            log_tail = _read_job_log_tail(work_dir, job_name)
            raise RuntimeError(f"Job thất bại (ERROR/ABORT trong .sta).\n{log_tail}".strip())

        odb = find_odb_path(work_dir, job_name)

        ready, last_odb_size, odb_stable_polls, pending_reason = _is_build_fully_finished(
            work_dir,
            job_name,
            odb,
            last_odb_size=last_odb_size,
            odb_stable_polls=odb_stable_polls,
            process=process,
        )

        if ready and odb is not None:
            if _verify_build_finished(work_dir, job_name, odb):
                _drain_subprocess(process)
                _notify(
                    on_progress,
                    f"Bước 2: Build xong → {odb.name} ({_format_size(odb)})",
                )
                return

            # Xác minh cuối thất bại — reset đếm ổn định, tiếp tục chờ.
            odb_stable_polls = 0
            last_odb_size = None
            notice = f"Bước 2: .odb vẫn đang ghi — chờ ổn định hoàn toàn…"
            if notice != last_odb_notice:
                _notify(on_progress, notice)
                last_odb_notice = notice
                last_log = time.time()
        elif pending_reason:
            now = time.time()
            notice = f"Bước 2: {pending_reason}…"
            if notice != last_odb_notice and now - last_log >= 8:
                _notify(on_progress, notice)
                last_odb_notice = notice
                last_log = now

        progress = _read_sta_progress(work_dir, job_name)
        now = time.time()
        if progress and progress != last_progress:
            _notify(on_progress, f"Bước 2: {progress}")
            last_progress = progress
            last_log = now
        elif get_sta_status(work_dir, job_name) != "COMPLETED" and now - last_log >= 20:
            _notify(on_progress, "Bước 2: Solver đang chạy, chờ build xong…")
            last_log = now

        if process is not None and process.poll() is not None:
            _raise_if_process_failed(process, work_dir, job_name, "Phân tích Abaqus")

        time.sleep(POLL_INTERVAL_SECONDS)

    _drain_subprocess(process)
    if not _analysis_completed(work_dir, job_name):
        log_tail = _read_job_log_tail(work_dir, job_name)
        artifacts = _list_job_artifacts(work_dir, job_name)
        sta = get_sta_status(work_dir, job_name)
        odb = find_odb_path(work_dir, job_name)
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

    work_dir = (work_dir or inp_path.parent).resolve()
    job_name = sanitize_job_name(job_name or derive_job_name(inp_path))
    model_name = derive_model_name(inp_path, job_name)
    cmd = resolve_abaqus_command(abaqus_cmd)
    script_path: Path | None = None

    _notify(on_progress, f"Bước 2: Abaqus → {cmd}")
    _notify(on_progress, f"Bước 2: File → {inp_path.name}  |  Job → {job_name}")

    analysis_proc: subprocess.Popen | None = None
    try:
        _run_cli_datacheck(cmd, job_name, inp_path, work_dir, on_progress)
        analysis_proc = _run_cli_submit(cmd, job_name, inp_path, work_dir, on_progress)
    except RuntimeError as cli_error:
        _notify(on_progress, f"Bước 2: CLI lỗi, thử script CAE — {cli_error}")
        script_path = (script_output or work_dir / "abaqus_run_imperfection.py").resolve()
        script_content = build_abaqus_analysis_script(
            inp_path,
            work_dir=work_dir,
            job_name=job_name,
            model_name=model_name,
        )
        write_text(
            script_path,
            script_content,
            encoding="mbcs" if sys.platform == "win32" else "utf-8",
        )
        _notify(on_progress, f"Bước 2: Đã ghi script → {script_path.name}")
        analysis_proc = _run_cae_script(cmd, script_path, work_dir, job_name, on_progress)

    _wait_for_completion(work_dir, job_name, on_progress, process=analysis_proc)

    odb = find_odb_path(work_dir, job_name)
    if odb is None or not _verify_build_finished(work_dir, job_name, odb):
        artifacts = _list_job_artifacts(work_dir, job_name)
        raise RuntimeError(
            f"Build chưa hoàn tất — không thể xác nhận file .odb (job={job_name}).\n"
            f"File trong thư mục: {artifacts}"
        )

    odb_tl = publish_odb_output(odb, job_name)
    _notify(on_progress, f"Bước 2: Đã xuất {odb_tl.name}")

    result_file = build_result_summary(
        work_dir,
        job_name,
        inp_path,
        status="COMPLETED",
        odb_path=odb_tl,
    )
    _notify(on_progress, f"Bước 2: Đã ghi file kết quả → {result_file.name}")

    return AbaqusRunResult(
        job_name=job_name,
        odb_path=odb_tl,
        result_file=result_file,
        script_path=script_path,
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
