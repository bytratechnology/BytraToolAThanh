"""Chạy hàng loạt nhiều mô hình .inp — chiều dài L lấy từ tên file (L6000mm)."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from inputs import ProcessInputs, compute_outputs, count_matrix_rows
from main import run_processing
from matlab_runner import run_matlab_script
from matlab_writer import update_matlab_parameters
from paths import ProjectPaths

LENGTH_MM_PATTERN = re.compile(r"L(\d+)mm", re.IGNORECASE)
LENGTH_M_PATTERN = re.compile(r"L(\d+)p(\d+)m", re.IGNORECASE)


@dataclass
class BatchModelResult:
    inp_path: Path
    length_l: float
    output_dir: Path
    success: bool
    detail: str = ""
    error: str | None = None
    max_rf3_bc1: float | None = None
    run_time_seconds: float | None = None


IMPERFECTION_MARKERS = ("IMPERFECTION", "IMPFECTION")


def parse_length_mm_from_name(name: str) -> float | None:
    """L6000mm → 6000; L1p5m → 1500 (1.5 m)."""
    stem = Path(name).stem
    match = LENGTH_MM_PATTERN.search(stem)
    if match:
        return float(match.group(1))
    match = LENGTH_M_PATTERN.search(stem)
    if match:
        meters = float(f"{match.group(1)}.{match.group(2)}")
        return meters * 1000.0
    return None


def is_source_inp(path: Path) -> bool:
    upper = path.stem.upper()
    return path.suffix.lower() == ".inp" and not any(m in upper for m in IMPERFECTION_MARKERS)


def discover_inp_models(directory: Path) -> list[Path]:
    """Liệt kê file .inp nguồn trong thư mục (bỏ *_IMPERFECTION)."""
    directory = directory.resolve()
    if not directory.is_dir():
        return []
    files = [p for p in directory.glob("*.inp") if is_source_inp(p)]
    return sorted(files, key=lambda p: p.name.lower())


def paths_for_model(base: ProjectPaths, inp_path: Path) -> ProjectPaths:
    """Mỗi mô hình có thư mục output riêng: output_dir/{tên_inp}/"""
    inp_path = inp_path.resolve()
    model_dir = base.output_dir / inp_path.stem
    return ProjectPaths(
        inp_source=inp_path,
        excel_template=base.excel_template,
        matlab_template=base.matlab_template,
        output_dir=model_dir,
        inp_output=None,
    ).resolve()


def run_single_model_pipeline(
    base_paths: ProjectPaths,
    inp_path: Path,
    inputs: ProcessInputs,
    *,
    run_abaqus: bool,
    abaqus_cmd: str | None,
    job_name: str | None,
    abaqus_cpus: int | None = None,
    include_step1: bool = True,
    length_l_override: float | None = None,
    n_override: float | None = None,
    on_progress=None,
) -> BatchModelResult:
    """Bước 1 + 2 (+ Abaqus) hoặc chỉ Bước 2 nếu include_step1=False."""
    from abaqus_runner import run_abaqus_analysis

    def log(msg: str):
        if on_progress:
            on_progress(msg)

    if length_l_override is not None:
        length_l = length_l_override
    else:
        length_l = parse_length_mm_from_name(inp_path.name)
    if length_l is None:
        return BatchModelResult(
            inp_path=inp_path,
            length_l=0.0,
            output_dir=base_paths.output_dir,
            success=False,
            error=f"Không có Length L — nhập vào ô L hoặc đặt Lxxxxmm/L1p5m trong tên file: {inp_path.name}",
        )

    model_inputs = replace(inputs, length_l=length_l)
    paths = paths_for_model(base_paths, inp_path)

    try:
        log(f"Bước 2: {inp_path.name} — Length L = {length_l:g} mm")
        log(f"Bước 2: Thư mục kết quả → {paths.output_dir}")

        if include_step1:
            log("Bước 1: Xử lý .inp (Excel, Matrix, MATLAB)…")
            node_count = run_processing(paths, on_progress=on_progress)
        elif n_override is not None:
            if not paths.matlab_output.is_file():
                raise FileNotFoundError(
                    f"Chưa có file MATLAB — chạy Bước 1 trước.\n({paths.matlab_output})"
                )
            node_count = float(n_override)
            log(f"Bước 2: Dùng n từ form — n = {int(node_count)} node")
        else:
            if not paths.matlab_output.is_file():
                raise FileNotFoundError(
                    f"Chưa có file MATLAB — chạy Bước 1 trước.\n({paths.matlab_output})"
                )
            node_count = count_matrix_rows(paths.matrix_output)
            if node_count <= 0:
                raise ValueError(
                    f"Chưa có Matrix.txt — chạy Bước 1 trước.\n({paths.matrix_output})"
                )
            log(f"Bước 2: Dùng kết quả Bước 1 — n = {int(node_count)} node")

        model_inputs = replace(inputs, length_l=length_l, n=float(node_count))
        if include_step1:
            log(f"Bước 1: n = {node_count} node")

        outputs = compute_outputs(model_inputs)
        log("Bước 2: Ghi tham số MATLAB…")
        update_matlab_parameters(model_inputs, outputs, str(paths.matlab_output))

        detail = run_matlab_script(paths=paths, on_progress=on_progress)
        inp_result = paths.inp_result

        abaqus_result = None
        if run_abaqus and inp_result.is_file():
            log("Bước 2: Chạy Abaqus…")
            abaqus_result = run_abaqus_analysis(
                inp_result,
                work_dir=paths.output_dir,
                script_output=paths.abaqus_script_output,
                job_name=job_name or None,
                abaqus_cmd=abaqus_cmd,
                num_cpus=abaqus_cpus,
                on_progress=on_progress,
            )
            detail = f"{detail}\n{abaqus_result.summary()}"

        return BatchModelResult(
            inp_path=inp_path,
            length_l=length_l,
            output_dir=paths.output_dir,
            success=True,
            detail=detail,
            max_rf3_bc1=abaqus_result.max_rf3_bc1 if abaqus_result else None,
            run_time_seconds=abaqus_result.elapsed_seconds if abaqus_result else None,
        )
    except Exception as exc:
        return BatchModelResult(
            inp_path=inp_path,
            length_l=length_l,
            output_dir=paths.output_dir,
            success=False,
            error=str(exc),
        )


def run_batch_models(
    base_paths: ProjectPaths,
    inp_files: list[Path],
    inputs: ProcessInputs,
    *,
    run_abaqus: bool,
    abaqus_cmd: str | None,
    job_name: str | None,
    abaqus_cpus: int | None = None,
    include_step1: bool = True,
    per_model_overrides: dict[str, tuple[float, float]] | None = None,
    on_progress=None,
) -> list[BatchModelResult]:
    results: list[BatchModelResult] = []
    total = len(inp_files)
    for index, inp_path in enumerate(inp_files, start=1):
        if on_progress:
            on_progress(f"════ Mô hình {index}/{total}: {inp_path.name} ════")
        overrides = (per_model_overrides or {}).get(str(inp_path.resolve()))
        length_override = overrides[0] if overrides else None
        n_override = overrides[1] if overrides else None
        results.append(
            run_single_model_pipeline(
                base_paths,
                inp_path,
                inputs,
                run_abaqus=run_abaqus,
                abaqus_cmd=abaqus_cmd,
                job_name=job_name,
                abaqus_cpus=abaqus_cpus,
                include_step1=include_step1,
                length_l_override=length_override,
                n_override=n_override,
                on_progress=on_progress,
            )
        )
    return results


__all__ = [
    "BatchModelResult",
    "discover_inp_models",
    "is_source_inp",
    "parse_length_mm_from_name",
    "paths_for_model",
    "run_batch_models",
    "run_single_model_pipeline",
]
