import shutil
from dataclasses import dataclass
from pathlib import Path

from app_runtime import application_dir, bundle_dir


@dataclass
class ProjectPaths:
    """Đường dẫn file nguồn và thư mục lưu kết quả."""

    inp_source: Path
    excel_template: Path
    matlab_template: Path
    output_dir: Path
    inp_output: Path | None = None

    @classmethod
    def defaults(cls, base_dir: Path | str | None = None):
        templates = Path(base_dir) if base_dir else bundle_dir()
        output = application_dir() / "output"
        return cls(
            inp_source=templates / "A_THANH/LT03D_LK02D_C10012_L1p5m_E1.inp",
            excel_template=templates / "A_THANH/ImperfectionsL_C10012_L1.5m.xlsx",
            matlab_template=templates / "A_THANH/LT03DLK02DC10012_1p5m_E1_G_Duong.m",
            output_dir=output,
        )

    def resolve(self) -> "ProjectPaths":
        """Chuẩn hóa đường dẫn tuyệt đối."""
        return ProjectPaths(
            inp_source=self.inp_source.expanduser().resolve(),
            excel_template=self.excel_template.expanduser().resolve(),
            matlab_template=self.matlab_template.expanduser().resolve(),
            output_dir=self.output_dir.expanduser().resolve(),
            inp_output=(
                self.inp_output.expanduser().resolve()
                if self.inp_output
                else None
            ),
        )

    @property
    def work_dir(self) -> Path:
        return self.output_dir / "_work"

    @property
    def excel_output(self) -> Path:
        return self.work_dir / self.excel_template.name

    @property
    def matrix_output(self) -> Path:
        return self.work_dir / "Matrix.txt"

    @property
    def selected_points_output(self) -> Path:
        return self.work_dir / "SelectedPoints.txt"

    @property
    def matlab_output(self) -> Path:
        return self.work_dir / self.matlab_template.name

    @property
    def myfile_output(self) -> Path:
        return self.work_dir / "myfile.txt"

    @property
    def inp_result(self) -> Path:
        if self.inp_output:
            return self.inp_output
        stem = self.inp_source.stem
        return self.output_dir / f"{stem}_IMPERFECTION{self.inp_source.suffix}"

    @property
    def matlab_script_name(self) -> str:
        return self.matlab_output.stem

    def validate_sources(self):
        """Kiểm tra file nguồn tồn tại."""
        missing = []
        for label, path in [
            ("File .inp", self.inp_source),
            ("File Excel mẫu", self.excel_template),
            ("File MATLAB mẫu", self.matlab_template),
        ]:
            if not path.is_file():
                missing.append(f"{label}: {path}")
        if missing:
            raise FileNotFoundError("\n".join(missing))

    def ensure_output_dir(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def ensure_work_dir(self):
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def cleanup_work_dir(self):
        if self.work_dir.is_dir():
            shutil.rmtree(self.work_dir)


DEFAULT_PATHS = ProjectPaths.defaults()
