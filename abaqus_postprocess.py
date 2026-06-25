"""Post-process .odb — RF3 (Unique Nodal) từ BC-1/BC-2, sum, xuất báo cáo."""

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
    """Sinh script viewer — Create XY Data -> RF3 Unique Nodal -> sum -> xydata txt."""
    work = str(work_dir.resolve()).replace("\\", "/")
    odb = str(odb_path.resolve()).replace("\\", "/")
    node_sets_literal = repr(list(node_sets))

    return f"""# -*- coding: mbcs -*-
# Auto - RF3 Unique Nodal from BC-1/BC-2 -> sum -> xydata-output.txt
from abaqus import session
from abaqusConstants import *
import os
import sys

WORK_DIR = r'{work}'
ODB_PATH = r'{odb}'
JOB_NAME = '{job_name}'
NODE_SETS = {node_sets_literal}
WANTED_LABELS = ('BC-1', 'BC-2')


def _match_instance(assembly, hint):
    names = list(assembly.instances.keys())
    if hint in names:
        return hint
    hint_u = hint.upper()
    for name in names:
        if name.upper() == hint_u:
            return name
    return None


def _discover_node_sets(odb):
    assembly = odb.rootAssembly
    discovered = []
    seen_labels = set()

    for inst_name, nset_name in NODE_SETS:
        matched = _match_instance(assembly, inst_name)
        if matched is None:
            continue
        inst = assembly.instances[matched]
        if nset_name in inst.nodeSets.keys():
            discovered.append((matched, nset_name, nset_name))
            seen_labels.add(nset_name)
            print('FOUND configured %s on %s' % (nset_name, matched))

    for nset_name in WANTED_LABELS:
        if nset_name in seen_labels:
            continue
        for inst_name in sorted(assembly.instances.keys()):
            inst = assembly.instances[inst_name]
            if nset_name in inst.nodeSets.keys():
                discovered.append((inst_name, nset_name, nset_name))
                seen_labels.add(nset_name)
                print('FOUND %s on %s' % (nset_name, inst_name))
                break
        if nset_name not in seen_labels and nset_name in assembly.nodeSets.keys():
            discovered.append(('', nset_name, nset_name))
            seen_labels.add(nset_name)
            print('FOUND assembly-level %s' % nset_name)

    if not discovered:
        print('ERROR: BC-1/BC-2 not found')
        print('Instances: ' + ', '.join(sorted(assembly.instances.keys())))
        for inst_name in sorted(assembly.instances.keys()):
            keys = sorted(assembly.instances[inst_name].nodeSets.keys())
            if keys:
                print('  %s nodeSets: %s' % (inst_name, ', '.join(keys[:30])))
        asm_keys = sorted(assembly.nodeSets.keys())
        if asm_keys:
            print('  assembly nodeSets: ' + ', '.join(asm_keys[:30]))
    return discovered


def _report_path(label):
    safe = label.replace('-', '_')
    return os.path.join(WORK_DIR, JOB_NAME + '_' + safe + '_RF3_sum.rpt')


def _xydata_output_path(label):
    return os.path.join(WORK_DIR, JOB_NAME + '-' + label + '-xydata-output.txt')


def _write_xydata_txt(xy_data, path):
    points = []
    try:
        points = list(xy_data.data)
    except (AttributeError, TypeError):
        try:
            points = [(xy_data[i][0], xy_data[i][1]) for i in range(len(xy_data))]
        except (TypeError, IndexError):
            pass
    if not points:
        raise ValueError('XY data empty for ' + path)
    with open(path, 'w') as handle:
        handle.write('X\\tY\\n')
        for pt in points:
            handle.write('%g\\t%g\\n' % (pt[0], pt[1]))
    print('WROTE xydata %d points -> %s' % (len(points), path))


def _sum_xy_list(xy_list):
    if not xy_list:
        return None
    if len(xy_list) == 1:
        return xy_list[0]
    try:
        return session.XYDataSum(xyData=tuple(xy_list))
    except Exception:
        total = xy_list[0]
        for item in xy_list[1:]:
            total = total + item
        return total


def _pull_xy_keys(keys_before):
    return sorted(set(session.xyDataObjects.keys()) - keys_before)


def _try_field_node_sets(odb, inst_name, nset_name):
    errors = []
    for pos_name, pos in (('UNIQUE_NODAL', UNIQUE_NODAL), ('NODAL', NODAL)):
        keys_before = set(session.xyDataObjects.keys())
        try:
            session.xyDataListFromField(
                odb=odb,
                outputPosition=pos,
                variable=(('RF', NODAL, (('RF3',),)),),
                nodeSets=((inst_name, nset_name),),
            )
            new_keys = _pull_xy_keys(keys_before)
            if new_keys:
                print('OK xyDataListFromField nodeSets %s %s (%s, %d curves)' % (
                    inst_name, nset_name, pos_name, len(new_keys)))
                return new_keys, []
        except Exception as exc:
            errors.append('nodeSets/%s/%s: %s' % (pos_name, inst_name, exc))
    return None, errors


def _try_field_node_labels(odb, inst_name, nset_name):
    assembly = odb.rootAssembly
    inst_key = _match_instance(assembly, inst_name) if inst_name else None
    if not inst_key:
        return None, ['no instance']
    instance = assembly.instances[inst_key]
    if nset_name not in instance.nodeSets.keys():
        return None, ['nset missing on instance']
    labels = tuple(sorted(set(node.label for node in instance.nodeSets[nset_name].nodes)))
    if not labels:
        return None, ['empty node set']
    errors = []
    for pos_name, pos in (('UNIQUE_NODAL', UNIQUE_NODAL), ('NODAL', NODAL)):
        keys_before = set(session.xyDataObjects.keys())
        try:
            session.xyDataListFromField(
                odb=odb,
                outputPosition=pos,
                variable=(('RF', NODAL, (('RF3',),)),),
                nodeLabels=((inst_key, labels),),
            )
            new_keys = _pull_xy_keys(keys_before)
            if new_keys:
                print('OK xyDataListFromField nodeLabels %s %s (%s, %d nodes)' % (
                    inst_key, nset_name, pos_name, len(labels)))
                return new_keys, []
        except Exception as exc:
            errors.append('nodeLabels/%s: %s' % (pos_name, exc))
    return None, errors


def _try_field_assembly_nset(odb, nset_name):
    assembly = odb.rootAssembly
    if nset_name not in assembly.nodeSets.keys():
        return None, ['no assembly nset']
    errors = []
    for pos_name, pos in (('UNIQUE_NODAL', UNIQUE_NODAL), ('NODAL', NODAL)):
        keys_before = set(session.xyDataObjects.keys())
        try:
            session.xyDataListFromField(
                odb=odb,
                outputPosition=pos,
                variable=(('RF', NODAL, (('RF3',),)),),
                nodeSets=((nset_name,),),
            )
            new_keys = _pull_xy_keys(keys_before)
            if new_keys:
                print('OK xyDataListFromField assembly %s (%s)' % (nset_name, pos_name))
                return new_keys, []
        except Exception as exc:
            errors.append('assembly/%s: %s' % (pos_name, exc))
    return None, errors


def _extract_and_sum(odb, instance_name, nset_name, label):
    new_keys = None
    all_errors = []

    if instance_name:
        new_keys, err = _try_field_node_sets(odb, instance_name, nset_name)
        if err:
            all_errors.extend(err)
        if not new_keys:
            new_keys, err = _try_field_node_labels(odb, instance_name, nset_name)
            if err:
                all_errors.extend(err)

    if not new_keys:
        new_keys, err = _try_field_assembly_nset(odb, nset_name)
        if err:
            all_errors.extend(err)

    if not new_keys:
        print('FAIL %s %s: %s' % (instance_name or 'assembly', nset_name, ' | '.join(all_errors)))
        return None

    xy_list = tuple(session.xyDataObjects[key] for key in new_keys)
    summed = _sum_xy_list(xy_list)
    if summed is None:
        print('FAIL sum empty for %s' % label)
        return None

    xydata_path = _xydata_output_path(label)
    try:
        _write_xydata_txt(summed, xydata_path)
    except Exception as exc:
        print('FAIL write xydata %s: %s' % (label, exc))
        return None

    out_path = _report_path(label)
    try:
        session.writeXYReport(fileName=out_path, appendMode=OFF, xyData=(summed,))
    except Exception as exc:
        print('WARN writeXYReport %s: %s' % (label, exc))
        out_path = None

    print('OK %s (%d nodes) -> %s' % (label, len(new_keys), xydata_path))
    return out_path, xydata_path


if not os.path.isfile(ODB_PATH):
    print('ERROR: ODB not found: ' + ODB_PATH)
    sys.exit(1)

odb = session.openOdb(name=ODB_PATH)
print('OPEN ODB: ' + ODB_PATH)

targets = _discover_node_sets(odb)
if not targets:
    odb.close()
    sys.exit(1)

written = []
xydata_written = []
for inst, nset, label in targets:
    result = _extract_and_sum(odb, inst, nset, label)
    if result:
        rpt_path, xy_path = result
        if rpt_path:
            written.append(rpt_path)
        xydata_written.append(xy_path)

missing = [label for label in WANTED_LABELS if not os.path.isfile(_xydata_output_path(label))]
if missing:
    print('ERROR: missing xydata for ' + ', '.join(missing))
    odb.close()
    sys.exit(1)

summary_path = os.path.join(WORK_DIR, JOB_NAME + '_RF3_SUMMARY.txt')
with open(summary_path, 'w') as handle:
    handle.write('RF3 post-process (Unique Nodal, sum per node set)\\n')
    handle.write('ODB: ' + ODB_PATH + '\\n')
    for path in written:
        handle.write('REPORT: ' + path + '\\n')
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


def _run_viewer_script(cmd: str, script_path: Path, work_dir: Path, timeout: int) -> tuple[subprocess.CompletedProcess, str]:
    argv = build_abaqus_subprocess_args(cmd, ["viewer", f"noGUI={script_path.name}"])
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
        on_progress("Bước 3: Post-process ODB — RF3 Unique Nodal, node set BC → sum…")

    cmd = resolve_abaqus_command(abaqus_cmd)
    result, log = _run_viewer_script(cmd, script_path, work_dir, POSTPROCESS_TIMEOUT)

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
            on_progress(f"Bước 3: Canh bao viewer exit {result.returncode} — da co output, xem {log_path.name}")

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
