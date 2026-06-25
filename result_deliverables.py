"""Giữ deliverable cuối (.inp, .odb, BC-1 xydata) và ghi Excel tổng hợp."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl
from openpyxl import Workbook

from abaqus_postprocess import rf3_xydata_output_path
from file_io import remove_tree, run_with_retry

SUMMARY_EXCEL_NAME = "TongHop_KetQua.xlsx"
BC1_NODE_SET = "BC-1"
ODB_OUTPUT_SUFFIX = "-TL"
EXCEL_HEADERS = ("Tên model", "Thời gian chạy", "Max RF3 (BC-1)")


@dataclass
class ModelSummaryRow:
    model_name: str
    run_time_seconds: float
    max_rf3_bc1: float

    @property
    def run_time_display(self) -> str:
        return format_duration(self.run_time_seconds)


def format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def summary_excel_path(output_root: Path) -> Path:
    return output_root.resolve() / SUMMARY_EXCEL_NAME


def deliverable_odb_path(output_dir: Path, job_name: str) -> Path:
    return output_dir.resolve() / f"{job_name}{ODB_OUTPUT_SUFFIX}.odb"


def deliverable_keep_paths(
    output_dir: Path,
    *,
    job_name: str,
    imperfection_inp: Path,
) -> set[Path]:
    output_dir = output_dir.resolve()
    return {
        imperfection_inp.resolve(),
        deliverable_odb_path(output_dir, job_name).resolve(),
        rf3_xydata_output_path(output_dir, job_name, BC1_NODE_SET).resolve(),
    }


def parse_xydata_max_rf3(path: Path) -> float:
    """Lấy giá trị Y lớn nhất trong file BC-1 xydata."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy xydata: {path}")
    y_max: float | None = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.lower().startswith("x"):
            continue
        parts = text.replace(",", ".").split()
        if len(parts) < 2:
            continue
        try:
            y_val = float(parts[1])
        except ValueError:
            continue
        if y_max is None or y_val > y_max:
            y_max = y_val
    if y_max is None:
        raise ValueError(f"Không đọc được dữ liệu Y trong {path.name}")
    return y_max


def cleanup_model_output_dir(output_dir: Path, *, keep_paths: set[Path]) -> list[str]:
    """Xóa mọi file/thư mục trong output_dir trừ các deliverable giữ lại."""
    output_dir = output_dir.resolve()
    keep = {p.resolve() for p in keep_paths}
    removed: list[str] = []

    if not output_dir.is_dir():
        return removed

    for item in sorted(output_dir.iterdir(), key=lambda p: p.name.lower()):
        resolved = item.resolve()
        if resolved in keep:
            continue
        try:
            if item.is_dir():
                remove_tree(item)
            else:
                item.unlink()
            removed.append(item.name)
        except OSError:
            pass
    return removed


def _write_workbook(path: Path, rows: list[ModelSummaryRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Ket qua"
    ws.append(list(EXCEL_HEADERS))
    for row in sorted(rows, key=lambda r: r.model_name.lower()):
        ws.append([row.model_name, row.run_time_display, row.max_rf3_bc1])
    wb.save(path)


def _load_existing_rows(path: Path) -> dict[str, ModelSummaryRow]:
    if not path.is_file():
        return {}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows: dict[str, ModelSummaryRow] = {}
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not row[0]:
                continue
            name = str(row[0]).strip()
            run_time = 0.0
            max_rf3 = 0.0
            try:
                if row[2] is not None:
                    max_rf3 = float(row[2])
            except (TypeError, ValueError):
                pass
            rows[name] = ModelSummaryRow(
                model_name=name,
                run_time_seconds=run_time,
                max_rf3_bc1=max_rf3,
            )
        return rows
    finally:
        wb.close()


def upsert_summary_row(excel_path: Path, row: ModelSummaryRow) -> Path:
    """Thêm hoặc cập nhật một dòng theo tên model."""
    excel_path = excel_path.resolve()
    existing = _load_existing_rows(excel_path)
    existing[row.model_name] = row
    run_with_retry(lambda: _write_workbook(excel_path, list(existing.values())), excel_path)
    return excel_path


def write_summary_excel(excel_path: Path, rows: list[ModelSummaryRow]) -> Path:
    """Ghi toàn bộ bảng tổng hợp (merge với file cũ theo tên model)."""
    excel_path = excel_path.resolve()
    merged = _load_existing_rows(excel_path)
    for row in rows:
        merged[row.model_name] = row
    run_with_retry(lambda: _write_workbook(excel_path, list(merged.values())), excel_path)
    return excel_path


def finalize_model_deliverables(
    output_dir: Path,
    *,
    job_name: str,
    imperfection_inp: Path,
    run_time_seconds: float,
    model_name: str | None = None,
    on_progress=None,
) -> tuple[Path, float, list[str]]:
    """
    Đọc max RF3 từ BC-1 xydata, dọn thư mục, cập nhật Excel tổng hợp.
    Trả về (bc1_xydata_path, max_rf3, removed_files).
    """
    output_dir = output_dir.resolve()
    bc1_path = rf3_xydata_output_path(output_dir, job_name, BC1_NODE_SET)
    max_rf3 = parse_xydata_max_rf3(bc1_path)

    keep = deliverable_keep_paths(
        output_dir,
        job_name=job_name,
        imperfection_inp=imperfection_inp,
    )
    removed = cleanup_model_output_dir(output_dir, keep_paths=keep)

    label = model_name or imperfection_inp.name
    excel_path = summary_excel_path(output_dir.parent)
    upsert_summary_row(
        excel_path,
        ModelSummaryRow(
            model_name=label,
            run_time_seconds=run_time_seconds,
            max_rf3_bc1=max_rf3,
        ),
    )

    if on_progress:
        on_progress(f"Bước 3: Max RF3 (BC-1) = {max_rf3:g}")
        on_progress(f"Đã dọn {len(removed)} file/thư mục — giữ .inp, .odb, BC-1 xydata")
        on_progress(f"Excel tổng hợp → {excel_path.name}")

    return bc1_path, max_rf3, removed


__all__ = [
    "BC1_NODE_SET",
    "ModelSummaryRow",
    "SUMMARY_EXCEL_NAME",
    "cleanup_model_output_dir",
    "deliverable_keep_paths",
    "finalize_model_deliverables",
    "format_duration",
    "parse_xydata_max_rf3",
    "summary_excel_path",
    "upsert_summary_row",
    "write_summary_excel",
]
