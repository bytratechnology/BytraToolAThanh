import math
import os
import re
import shutil

import openpyxl

from matlab_writer import write_matlab_file
from paths import DEFAULT_PATHS, ProjectPaths

SHEET_SECTION_A = "SectionA"
START_ROW = 3
TOL = 1e-3


def parse_nodes_from_inp(inp_path, instance_name="C10012"):
    """Đọc block *Node của instance C10012 trong file Abaqus .inp."""
    nodes = []
    in_target_instance = False
    inside_node = False

    instance_pattern = re.compile(
        rf"^\*Instance,\s*name={re.escape(instance_name)}\b", re.IGNORECASE
    )

    with open(inp_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()

            if instance_pattern.match(line):
                in_target_instance = True
                inside_node = False
                continue

            if in_target_instance and line.startswith("*End Instance"):
                break

            if in_target_instance and line.startswith("*Node"):
                inside_node = True
                continue

            if inside_node and line.startswith("*"):
                break

            if inside_node and line:
                parts = [x.strip() for x in line.split(",")]
                if len(parts) < 4:
                    continue

                try:
                    node_id = int(parts[0])
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                    nodes.append((node_id, x, y, z))
                except ValueError:
                    continue

    return nodes


def write_nodes_to_section_a(nodes, excel_template, excel_output, start_row=3):
    """
    Copy file Excel gốc sang thư mục đích, dán tọa độ node vào SectionA (H=x, I=y, J=z).
    File mẫu gốc không bị thay đổi.
    """
    out_dir = os.path.dirname(excel_output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    shutil.copy2(excel_template, excel_output)

    wb = openpyxl.load_workbook(excel_output)
    ws = wb[SHEET_SECTION_A]

    for i, (_, x, y, z) in enumerate(nodes):
        row = start_row + i
        ws[f"H{row}"] = x
        ws[f"I{row}"] = y
        ws[f"J{row}"] = z

    wb.save(excel_output)


def _format_number(value):
    if value == int(value):
        return str(int(value))
    return str(value)


def write_matrix_txt(nodes, matrix_output):
    """Ghi tọa độ node (x, y, z) vào Matrix.txt, mỗi dòng cách nhau bằng tab."""
    out_dir = os.path.dirname(matrix_output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(matrix_output, "w", encoding="utf-8") as f:
        for _, x, y, z in nodes:
            f.write(f"{_format_number(x)}\t{_format_number(y)}\t{_format_number(z)}\n")


def _dist(point):
    return math.hypot(point[0], point[1])


def find_lip_midpoint_between(point_a, point_b, nodes):
    """Điểm giữa trên môi (X23/Y23, X78/Y78): cùng x, nằm giữa 2 điểm, gần trục hoành nhất."""
    x_lip = point_a[0]
    y_low = min(point_a[1], point_b[1])
    y_high = max(point_a[1], point_b[1])

    xy_points = list({(x, y) for _, x, y, _ in nodes})
    on_lip = [
        p
        for p in xy_points
        if abs(p[0] - x_lip) < TOL and y_low < p[1] < y_high
    ]
    if not on_lip:
        raise ValueError(f"Không tìm thấy điểm giữa trên môi x={x_lip}")

    return min(on_lip, key=lambda p: abs(p[1]))


def select_11_points(nodes):
    """
    Chọn 11 tọa độ (x, y) theo thứ tự MATLAB:
    9 điểm đo + 2 điểm giữa môi (23 giữa 2-3, 78 giữa 7-8).
    """
    xy_points = list({(x, y) for _, x, y, _ in nodes})

    max_y = max(p[1] for p in xy_points)
    min_y = min(p[1] for p in xy_points)
    max_x = max(p[0] for p in xy_points)
    min_x = min(p[0] for p in xy_points)

    q1 = [p for p in xy_points if p[0] > 0 and p[1] > 0]
    q2 = [p for p in xy_points if p[0] < 0 and p[1] > 0]
    q3 = [p for p in xy_points if p[0] < 0 and p[1] < 0]
    q4 = [p for p in xy_points if p[0] > 0 and p[1] < 0]

    on_max_y = lambda p: abs(p[1] - max_y) < TOL
    on_min_y = lambda p: abs(p[1] - min_y) < TOL
    on_max_x = lambda p: abs(p[0] - max_x) < TOL
    on_min_x = lambda p: abs(p[0] - min_x) < TOL

    q1_flange = max([p for p in q1 if on_max_y(p)], key=lambda p: p[0])
    q1_lip = max([p for p in q1 if on_max_x(p)], key=lambda p: p[1])

    q2_flange = max([p for p in q2 if on_max_y(p)], key=lambda p: -p[0])
    q2_lip = max([p for p in q2 if on_min_x(p)], key=lambda p: p[1])

    neg_x_axis = max([p for p in q3 if on_min_x(p)], key=lambda p: -p[1])

    q3_on_web = sorted(
        [p for p in q3 if on_min_y(p)],
        key=lambda p: p[0],
    )
    near_y_axis = min(xy_points, key=lambda p: (abs(p[0]), -_dist(p)))
    q3_on_web = [p for p in q3_on_web if p != near_y_axis]
    q3_web = q3_on_web[1] if len(q3_on_web) > 1 else q3_on_web[0]

    q4_on_web = sorted([p for p in q4 if on_min_y(p)], key=lambda p: p[0], reverse=True)
    q4_web = q4_on_web[1] if len(q4_on_web) > 1 else q4_on_web[0]
    pos_x_axis = max([p for p in q4 if on_max_x(p)], key=lambda p: -p[1])

    mid_23 = find_lip_midpoint_between(q2_lip, neg_x_axis, nodes)
    mid_78 = find_lip_midpoint_between(pos_x_axis, q1_lip, nodes)

    return [
        ("Điểm 1 (X1,Y1) - Q2 vành", q2_flange),
        ("Điểm 2 (X2,Y2) - Q2 môi", q2_lip),
        ("Điểm 23 (X23,Y23) - giữa điểm 2 và 3", mid_23),
        ("Điểm 3 (X3,Y3) - trục hoành âm", neg_x_axis),
        ("Điểm 4 (X4,Y4) - Q3 web", q3_web),
        ("Điểm 5 (X5,Y5) - trục tung", near_y_axis),
        ("Điểm 6 (X6,Y6) - Q4 web", q4_web),
        ("Điểm 7 (X7,Y7) - trục hoành dương", pos_x_axis),
        ("Điểm 78 (X78,Y78) - giữa điểm 7 và 8", mid_78),
        ("Điểm 8 (X8,Y8) - Q1 môi", q1_lip),
        ("Điểm 9 (X9,Y9) - Q1 vành", q1_flange),
    ]


def write_selected_points(selected_points, output_path):
    """Ghi 11 điểm đo ra file text."""
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# 11 tọa độ đo (X, Y) chọn từ Matrix\n")
        f.write("# STT\tMô tả\tX\tY\n")
        for i, (label, (x, y)) in enumerate(selected_points, start=1):
            f.write(f"{i}\t{label}\t{_format_number(x)}\t{_format_number(y)}\n")


def _notify(on_progress, message: str):
    print(message, flush=True)
    if on_progress:
        on_progress(message)


def run_processing(paths: ProjectPaths | None = None, on_progress=None):
    """Bước 1: đọc .inp, ghi Excel/Matrix, chọn 11 tọa độ, tạo file MATLAB."""
    paths = (paths or DEFAULT_PATHS).resolve()

    _notify(on_progress, "Bước 1: Kiểm tra file nguồn...")
    paths.validate_sources()
    paths.ensure_output_dir()

    _notify(
        on_progress,
        f"Bước 1: Đang đọc node từ {paths.inp_source.name} "
        f"(instance {paths.instance_name})...",
    )
    nodes = parse_nodes_from_inp(paths.inp_source, paths.instance_name)

    if not nodes:
        raise ValueError(
            f"Không tìm thấy dữ liệu *Node trong {paths.inp_source} "
            f"(instance {paths.instance_name})"
        )

    _notify(on_progress, f"Bước 1: Đã đọc {len(nodes)} node. Đang ghi Excel...")
    write_nodes_to_section_a(
        nodes,
        paths.excel_template,
        str(paths.excel_output),
        START_ROW,
    )
    _notify(on_progress, f"Bước 1: Đã ghi Excel → {paths.excel_output.name}")

    _notify(on_progress, "Bước 1: Đang ghi Matrix.txt...")
    write_matrix_txt(nodes, str(paths.matrix_output))
    _notify(on_progress, f"Bước 1: Đã ghi Matrix → {paths.matrix_output.name}")

    _notify(on_progress, "Bước 1: Đang chọn 11 tọa độ đo...")
    selected_points = select_11_points(nodes)
    write_selected_points(selected_points, str(paths.selected_points_output))
    _notify(on_progress, f"Bước 1: Đã ghi 11 tọa độ → {paths.selected_points_output.name}")

    _notify(on_progress, "Bước 1: Đang tạo file MATLAB...")
    write_matlab_file(
        selected_points,
        matlab_template=str(paths.matlab_template),
        matlab_output=str(paths.matlab_output),
        node_count=len(nodes),
    )
    _notify(on_progress, f"Bước 1: Đã ghi MATLAB → {paths.matlab_output.name}")
    _notify(on_progress, f"Bước 1: Hoàn tất. Thư mục kết quả: {paths.output_dir}")

    return len(nodes)


def run_pipeline():
    """Mở GUI; xử lý chỉ chạy khi người dùng bấm nút."""
    from gui import launch_gui

    print("Mở giao diện...")
    launch_gui()


if __name__ == "__main__":
    run_pipeline()
