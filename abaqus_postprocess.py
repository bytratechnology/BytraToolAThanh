"""Post-process .odb — RF3: tong RF3 moi node trong Node Set (BC-1/BC-2) theo frame, xuat XY."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from abaqus_config import build_abaqus_subprocess_args, resolve_abaqus_command
from file_io import write_abaqus_script, write_text

POSTPROCESS_TIMEOUT = 600
DEFAULT_NODE_SETS = (
    ("Plate-1", "BC-1"),
    ("Plate-2", "BC-2"),
)


@dataclass
class OdbPostprocessResult:
    script_path: Path
    report_paths: list[Path]
    xydata_output_paths: list[Path] = field(default_factory=list)
    summary_path: Path | None = None


def rf3_sum_report_path(work_dir: Path, job_name: str, label: str) -> Path:
    safe = label.replace("-", "_")
    return work_dir.resolve() / f"{job_name}_{safe}_RF3_sum.rpt"


def rf3_xydata_output_path(work_dir: Path, job_name: str, label: str) -> Path:
    """File XY sau sum — {job_name}-{label}-xydata-output.txt"""
    return work_dir.resolve() / f"{job_name}-{label}-xydata-output.txt"


def rf3_summary_path(work_dir: Path, job_name: str) -> Path:
    return work_dir.resolve() / f"{job_name}_RF3_SUMMARY.txt"


def postprocess_script_path(work_dir: Path) -> Path:
    return work_dir.resolve() / "abaqus_postprocess_rf3.py"


def postprocess_log_path(work_dir: Path) -> Path:
    return work_dir.resolve() / "abaqus_postprocess.log"


def build_rf3_postprocess_script(
    *,
    work_dir: Path,
    odb_path: Path,
    job_name: str,
    node_sets: tuple[tuple[str, str], ...] = DEFAULT_NODE_SETS,
) -> str:
    """Sinh script abaqus python — doc RF3 tung node trong Node Set, cong tong moi frame, ghi XY."""
    work = str(work_dir.resolve()).replace("\\", "/")
    odb = str(odb_path.resolve()).replace("\\", "/")
    node_sets_literal = repr(list(node_sets))

    return f"""# -*- coding: mbcs -*-
# RF3: lay TOAN BO node trong Node Set, moi frame cong tong RF3 -> XY (X=time/frame, Y=Total_RF3)
from odbAccess import openOdb
from abaqusConstants import NODAL
import os
import sys

WORK_DIR = r'{work}'
ODB_PATH = r'{odb}'
JOB_NAME = '{job_name}'
NODE_SETS = {node_sets_literal}
WANTED_LABELS = ('BC-1', 'BC-2')

try:
    from abaqusConstants import UNIQUE_NODAL
    RF_POSITIONS = (UNIQUE_NODAL, NODAL)
except ImportError:
    UNIQUE_NODAL = None
    RF_POSITIONS = (NODAL,)


def _match_instance(assembly, hint):
    names = list(assembly.instances.keys())
    if hint in names:
        return hint
    hint_u = hint.upper()
    for name in names:
        if name.upper() == hint_u:
            return name
    return None


def _discover_targets(odb):
    assembly = odb.rootAssembly
    discovered = []
    seen = set()

    for inst_name, nset_name in NODE_SETS:
        inst_key = _match_instance(assembly, inst_name)
        if inst_key and nset_name in assembly.instances[inst_key].nodeSets.keys():
            discovered.append((inst_key, nset_name, nset_name))
            seen.add(nset_name)
            print('FOUND %s on %s' % (nset_name, inst_key))

    for nset_name in WANTED_LABELS:
        if nset_name in seen:
            continue
        for inst_name in sorted(assembly.instances.keys()):
            if nset_name in assembly.instances[inst_name].nodeSets.keys():
                discovered.append((inst_name, nset_name, nset_name))
                seen.add(nset_name)
                print('FOUND %s on %s' % (nset_name, inst_name))
                break
        if nset_name not in seen and nset_name in assembly.nodeSets.keys():
            discovered.append(('', nset_name, nset_name))
            seen.add(nset_name)
            print('FOUND assembly %s' % nset_name)

    if not discovered:
        print('ERROR: BC-1/BC-2 not found')
        print('Instances: ' + ', '.join(sorted(assembly.instances.keys())))
    return discovered


def _get_region(assembly, inst_name, nset_name):
    if inst_name:
        inst_key = _match_instance(assembly, inst_name)
        if inst_key and nset_name in assembly.instances[inst_key].nodeSets.keys():
            return assembly.instances[inst_key].nodeSets[nset_name]
    if nset_name in assembly.nodeSets.keys():
        return assembly.nodeSets[nset_name]
    return None


def _find_step(odb):
    best = None
    best_name = ''
    best_frames = 0
    for name, step in odb.steps.items():
        if name == 'Initial':
            continue
        nframes = len(step.frames)
        if nframes <= best_frames:
            continue
        has_rf = False
        for frame in step.frames:
            if 'RF' in frame.fieldOutputs.keys():
                has_rf = True
                break
        if has_rf and nframes > best_frames:
            best = step
            best_name = name
            best_frames = nframes
    if best is None:
        for name, step in odb.steps.items():
            if len(step.frames) > best_frames:
                best = step
                best_name = name
                best_frames = len(step.frames)
    return best_name, best


def _node_labels_in_set(region):
    # Toan bo node label trong Node Set
    return [node.label for node in region.nodes]


def _total_rf3_for_frame(rf_field, region, node_labels):
    # Total_RF3 = RF3_node1 + RF3_node2 + ... + RF3_nodeN
    # Uu tien UNIQUE_NODAL; fallback NODAL: trung binh theo node roi cong
    label_set = set(node_labels)
    for pos in RF_POSITIONS:
        try:
            subset = rf_field.getSubset(region=region, position=pos)
            node_rf3 = {{}}
            for value in subset.values:
                label = value.nodeLabel
                if label not in label_set:
                    continue
                rf3 = value.data[2]
                if pos == NODAL:
                    if label not in node_rf3:
                        node_rf3[label] = [0.0, 0]
                    node_rf3[label][0] += rf3
                    node_rf3[label][1] += 1
                else:
                    node_rf3[label] = [rf3, 1]
            if not node_rf3:
                continue
            total = sum(acc[0] / acc[1] for acc in node_rf3.values())
            return total, pos, len(node_rf3)
        except Exception:
            pass
    try:
        subset = rf_field.getSubset(region=region)
        node_rf3 = {{}}
        for value in subset.values:
            label = value.nodeLabel
            if label not in label_set:
                continue
            rf3 = value.data[2]
            if label not in node_rf3:
                node_rf3[label] = [0.0, 0]
            node_rf3[label][0] += rf3
            node_rf3[label][1] += 1
        if node_rf3:
            total = sum(acc[0] / acc[1] for acc in node_rf3.values())
            return total, 'default', len(node_rf3)
    except Exception:
        pass
    return None, None, 0


def _extract_rf3_xy(odb, inst_name, nset_name):
    assembly = odb.rootAssembly
    region = _get_region(assembly, inst_name, nset_name)
    if region is None:
        print('FAIL region %s %s' % (inst_name, nset_name))
        return None

    node_labels = _node_labels_in_set(region)
    if not node_labels:
        print('FAIL empty node set %s' % nset_name)
        return None
    print('NSET %s: %d nodes (labels %d..%d)' % (
        nset_name, len(node_labels), min(node_labels), max(node_labels)))

    step_name, step = _find_step(odb)
    if step is None:
        print('FAIL no step with frames')
        return None
    print('STEP %s: %d frames for %s' % (step_name, len(step.frames), nset_name))

    points = []
    last_pos = '?'
    for frame in step.frames:
        x_time = frame.frameValue
        if 'RF' not in frame.fieldOutputs.keys():
            continue
        total_rf3, pos, n_matched = _total_rf3_for_frame(
            frame.fieldOutputs['RF'], region, node_labels)
        if total_rf3 is None:
            continue
        last_pos = pos
        points.append((x_time, total_rf3))

    if not points:
        print('FAIL no RF3 data for %s' % nset_name)
        return None
    print('OK %s: %d XY points, %d nodes summed/frame (pos=%s)' % (
        nset_name, len(points), len(node_labels), last_pos))
    return points


def _xydata_output_path(label):
    return os.path.join(WORK_DIR, JOB_NAME + '-' + label + '-xydata-output.txt')


def _write_xydata_points(points, path):
    # X = Time hoac Arc length (frameValue); Y = Total_RF3
    yvals = [p[1] for p in points]
    with open(path, 'w') as handle:
        handle.write('X\\tY\\n')
        for x_time, total_rf3 in points:
            handle.write('%g\\t%g\\n' % (x_time, total_rf3))
    print('WROTE XYDATA %d rows (X=time/frame, Y=Total_RF3), Y=[%g .. %g] -> %s' % (
        len(points), min(yvals), max(yvals), path))


if not os.path.isfile(ODB_PATH):
    print('ERROR: ODB not found: ' + ODB_PATH)
    sys.exit(1)

odb = openOdb(path=ODB_PATH, readOnly=True)
print('OPEN ODB: ' + ODB_PATH)

targets = _discover_targets(odb)
if not targets:
    odb.close()
    sys.exit(1)

xydata_written = []
for inst, nset, label in targets:
    points = _extract_rf3_xy(odb, inst, nset)
    if not points:
        continue
    out_path = _xydata_output_path(label)
    _write_xydata_points(points, out_path)
    xydata_written.append(out_path)

missing = [label for label in WANTED_LABELS if not os.path.isfile(_xydata_output_path(label))]
if missing:
    print('ERROR: missing xydata for ' + ', '.join(missing))
    odb.close()
    sys.exit(1)

summary_path = os.path.join(WORK_DIR, JOB_NAME + '_RF3_SUMMARY.txt')
with open(summary_path, 'w') as handle:
    handle.write('RF3: sum RF3 of all nodes in Node Set per frame -> XYDATA\\n')
    handle.write('X = frame time / arc length; Y = Total_RF3\\n')
    handle.write('ODB: ' + ODB_PATH + '\\n')
    for path in xydata_written:
        handle.write('XYDATA: ' + path + '\\n')

odb.close()
print('DONE: RF3 post-process -> ' + summary_path)
"""


def _validate_xydata_file(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 4:
        return False
    try:
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip()
        ]
    except OSError:
        return False
    if len(lines) < 2:
        return False
    return any(not line.lower().startswith("x") for line in lines[1:])


def _run_postprocess_script(cmd: str, script_path: Path, work_dir: Path, timeout: int) -> tuple[subprocess.CompletedProcess, str]:
    argv = build_abaqus_subprocess_args(cmd, ["python", script_path.name])
    result = subprocess.run(
        argv,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    log = "\n".join(part for part in (stdout, stderr) if part)
    log_path = postprocess_log_path(work_dir)
    try:
        log_path.write_text(log + ("\n" if log else ""), encoding="utf-8")
    except OSError:
        pass
    return result, log


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
    write_abaqus_script(script_path, script_content)

    if on_progress:
        on_progress("Bước 3: Post-process ODB — Total_RF3 (sum all nodes BC-1/BC-2)…")

    cmd = resolve_abaqus_command(abaqus_cmd)
    result, log = _run_postprocess_script(cmd, script_path, work_dir, POSTPROCESS_TIMEOUT)

    report_paths = [
        path
        for _inst, nset in node_sets
        if (path := rf3_sum_report_path(work_dir, job_name, nset)).is_file()
    ]
    xydata_output_paths = [
        path
        for _inst, nset in node_sets
        if (path := rf3_xydata_output_path(work_dir, job_name, nset)).is_file()
    ]
    summary = rf3_summary_path(work_dir, job_name)

    expected_xy = [rf3_xydata_output_path(work_dir, job_name, nset) for _inst, nset in node_sets]
    missing_xy = [path.name for path in expected_xy if not path.is_file()]
    invalid_xy = [
        path.name
        for path in expected_xy
        if path.is_file() and not _validate_xydata_file(path)
    ]

    if missing_xy or invalid_xy:
        log_path = postprocess_log_path(work_dir)
        detail_parts = []
        if missing_xy:
            detail_parts.append("Thieu: " + ", ".join(missing_xy))
        if invalid_xy:
            detail_parts.append("Rong/khong hop le: " + ", ".join(invalid_xy))
        raise RuntimeError(
            f"Post-process chua tao du xydata-output.txt (exit {result.returncode}).\n"
            f"{chr(10).join(detail_parts)}\n"
            f"Xem log: {log_path}\n\n{log}".strip()
        )

    if result.returncode != 0:
        log_path = postprocess_log_path(work_dir)
        if on_progress:
            on_progress(f"Bước 3: Canh bao python exit {result.returncode} — da co output, xem {log_path.name}")

    if on_progress:
        for path in report_paths:
            on_progress(f"Bước 3: Đã ghi {path.name}")
        for path in xydata_output_paths:
            on_progress(f"Bước 3: XY data → {path.name}")
        if summary.is_file():
            on_progress(f"Bước 3: Tóm tắt → {summary.name}")

    return OdbPostprocessResult(
        script_path=script_path,
        report_paths=report_paths,
        xydata_output_paths=xydata_output_paths,
        summary_path=summary if summary.is_file() else None,
    )


__all__ = [
    "DEFAULT_NODE_SETS",
    "OdbPostprocessResult",
    "build_rf3_postprocess_script",
    "postprocess_script_path",
    "rf3_sum_report_path",
    "rf3_xydata_output_path",
    "rf3_summary_path",
    "run_odb_rf3_postprocess",
]
