"""Cấu hình Job Abaqus — memory, CPU, threads, Riks maxLPF."""

from __future__ import annotations

import re
from pathlib import Path

# Edit Job (CAE) / CLI
JOB_NUM_CPUS = 6
JOB_MEMORY_PERCENT = 75
JOB_MP_MODE = "threads"  # Multiprocessing mode: Threads
JOB_NUM_DOMAINS = 1  # dùng với THREADS (không phải MPI)


def cli_job_resource_args() -> list[str]:
    """Tham số CLI: cpus, memory, mp_mode."""
    return [
        f"cpus={JOB_NUM_CPUS}",
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
    """Khối mdb.Job(...) — memory 75%, 6 CPU, THREADS."""
    desc = description.replace("'", "\\'")
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
    numCpus={JOB_NUM_CPUS},
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
    "JOB_NUM_DOMAINS",
    "cae_configure_riks_steps_snippet",
    "cae_job_constructor_snippet",
    "cli_job_resource_args",
    "patch_inp_riks_no_max_lpf",
]
