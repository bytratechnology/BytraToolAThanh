import math
import re
from pathlib import Path

PROCESS_DIR = Path("PROCESS")
MATRIX_FILE = PROCESS_DIR / "Matrix.txt"
MATLAB_FILE = PROCESS_DIR / "LT03DLK02DC10012_1p5m_E1_G_Duong.m"
MYFILE_OUTPUT = PROCESS_DIR / "myfile.txt"

_VAR_PATTERN = re.compile(
    r"^([A-Za-z][A-Za-z0-9]*)=\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*;",
    re.MULTILINE,
)

PI = 3.14


def _eq(a, b, tol=1e-5):
    return abs(a - b) <= tol


def parse_matlab_vars(m_path):
    text = Path(m_path).read_text(encoding="utf-8")
    return {m.group(1): float(m.group(2)) for m in _VAR_PATTERN.finditer(text)}


def _load_matrix(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
    return rows


def _save_matrix(path, rows):
    with Path(path).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(f"{row[0]:.6f} {row[1]:.6f} {row[2]:.6f}\n")


def run_incorporation_python(
    work_dir=PROCESS_DIR,
    matrix_file=None,
    m_file=None,
    output_file=None,
):
    """
    Chạy logic incorporation (tương đương file .m) bằng Python.
    Đọc Matrix.txt và tham số từ file .m, ghi myfile.txt.
    """
    work_dir = Path(work_dir)
    matrix_path = Path(matrix_file or work_dir / "Matrix.txt")
    m_path = Path(m_file or work_dir / "LT03DLK02DC10012_1p5m_E1_G_Duong.m")
    out_path = Path(output_file or work_dir / "myfile.txt")

    if not matrix_path.exists():
        raise FileNotFoundError(f"Không tìm thấy {matrix_path}")
    if not m_path.exists():
        raise FileNotFoundError(f"Không tìm thấy {m_path}")

    A = _load_matrix(matrix_path)
    v = parse_matlab_vars(m_path)
    n = int(v["n"])
    if len(A) != n:
        n = min(n, len(A))

    X1, Y1 = v["X1"], v["Y1"]
    X2, Y2 = v["X2"], v["Y2"]
    X23, Y23 = v["X23"], v["Y23"]
    X3, Y3 = v["X3"], v["Y3"]
    X4, Y4 = v["X4"], v["Y4"]
    X5, Y5 = v["X5"], v["Y5"]
    X6, Y6 = v["X6"], v["Y6"]
    X7, Y7 = v["X7"], v["Y7"]
    X78, Y78 = v["X78"], v["Y78"]
    X8, Y8 = v["X8"], v["Y8"]
    X9, Y9 = v["X9"], v["Y9"]

    L = v["L"]
    G1 = v["G1"]
    T2, T3, T4 = v["T2"], v["T3"], v["T4"]
    T6, T7, T8 = v["T6"], v["T7"], v["T8"]
    D1, D2, D5 = v["D1"], v["D2"], v["D5"]
    D8, D9 = v["D8"], v["D9"]
    D23, D78 = v["D23"], v["D78"]
    L5, L23, L78 = v["L5"], v["L23"], v["L78"]
    Nl, Nd = v["Nl"], v["Nd"]

    sin = math.sin

    for i in range(n):
        x, y, z = A[i]
        sz = sin(Nd * PI * z / L)
        s1 = sin(PI * z / L)
        snl = sin(Nl * PI * z / L)

        if _eq(x, X1) and _eq(y, Y1):
            A[i][1] += D1 * sz

        if _eq(x, X2) and _eq(y, Y2):
            A[i][0] += D2 * sz + T2 * s1

        if _eq(x, X23) and _eq(y, Y23):
            A[i][0] += D23 * sz + L23 * snl

        if _eq(x, X3) and _eq(y, Y3):
            A[i][0] += T3 * s1

        if _eq(x, X4) and _eq(y, Y4):
            A[i][1] += (G1 + T4) * s1

        if _eq(x, X5) and _eq(y, Y5):
            A[i][1] += G1 * s1 + L5 * snl + D5 * sz

        if _eq(x, X6) and _eq(y, Y6):
            A[i][1] += (G1 + T6) * s1

        if _eq(x, X7) and _eq(y, Y7):
            A[i][0] += T7 * s1

        if _eq(x, X78) and _eq(y, Y78):
            A[i][0] += D78 * sz + L78 * snl

        if _eq(x, X8) and _eq(y, Y8):
            A[i][0] += D8 * sz + T8 * s1

        if _eq(x, X9) and _eq(y, Y9):
            A[i][1] += D9 * sz

        if x < 0 and x > X1 and y > Y2:
            A[i][1] += D1 * sz * (x - X2) / (X1 - X2)

        if x < X1 and y > Y2:
            A[i][1] += D1 * sz * (x - X2) / (X1 - X2)

        if Y23 < y < Y2 and x < 0:
            A[i][0] += (
                (D23 * sz + L23 * snl) * (y - Y2)
                + (D2 * sz + T2 * s1) * (Y23 - y)
            ) / (Y23 - Y2)

        if Y3 < y < Y23 and x < 0:
            A[i][0] += (
                T3 * s1 * (y - Y23) + (D23 * sz + L23 * snl) * (Y3 - y)
            ) / (Y3 - Y23)

        if x < X5 and x > X4 and y < 0:
            A[i][1] += (
                (G1 * s1 + L5 * snl + D5 * sz) * (x - X4)
                + (G1 + T4) * s1 * (X5 - x)
            ) / (X5 - X4)

        if x < X6 and x > X5 and y < 0:
            A[i][1] += (
                (G1 + T6) * s1 * (x - X5)
                + (G1 * s1 + L5 * snl + D5 * sz) * (X6 - x)
            ) / (X6 - X5)

        if Y7 < y < Y78 and x > 0:
            A[i][0] += (
                (D78 * sz + L78 * snl) * (y - Y7) + T7 * s1 * (Y78 - y)
            ) / (Y78 - Y7)

        if Y78 < y < Y8 and x > 0:
            A[i][0] += (
                (D8 * sz + T8 * s1) * (y - Y78)
                + (D78 * sz + L78 * snl) * (Y8 - y)
            ) / (Y8 - Y78)

        if x > 0 and x < X9 and y > Y8:
            A[i][1] += D9 * sz * (X8 - x) / (X8 - X9)

        if x > X9 and y > Y8:
            A[i][1] += D9 * sz * (X8 - x) / (X8 - X9)

        if y > Y2 and x < 0:
            A[i][0] += (
                T3 * s1 * (y - Y2) + (D2 * sz + T2 * s1) * (Y3 - y)
            ) / (Y3 - Y2)

        if y < Y3 and x < X4:
            A[i][0] += (
                (T3 * s1 * (y - Y2) + (D2 * sz + T2 * s1) * (Y3 - y))
                / (Y3 - Y2)
                * (y - Y4)
                / (Y3 - Y4)
            )

        if (x < X4) or (x >= X4 and x < 0 and y > 0):
            A[i][1] += (
                (G1 * s1 + L5 * snl + D5 * sz) * (x - X4)
                + (G1 + T4) * s1 * (X5 - x)
            ) / (X5 - X4)

        if y > Y8 and x > 0:
            A[i][0] += (
                (D8 * sz + T8 * s1) * (y - Y7) + T7 * s1 * (Y8 - y)
            ) / (Y8 - Y7)

        if y < Y7 and x > X6:
            A[i][0] += (
                ((D8 * sz + T8 * s1) * (y - Y7) + T7 * s1 * (Y8 - y))
                / (Y8 - Y7)
                * (y - Y6)
                / (Y7 - Y6)
            )

        if (x > X6) or (x <= X6 and x > 0 and y > 0):
            A[i][1] += (
                (G1 + T6) * s1 * (x - X5)
                + (G1 * s1 + L5 * snl + D5 * sz) * (X6 - x)
            ) / (X6 - X5)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _save_matrix(out_path, A)

    return f"Đã chạy incorporation (Python), ghi {out_path} ({n} dòng)"
