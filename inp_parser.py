"""Đọc node từ file Abaqus .inp — block *Node đầu tiên đến *Element."""

from pathlib import Path


def _parse_node_tuple(line: str):
    parts = [x.strip() for x in line.split(",")]
    if len(parts) < 4:
        return None
    try:
        return (int(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
    except ValueError:
        return None


def parse_nodes_from_inp(inp_path) -> list[tuple]:
    """
    Đọc các dòng node từ *Node đầu tiên đến trước *Element đầu tiên.
    Không phụ thuộc instance.
    """
    nodes = []
    in_node_block = False
    found_node_keyword = False

    with open(inp_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()

            if not found_node_keyword:
                if stripped.startswith("*Node"):
                    found_node_keyword = True
                    in_node_block = True
                continue

            if in_node_block and stripped.startswith("*Element"):
                break

            if in_node_block and stripped:
                node = _parse_node_tuple(stripped)
                if node:
                    nodes.append(node)

    if not nodes:
        raise ValueError(
            f"Không tìm thấy dữ liệu *Node trong {inp_path} "
            f"(từ *Node đầu tiên đến *Element)"
        )

    return nodes
