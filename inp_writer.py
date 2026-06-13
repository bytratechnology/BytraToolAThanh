import re
from pathlib import Path

INP_SOURCE = Path("A_THANH/LT03D_LK02D_C10012_L1p5m_E1.inp")
INP_OUTPUT = Path("PROCESS/LT03D_LK02D_C10012_L1p5m_E1.inp")
MYFILE_INPUT = Path("PROCESS/myfile.txt")
INSTANCE_NAME = "C10012"


def load_myfile_coords(myfile_path):
    """Đọc 3 cột x, y, z từ myfile.txt (cách nhau bằng space hoặc dấu phẩy)."""
    rows = []
    for line in Path(myfile_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if "," in line:
            parts = [p.strip() for p in line.split(",")]
        else:
            parts = line.split()
        if len(parts) < 3:
            continue
        rows.append((float(parts[0]), float(parts[1]), float(parts[2])))
    return rows


def _is_node_data_line(line):
    stripped = line.strip()
    if not stripped or stripped.startswith("*"):
        return False
    parts = [p.strip() for p in stripped.split(",")]
    if len(parts) < 4:
        return False
    try:
        int(parts[0])
        float(parts[1])
        float(parts[2])
        float(parts[3])
        return True
    except ValueError:
        return False


def _format_coord_field(template_field, value):
    """Giữ khoảng trắng đầu cột; ghi đủ chính xác (6 chữ số thập phân như myfile.txt)."""
    leading = template_field[: len(template_field) - len(template_field.lstrip())]
    template = template_field.strip()
    width = len(template_field)

    if template.endswith(".") and abs(value - round(value)) < 1e-9:
        text = f"{int(round(value))}."
    else:
        text = f"{value:.6f}".rstrip("0").rstrip(".")
        if "." not in text:
            text = f"{value:.6f}"

    padded = text.rjust(max(width - len(leading), len(text)))
    return leading + padded


def _build_node_line(original_line, x, y, z):
    parts = original_line.split(",")
    if len(parts) < 4:
        return original_line
    return (
        f"{parts[0]},{_format_coord_field(parts[1], x)},"
        f"{_format_coord_field(parts[2], y)},{_format_coord_field(parts[3], z)}"
    )


def write_myfile_to_inp(
    inp_source=INP_SOURCE,
    myfile_path=MYFILE_INPUT,
    inp_output=INP_OUTPUT,
    instance_name=INSTANCE_NAME,
):
    """
    Ghi 3 cột tọa độ từ myfile.txt vào block *Node của instance C10012.
    Giữ nguyên cột số thứ tự node. File gốc A_THANH không bị sửa.
    """
    inp_source = Path(inp_source)
    myfile_path = Path(myfile_path)
    inp_output = Path(inp_output)

    if not inp_source.exists():
        raise FileNotFoundError(f"Không tìm thấy file .inp: {inp_source}")
    if not myfile_path.exists():
        raise FileNotFoundError(f"Không tìm thấy {myfile_path}")

    coords = load_myfile_coords(myfile_path)
    lines = inp_source.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)

    instance_pattern = re.compile(
        rf"^\*Instance,\s*name={re.escape(instance_name)}\b", re.IGNORECASE
    )

    in_target_instance = False
    in_node_block = False
    coord_idx = 0
    updated = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        if instance_pattern.match(stripped):
            in_target_instance = True
            in_node_block = False
            continue

        if in_target_instance and stripped.startswith("*End Instance"):
            break

        if in_target_instance and stripped.startswith("*Node"):
            in_node_block = True
            continue

        if in_node_block and stripped.startswith("*"):
            in_node_block = False
            continue

        if in_node_block and _is_node_data_line(line):
            if coord_idx >= len(coords):
                raise ValueError(
                    f"Số dòng node trong .inp nhiều hơn myfile.txt "
                    f"({coord_idx + 1} > {len(coords)})"
                )
            x, y, z = coords[coord_idx]
            newline = "\n" if line.endswith("\n") else ""
            lines[i] = _build_node_line(line.rstrip("\n"), x, y, z) + newline
            coord_idx += 1
            updated += 1

    if updated == 0:
        raise ValueError(f"Không tìm thấy block *Node của instance {instance_name}")

    if coord_idx != len(coords):
        raise ValueError(
            f"Số dòng myfile.txt ({len(coords)}) không khớp số node đã cập nhật ({coord_idx})"
        )

    inp_output.parent.mkdir(parents=True, exist_ok=True)
    inp_output.write_text("".join(lines), encoding="utf-8")

    return f"Đã ghi {updated} node vào {inp_output}"
