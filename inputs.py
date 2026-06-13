import math
from dataclasses import dataclass, fields
from pathlib import Path

MATRIX_OUTPUT = Path("PROCESS/Matrix.txt")


def count_matrix_rows(matrix_path=MATRIX_OUTPUT):
    """Đếm số dòng trong Matrix.txt (dùng cho n)."""
    path = Path(matrix_path)
    if not path.exists():
        return 0.0

    with path.open("r", encoding="utf-8") as f:
        return float(sum(1 for line in f if line.strip()))


@dataclass
class ProcessInputs:
    """Các tham số input kiểu float cho bước xử lý."""

    length_l: float = 0.0
    n: float = 0.0
    flexural_imperfections: float = 0.0
    initial_twist: float = 0.0
    hwl: float = 0.0
    hwd: float = 0.0
    thickness: float = 0.0
    xc: float = 0.0
    b: float = 0.0
    r: float = 0.0
    d: float = 0.0
    l: float = 0.0
    slenderness_distortional: float = 0.0
    slenderness_local: float = 0.0
    l23: float = 0.0
    l78: float = 0.0

    def as_dict(self):
        return {field.name: getattr(self, field.name) for field in fields(self)}


@dataclass
class CalculatedOutputs:
    """Kết quả tính từ ProcessInputs."""

    md: float = 0.0
    d1: float = 0.0
    d2: float = 0.0
    d5: float = 0.0
    d8: float = 0.0
    d9: float = 0.0
    d23: float = 0.0
    d78: float = 0.0
    l5: float = 0.0
    t2: float = 0.0
    t3: float = 0.0
    t4: float = 0.0
    t6: float = 0.0
    t7: float = 0.0
    t8: float = 0.0
    nl: float = 0.0
    nd: float = 0.0

    def as_dict(self):
        return {field.name: getattr(self, field.name) for field in fields(self)}


def _twist_tangent(initial_twist: float, length_l: float) -> float:
    """tan(IT * L * π / (2 * 1000 * 180)) — dùng π = 3.14 theo công thức."""
    angle_rad = initial_twist * length_l * 3.14 / (2 * 1000 * 180)
    return math.tan(angle_rad)


def compute_outputs(inputs: ProcessInputs) -> CalculatedOutputs:
    """Tính MD, D1–D9, D23, D78, L5, T2–T8, Nl, Nd từ tham số người dùng nhập."""
    thickness = inputs.thickness
    b = inputs.b
    r = inputs.r
    lip_l = inputs.l
    xc = inputs.xc
    d = inputs.d
    length_l = inputs.length_l
    initial_twist = inputs.initial_twist
    hwl = inputs.hwl
    hwd = inputs.hwd
    slenderness_distortional = inputs.slenderness_distortional
    slenderness_local = inputs.slenderness_local

    md = 0.3 * thickness * slenderness_distortional
    b_eff = b - 2 * r

    if b_eff == 0:
        raise ValueError("B - 2*r không được bằng 0")
    if hwl == 0:
        raise ValueError("HWL (hard-wave length local) không được bằng 0")
    if hwd == 0:
        raise ValueError("HWD (hard-wave length distortional) không được bằng 0")

    d1 = -md * (lip_l - r) / b_eff
    d2 = md
    d5 = 0.5 * 0.15 * thickness * slenderness_local
    d8 = -md
    d9 = d1
    d23 = md * (xc - r) / b_eff
    d78 = -d23
    l5 = 0.15 * thickness * slenderness_local

    tan_twist = _twist_tangent(initial_twist, length_l)
    t2 = (b - r - xc) * tan_twist
    t3 = -(xc - r) * tan_twist
    t4 = tan_twist * (d - 2 * r) / 2
    t6 = -t4
    t7 = t3
    t8 = t2
    nl = round(length_l / hwl)
    nd = round(length_l / hwd)

    return CalculatedOutputs(
        md=md,
        d1=d1,
        d2=d2,
        d5=d5,
        d8=d8,
        d9=d9,
        d23=d23,
        d78=d78,
        l5=l5,
        t2=t2,
        t3=t3,
        t4=t4,
        t6=t6,
        t7=t7,
        t8=t8,
        nl=nl,
        nd=nd,
    )


CALCULATED_FIELD_LABELS = {
    "md": "MD",
    "d1": "D1",
    "d2": "D2",
    "d5": "D5",
    "d8": "D8",
    "d9": "D9",
    "d23": "D23",
    "d78": "D78",
    "l5": "L5",
    "t2": "T2",
    "t3": "T3",
    "t4": "T4",
    "t6": "T6",
    "t7": "T7",
    "t8": "T8",
    "nl": "Nl",
    "nd": "Nd",
}


INPUT_FIELD_LABELS = {
    "length_l": "Length L",
    "n": "n",
    "flexural_imperfections": "Flexural imperfections",
    "initial_twist": "Initial twist (IT)",
    "hwl": "Hard-wave length local (HWL)",
    "hwd": "Hard-wave length distortional (HWD)",
    "thickness": "Thickness",
    "xc": "Xc",
    "b": "B",
    "r": "r",
    "d": "D",
    "l": "L",
    "slenderness_distortional": "Slenderness_Distortional",
    "slenderness_local": "Slenderness_Local",
    "l23": "L23",
    "l78": "L78",
}
