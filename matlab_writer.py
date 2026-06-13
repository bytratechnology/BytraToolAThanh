import os
import re

from inputs import CalculatedOutputs, ProcessInputs

MATLAB_OUTPUT = "PROCESS/LT03DLK02DC10012_1p5m_E1_G_Duong.m"
MATLAB_TEMPLATE = "A_THANH/LT03DLK02DC10012_1p5m_E1_G_Duong.m"


def _format_matlab(value):
    if value == int(value):
        return str(int(value))
    return format(value, ".10g")


def _matlab_assign(name, value):
    return f"{name}=\t{_format_matlab(value)}\t;"


def _matlab_coord_line(var_name, value, comment, tight_comment=False):
    sep = ";" if tight_comment else "; "
    return f"{var_name}={_format_matlab(value)}{sep}{comment}"


def build_coordinates_block(selected_points):
    """Tạo block %Input với 11 tọa độ (X1..X9, X23, X78)."""
    points = [point for _, point in selected_points]
    p1, p2, p23, p3, p4, p5, p6, p7, p78, p8, p9 = points

    ordinal = [
        "first",
        "second",
        "third",
        "fourth",
        "firth",
        "six",
        "seventh",
        "eight",
        "nineth",
    ]

    lines = ["%Input", ""]

    def add_point(index, x, y, tight=False):
        n = ordinal[index - 1]
        lines.append(
            _matlab_coord_line(
                f"X{index}",
                x,
                f"%the X coordinate of the {n} measuring",
                tight_comment=tight,
            )
        )
        lines.append(
            _matlab_coord_line(
                f"Y{index}",
                y,
                f"%the Y coordinate of the {n} measuring",
                tight_comment=tight,
            )
        )

    add_point(1, *p1)
    add_point(2, *p2)
    lines.append(
        _matlab_coord_line(
            "X23",
            p23[0],
            "%The X coordinate of the middle point between point 2 and 3",
        )
    )
    lines.append(
        _matlab_coord_line(
            "Y23",
            p23[1],
            "%The Y coordinate of the middle point between point 2 and 3",
        )
    )
    add_point(3, *p3)
    add_point(4, *p4)
    add_point(5, *p5)
    add_point(6, *p6)
    add_point(7, *p7)
    lines.append(
        _matlab_coord_line(
            "X78",
            p78[0],
            "%The X coordinate of the middle point between point 7 and 8",
        )
    )
    lines.append(
        _matlab_coord_line(
            "Y78",
            p78[1],
            "%The Y coordinate of the middle point between point 7 and 8",
        )
    )
    add_point(8, *p8, tight=True)
    add_point(9, *p9, tight=True)

    return "\n".join(lines) + "\n"


def build_params_block(inputs: ProcessInputs, outputs: CalculatedOutputs):
    """Tạo block tham số L, n, G1, T2..T8, D1..D78, L5, L23, L78, Nl, Nd."""
    lines = [
        _matlab_assign("L", inputs.length_l),
        _matlab_assign("n", inputs.n),
        _matlab_assign("G1", inputs.flexural_imperfections),
        _matlab_assign("T2", outputs.t2),
        _matlab_assign("T3", outputs.t3),
        _matlab_assign("T4", outputs.t4),
        _matlab_assign("T6", outputs.t6),
        _matlab_assign("T7", outputs.t7),
        _matlab_assign("T8", outputs.t8),
        "",
        _matlab_assign("D1", outputs.d1),
        _matlab_assign("D2", outputs.d2),
        _matlab_assign("D5", outputs.d5),
        _matlab_assign("D8", outputs.d8),
        _matlab_assign("D9", outputs.d9),
        _matlab_assign("D23", outputs.d23),
        _matlab_assign("D78", outputs.d78),
        "",
        _matlab_assign("L5", outputs.l5),
        _matlab_assign("L23", inputs.l23),
        _matlab_assign("L78", inputs.l78),
        "",
        "",
        _matlab_assign("Nl", outputs.nl),
        _matlab_assign("Nd", outputs.nd),
    ]
    return "\n".join(lines) + "\n"


def apply_matlab_blocks(content, coordinates_block, params_block=None):
    """Thay block tọa độ và/hoặc block tham số trong nội dung file .m."""
    content = re.sub(
        r"%Input\r?\n.*?(?=\r?\nL=\s)",
        coordinates_block,
        content,
        count=1,
        flags=re.DOTALL,
    )

    if params_block is not None:
        content = re.sub(
            r"(?m)^L=\s.*?(?=^\s*%Incorporation code:)",
            params_block,
            content,
            count=1,
            flags=re.DOTALL | re.MULTILINE,
        )

    return content


def write_matlab_file(
    selected_points,
    matlab_template=MATLAB_TEMPLATE,
    matlab_output=MATLAB_OUTPUT,
    inputs=None,
    outputs=None,
    node_count=None,
):
    """Ghi file MATLAB ra thư mục đích."""
    out_dir = os.path.dirname(matlab_output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(matlab_template, "r", encoding="utf-8") as f:
        content = f.read()

    coordinates_block = build_coordinates_block(selected_points)
    params_block = None

    if inputs is not None and outputs is not None:
        if node_count is not None and inputs.n == 0:
            inputs.n = float(node_count)
        params_block = build_params_block(inputs, outputs)

    content = apply_matlab_blocks(content, coordinates_block, params_block)

    if node_count is not None and params_block is None:
        content = re.sub(
            r"(?m)^n=\s*[\d.]+\s*;",
            f"n=\t{node_count}\t;",
            content,
            count=1,
        )

    with open(matlab_output, "w", encoding="utf-8") as f:
        f.write(content)


def update_matlab_parameters(
    inputs: ProcessInputs,
    outputs: CalculatedOutputs,
    matlab_path=MATLAB_OUTPUT,
):
    """Cập nhật block L..Nd trong file MATLAB đã có."""
    if not os.path.exists(matlab_path):
        raise FileNotFoundError(f"Chưa có file MATLAB: {matlab_path}")

    with open(matlab_path, "r", encoding="utf-8") as f:
        content = f.read()

    params_block = build_params_block(inputs, outputs)
    content = re.sub(
        r"(?m)^L=\s.*?(?=^\s*%Incorporation code:)",
        params_block,
        content,
        count=1,
        flags=re.DOTALL | re.MULTILINE,
    )

    with open(matlab_path, "w", encoding="utf-8") as f:
        f.write(content)
