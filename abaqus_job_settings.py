"""Cấu hình Job Abaqus — memory, CPU, threads, Riks maxLPF."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Edit Job (CAE) / CLI — ưu tiên tối đa; thực tế = min(máy/Abaqus, JOB_NUM_CPUS)
JOB_NUM_CPUS = 6
JOB_MEMORY_PERCENT = 75
JOB_MP_MODE = "threads"  # Multiprocessing mode: Threads
JOB_NUM_DOMAINS = 1  # dùng với THREADS (không phải MPI)

ABAQUS_CPU_LIMIT_RE = re.compile(
    r"number of cpus \(\d+\) exceeds the number of cpus available \((\d+)\)",
    re.IGNORECASE,
)

_cpu_override: int | None = None


def parse_abaqus_available_cpus(text: str) -> int | None:
    """Đọc số CPU Abaqus cho phép từ log lỗi."""
    match = ABAQUS_CPU_LIMIT_RE.search(text)
    if not match:
        return None
    return max(1, int(match.group(1)))


def set_job_cpu_override(count: int | None) -> None:
    """Ghi đè số CPU sau khi Abaqus báo giới hạn (license / máy)."""
    global _cpu_override
    if count is None:
        _cpu_override = None
        return
    _cpu_override = max(1, int(count))


def _windows_physical_cpu_count() -> int | None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for ps_cmd in (
        "(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum",
        "(Get-WmiObject Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum",
    ):
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                stderr=subprocess.DEVNULL,
                timeout=12,
                creationflags=flags,
            ).decode("utf-8", errors="ignore").strip()
            value = int(out)
            if value > 0:
                return value
        except (OSError, subprocess.SubprocessError, ValueError):
            continue

    try:
        out = subprocess.check_output(
            ["wmic", "cpu", "get", "NumberOfCores"],
            stderr=subprocess.DEVNULL,
            timeout=8,
            creationflags=flags,
        ).decode("utf-8", errors="ignore")
        cores = [int(token) for token in out.split() if token.isdigit()]
        if cores:
            return sum(cores)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def _unix_physical_cpu_count() -> int | None:
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.physicalcpu"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip()
            value = int(out)
            if value > 0:
                return value
        except (OSError, subprocess.SubprocessError, ValueError):
            return None

    try:
        cores: set[tuple[str, str]] = set()
        with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as handle:
            physical_id = ""
            core_id = ""
            for line in handle:
                if line.lower().startswith("physical id"):
                    physical_id = line.split(":", 1)[1].strip()
                elif line.lower().startswith("core id"):
                    core_id = line.split(":", 1)[1].strip()
                elif line.strip() == "" and physical_id and core_id:
                    cores.add((physical_id, core_id))
                    physical_id = ""
                    core_id = ""
        if cores:
            return len(cores)
    except OSError:
        pass
    return None


def _detect_physical_cpu_count() -> int | None:
    if sys.platform == "win32":
        return _windows_physical_cpu_count()
    if sys.platform in ("darwin", "linux"):
        return _unix_physical_cpu_count()
    return None


def resolve_job_num_cpus() -> int:
    """Số CPU gửi Abaqus — ưu tiên lõi vật lý (Abaqus không dùng hyper-threading)."""
    env_cpus = os.environ.get("BYTRA_ABAQUS_CPUS", "").strip()
    if env_cpus.isdigit():
        return max(1, min(JOB_NUM_CPUS, int(env_cpus)))

    if _cpu_override is not None:
        return max(1, min(JOB_NUM_CPUS, _cpu_override))

    try:
        logical = os.cpu_count() or 1
    except (TypeError, OSError):
        logical = 1

    physical = _detect_physical_cpu_count()
    if physical:
        available = physical
    elif sys.platform == "win32" and logical > 1:
        # Máy Windows không đọc được lõi vật lý — ước lượng an toàn (HT thường x2)
        available = max(1, logical // 2)
    else:
        available = logical

    return max(1, min(JOB_NUM_CPUS, available))


def cli_job_resource_args(cpus: int | None = None) -> list[str]:
    """Tham số CLI: cpus, memory, mp_mode."""
    count = max(1, int(cpus)) if cpus is not None else resolve_job_num_cpus()
    return [
        f"cpus={count}",
        f"memory={JOB_MEMORY_PERCENT}%",
        f"mp_mode={JOB_MP_MODE}",
    ]


def cae_configure_riks_steps_snippet(model_var: str = "model_name") -> str:
    """Python CAE — bỏ tick Maximum load proportional factor (maxLPF=None)."""
    return f"""
# Bỏ Maximum load proportional factor trên step Riks
for _step_name, _step in mdb.models[{model_var}].steps.items():
    if _step_name == 'Initial':
        continue
    try:
        _step.setValues(maxLPF=None)
        print('CONFIGURE step %s: maxLPF=None (bo Maximum load proportional factor)' % _step_name)
    except Exception:
        pass
"""


def cae_job_constructor_snippet(
    *,
    model_var: str,
    job_var: str,
    description: str = "IMPERFECTION auto submit",
) -> str:
    """Khối mdb.Job(...) — memory 75%, CPU theo máy, THREADS."""
    desc = description.replace("'", "\\'")
    cpus = resolve_job_num_cpus()
    return f"""mdb.Job(
    atTime=None,
    contactPrint=OFF,
    description='{desc}',
    echoPrint=OFF,
    explicitPrecision=SINGLE,
    getMemoryFromAnalysis=True,
    historyPrint=OFF,
    memory={JOB_MEMORY_PERCENT},
    memoryUnits=PERCENTAGE,
    model={model_var},
    modelPrint=OFF,
    multiprocessingMode=THREADS,
    name={job_var},
    nodalOutputPrecision=SINGLE,
    numCpus={cpus},
    numDomains={JOB_NUM_DOMAINS},
    numGPUs=0,
    numThreadsPerMpiProcess=1,
    queue=None,
    resultsFormat=ODB,
    scratch='',
    type=ANALYSIS,
    userSubroutine='',
    waitHours=0,
    waitMinutes=0,
)"""


def patch_inp_riks_no_max_lpf(inp_path: Path) -> bool:
    """
    Bỏ Maximum load proportional factor trong .inp — field maxLPF (cột 5)
    trên dòng sau *Static, riks để trống.
    """
    inp_path = inp_path.resolve()
    text = inp_path.read_text(encoding="utf-8", errors="ignore")
    changed = False

    def _replacer(match: re.Match[str]) -> str:
        nonlocal changed
        header = match.group(1)
        data_line = match.group(2)
        parts = [part.strip() for part in data_line.split(",")]
        while len(parts) < 5:
            parts.append("")
        if parts[4]:
            parts[4] = ""
            changed = True
        trailing_comma = data_line.rstrip().endswith(",")
        new_data = ", ".join(parts)
        if trailing_comma and not new_data.rstrip().endswith(","):
            new_data += ","
        return header + new_data

    pattern = re.compile(r"(\*Static,\s*riks\s*\r?\n)([^\r\n]+)", re.IGNORECASE)
    new_text = pattern.sub(_replacer, text)
    if changed:
        inp_path.write_text(new_text, encoding="utf-8")
    return changed


__all__ = [
    "JOB_MEMORY_PERCENT",
    "JOB_MP_MODE",
    "JOB_NUM_CPUS",
    "resolve_job_num_cpus",
    "parse_abaqus_available_cpus",
    "set_job_cpu_override",
    "JOB_NUM_DOMAINS",
    "cae_configure_riks_steps_snippet",
    "cae_job_constructor_snippet",
    "cli_job_resource_args",
    "patch_inp_riks_no_max_lpf",
]
