"""Post-process .odb — RF3 (Unique Nodal) từ BC-1/BC-2, sum, xuất báo cáo."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from abaqus_config import build_abaqus_subprocess_args, resolve_abaqus_command
from file_io import write_text

POSTPROCESS_TIMEOUT = 600
DEFAULT_NODE_SETS = (
    ("Plate-1", "BC-1"),
    ("Plate-2", "BC-2"),
)


@dataclass
class OdbPostprocessResult:
    script_path: Path
    report_paths: list[Path]
    summary_path: Path | None = None


def rf3_sum_report_path(work_dir: Path, job_name: str, label: str) -> Path:
    safe = label.replace("-", "_")
    return work_dir.resolve() / f"{job_name}_{safe}_RF3_sum.rpt"


def rf3_summary_path(work_dir: Path, job_name: str) -> Path:
    return work_dir.resolve() / f"{job_name}_RF3_SUMMARY.txt"


def postprocess_script_path(work_dir: Path) -> Path:
    return work_dir.resolve() / "abaqus_postprocess_rf3.py"


def build_rf3_postprocess_script(
    *,
    work_dir: Path,
    odb_path: Path,
    job_name: str,
    node_sets: tuple[tuple[str, str], ...] = DEFAULT_NODE_SETS,
) -> str:
    """Sinh script viewer — tương đương Create XY Data → RF3 → Node set → sum."""
    work = str(work_dir.resolve()).replace("\\", "/")
    odb = str(odb_path.resolve()).replace("\\", "/")
    node_sets_literal = repr(list(node_sets))

    return f"""# -*- coding: mbcs -*-
# Auto — XY Data from ODB field output: RF3 (Unique Nodal) → sum
from abaqus import session
from abaqusConstants import *
import os

WORK_DIR = r'{work}'
ODB_PATH = r'{odb}'
JOB_NAME = '{job_name}'
NODE_SETS = {node_sets_literal}


def _report_path(label):
    safe = label.replace('-', '_')
    return os.path.join(WORK_DIR, JOB_NAME + '_' + safe + '_RF3_sum.rpt')


def _extract_and_sum(odb, instance_name, nset_name, label):
    keys_before = set(session.xyDataObjects.keys())
    try:
        session.xyDataListFromField(
            odb=odb,
            outputPosition=UNIQUE_NODAL,
            variable=(('RF', NODAL, (('RF3', ), )), ),
            nodeSets=((instance_name, nset_name), ),
        )
    except Exception as exc:
        print('SKIP %s %s: %s' % (instance_name, nset_name, exc))
        return None

    new_keys = sorted(set(session.xyDataObjects.keys()) - keys_before)
    if not new_keys:
        print('WARN: no XY data for %s %s' % (instance_name, nset_name))
        return None

    xy_list = tuple(session.xyDataObjects[key] for key in new_keys)
    try:
        summed = session.XYDataSum(xyData=xy_list)
    except Exception:
        summed = xy_list[0]
        for item in xy_list[1:]:
            summed = summed + item

    out_path = _report_path(label)
    session.writeXYReport(fileName=out_path, appendMode=OFF, xyData=(summed, ))
    print('OK: %s (%d nodes)' % (out_path, len(new_keys)))
    return out_path


if not os.path.isfile(ODB_PATH):
    raise IOError('ODB not found: ' + ODB_PATH)

odb = session.openOdb(name=ODB_PATH)
session.viewports['Viewport: 1'].setValues(displayedObject=odb)

written = []
for inst, nset, label in [(a, b, b) for a, b in NODE_SETS]:
    path = _extract_and_sum(odb, inst, nset, label)
    if path:
        written.append(path)

summary_path = os.path.join(WORK_DIR, JOB_NAME + '_RF3_SUMMARY.txt')
with open(summary_path, 'w') as handle:
    handle.write('RF3 post-process (Unique Nodal, sum per node set)\\n')
    handle.write('ODB: ' + ODB_PATH + '\\n')
    for path in written:
        handle.write('REPORT: ' + path + '\\n')

odb.close()
print('DONE: RF3 post-process -> ' + summary_path)
"""


def _run_viewer_script(cmd: str, script_path: Path, work_dir: Path, timeout: int) -> subprocess.CompletedProcess:
    argv = build_abaqus_subprocess_args(cmd, ["viewer", f"noGUI={script_path.name}"])
    return subprocess.run(
        argv,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_odb_rf3_postprocess(
    odb_path: Path,
    *,
    work_dir: Path | None = None,
    job_name: str,
    abaqus_cmd: str | None = None,
    node_sets: tuple[tuple[str, str], ...] = DEFAULT_NODE_SETS,
    on_progress=None,
) -> OdbPostprocessResult:
    """Chạy post-process RF3 sau khi có file .odb."""
    odb_path = odb_path.resolve()
    work_dir = (work_dir or odb_path.parent).resolve()
    if not odb_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ODB: {odb_path}")

    script_path = postprocess_script_path(work_dir)
    script_content = build_rf3_postprocess_script(
        work_dir=work_dir,
        odb_path=odb_path,
        job_name=job_name,
        node_sets=node_sets,
    )
    write_text(
        script_path,
        script_content,
        encoding="mbcs" if sys.platform == "win32" else "utf-8",
    )

    if on_progress:
        on_progress("Bước 3: Post-process ODB — RF3 Unique Nodal, node set BC → sum…")

    cmd = resolve_abaqus_command(abaqus_cmd)
    result = _run_viewer_script(cmd, script_path, work_dir, POSTPROCESS_TIMEOUT)
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    log = "\n".join(part for part in (stdout, stderr) if part)

    report_paths = [
        path
        for _inst, nset in node_sets
        if (path := rf3_sum_report_path(work_dir, job_name, nset)).is_file()
    ]
    summary = rf3_summary_path(work_dir, job_name)

    if result.returncode != 0 and not report_paths:
        raise RuntimeError(
            f"Post-process ODB thất bại (exit {result.returncode}).\n{log}".strip()
        )

    if on_progress:
        for path in report_paths:
            on_progress(f"Bước 3: Đã ghi {path.name}")
        if summary.is_file():
            on_progress(f"Bước 3: Tóm tắt → {summary.name}")

    return OdbPostprocessResult(
        script_path=script_path,
        report_paths=report_paths,
        summary_path=summary if summary.is_file() else None,
    )


__all__ = [
    "DEFAULT_NODE_SETS",
    "OdbPostprocessResult",
    "build_rf3_postprocess_script",
    "postprocess_script_path",
    "rf3_sum_report_path",
    "rf3_summary_path",
    "run_odb_rf3_postprocess",
]
