import threading
import tkinter as tk
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from abaqus_config import (
    auto_configure_abaqus,
    config_file_path,
    is_valid_abaqus_command,
    save_abaqus_command,
    search_abaqus_candidates,
)
from abaqus_job_settings import JOB_NUM_CPUS, resolve_job_num_cpus
from batch_models import (
    is_source_inp,
    parse_length_mm_from_name,
    paths_for_model,
    run_batch_models,
    run_single_model_pipeline,
)
from branding import APP_NAME, APP_TAGLINE
from inp_parser import parse_nodes_from_inp
from inputs import (
    CALCULATED_FIELD_LABELS,
    INPUT_FIELD_LABELS,
    ProcessInputs,
    compute_outputs,
)
from main import run_processing
from paths import DEFAULT_PATHS, ProjectPaths
from result_deliverables import summary_excel_path

INPUT_SECTIONS = [
    (
        "Thông số chung",
        ["flexural_imperfections"],
    ),
    (
        "Twist & half-wave",
        ["initial_twist", "hwl", "hwd"],
    ),
    (
        "Tiết diện",
        ["thickness", "xc", "b", "r", "d", "l"],
    ),
    (
        "Slenderness & khác",
        [
            "slenderness_distortional",
            "slenderness_local",
            "l23",
            "l78",
        ],
    ),
]

STEP1_BUTTON_TEXT = "Bước 1 — Xử lý .inp (Excel, Matrix, MATLAB)"
STEP2_BUTTON_TEXT = "Bước 2 — Tính toán, incorporation & Abaqus"

PATH_FIELDS = [
    ("excel_template", "File Excel mẫu", "file", [("Excel", "*.xlsx"), ("All", "*.*")]),
    ("matlab_template", "File MATLAB mẫu", "file", [("MATLAB", "*.m"), ("All", "*.*")]),
    ("output_dir", "Thư mục lưu kết quả", "dir", None),
    ("inp_output", "File .inp kết quả (tùy chọn)", "save", [("Abaqus INP", "*.inp"), ("All", "*.*")]),
]


class InputForm(tk.Tk):
    """GUI: Bước 1 — chọn file, tham số & xử lý .inp; Bước 2 — incorporation & Abaqus."""

    def __init__(self, paths=None, node_count=None):
        super().__init__()
        self.title(APP_NAME)
        self.minsize(820, 680)
        self.geometry("920x860")
        self.configure(bg="#f0f0f0")

        self.paths = (paths or DEFAULT_PATHS).resolve()
        self.initial_node_count = node_count

        self.path_vars: dict[str, tk.StringVar] = {}
        self.entries: dict[str, ttk.Entry] = {}
        self.result_labels: dict[str, ttk.Label] = {}
        self.process_button: ttk.Button | None = None
        self.run_button: ttk.Button | None = None
        self.abaqus_job_entry: ttk.Entry | None = None
        self.abaqus_path_var: tk.StringVar | None = None
        self.abaqus_status_label: ttk.Label | None = None
        self.run_abaqus_var: tk.BooleanVar | None = None
        self.inp_model_paths: list[Path] = []
        self.inp_models_rows_frame: ttk.Frame | None = None
        self.inp_model_rows: dict[str, dict] = {}
        self._inp_model_selected: set[str] = set()
        self.status_label: ttk.Label | None = None
        self.output_hint_label: ttk.Label | None = None
        self.log_text: scrolledtext.ScrolledText | None = None
        self._operation_running = False
        self._active_step: int | None = None

        self._setup_style()
        self._build_ui()
        auto_configure_abaqus()
        self._refresh_abaqus_status()
        self._center_window()

    def _setup_style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("Header.TLabel", font=("Helvetica", 16, "bold"))
        style.configure("Sub.TLabel", font=("Helvetica", 10), foreground="#555")
        style.configure("Section.TLabelframe.Label", font=("Helvetica", 11, "bold"))
        style.configure("Field.TLabel", font=("Helvetica", 11))
        style.configure("Result.TLabel", font=("Helvetica", 11), foreground="#1a5276")
        style.configure("Action.TButton", font=("Helvetica", 12, "bold"), padding=8)
        style.configure("Path.TEntry", font=("Helvetica", 10))

    def _center_window(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _init_path_vars(self):
        if self.paths.inp_source.is_file():
            self.inp_model_paths = [self.paths.inp_source.resolve()]
            self._refresh_inp_models_table()
        self.path_vars["excel_template"].set(str(self.paths.excel_template))
        self.path_vars["matlab_template"].set(str(self.paths.matlab_template))
        self.path_vars["output_dir"].set(str(self.paths.output_dir))
        if self.paths.inp_output:
            self.path_vars["inp_output"].set(str(self.paths.inp_output))
        else:
            self.path_vars["inp_output"].set("")

    def _build_ui(self):
        header = ttk.Frame(self, padding=(16, 14, 16, 8))
        header.pack(fill="x")

        ttk.Label(header, text=APP_NAME, style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text=APP_TAGLINE, style="Sub.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Label(
            header,
            text="Bước 1: chọn file & tham số → Bước 1 chạy → Bước 2 incorporation & Abaqus",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        canvas = tk.Canvas(self, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scroll_body = ttk.Frame(canvas, padding=(16, 8, 16, 16))

        scroll_body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_window = canvas.create_window((0, 0), window=scroll_body, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # --- Chọn file / thư mục ---
        paths_frame = ttk.LabelFrame(
            scroll_body,
            text="  Bước 1 — Tệp & thư mục  ",
            style="Section.TLabelframe",
            padding=(12, 10),
        )
        paths_frame.pack(fill="x", pady=(0, 10))
        paths_frame.columnconfigure(1, weight=1)

        ttk.Label(
            paths_frame,
            text="File .inp nguồn",
            style="Field.TLabel",
        ).grid(row=0, column=0, sticky="ne", padx=(0, 8), pady=4)

        inp_list_wrap = ttk.Frame(paths_frame)
        inp_list_wrap.grid(row=0, column=1, sticky="ew", pady=4)
        inp_list_wrap.columnconfigure(0, weight=1)
        inp_list_wrap.columnconfigure(1, weight=0, minsize=92)
        inp_list_wrap.columnconfigure(2, weight=0, minsize=92)

        models_header = ttk.Frame(inp_list_wrap)
        models_header.grid(row=0, column=0, columnspan=3, sticky="ew")
        models_header.columnconfigure(0, weight=1)
        models_header.columnconfigure(1, weight=0, minsize=92)
        models_header.columnconfigure(2, weight=0, minsize=92)
        ttk.Label(models_header, text="File .inp", style="Field.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(models_header, text="L (mm)", style="Field.TLabel").grid(
            row=0, column=1, padx=(6, 0), sticky="e"
        )
        ttk.Label(models_header, text="n (node)", style="Field.TLabel").grid(
            row=0, column=2, padx=(6, 0), sticky="e"
        )

        self.inp_models_rows_frame = ttk.Frame(inp_list_wrap)
        self.inp_models_rows_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.inp_models_rows_frame.columnconfigure(0, weight=1)
        self.inp_models_rows_frame.columnconfigure(1, weight=0, minsize=92)
        self.inp_models_rows_frame.columnconfigure(2, weight=0, minsize=92)

        inp_btn_frame = ttk.Frame(paths_frame)
        inp_btn_frame.grid(row=0, column=2, padx=(6, 0), pady=4, sticky="n")
        ttk.Button(
            inp_btn_frame,
            text="Thêm…",
            command=self._add_inp_models,
        ).pack(fill="x")
        ttk.Button(
            inp_btn_frame,
            text="Xóa",
            width=6,
            command=self._remove_inp_models,
        ).pack(fill="x", pady=(4, 0))
        ttk.Button(
            inp_btn_frame,
            text="Xóa hết",
            width=6,
            command=self._clear_inp_models,
        ).pack(fill="x", pady=(4, 0))

        ttk.Label(
            paths_frame,
            text="L/n tự điền từ file — có thể sửa thủ công. Click dòng để chọn (Ctrl/⌘ = nhiều dòng).",
            style="Sub.TLabel",
        ).grid(row=1, column=1, sticky="w", pady=(0, 4))

        for row, (key, label, kind, filetypes) in enumerate(PATH_FIELDS, start=2):
            var = tk.StringVar()
            self.path_vars[key] = var

            ttk.Label(paths_frame, text=label, style="Field.TLabel").grid(
                row=row, column=0, sticky="ne", padx=(0, 8), pady=4
            )
            entry = ttk.Entry(paths_frame, textvariable=var, style="Path.TEntry")
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            entry.bind("<FocusOut>", lambda _e: self._update_output_hint())

            ttk.Button(
                paths_frame,
                text="…",
                width=3,
                command=lambda k=key, t=kind, ft=filetypes: self._browse(k, t, ft),
            ).grid(row=row, column=2, padx=(6, 0), pady=4)

        self._init_path_vars()

        self.output_hint_label = ttk.Label(paths_frame, text="", style="Sub.TLabel")
        self.output_hint_label.grid(
            row=len(PATH_FIELDS) + 2, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

        self.process_button = ttk.Button(
            paths_frame,
            text=STEP1_BUTTON_TEXT,
            style="Action.TButton",
            command=self._on_run_step1,
        )
        self.process_button.grid(
            row=len(PATH_FIELDS) + 3,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )
        self._update_output_hint()

        # --- Ô nhập theo nhóm (Bước 1) ---
        for section_title, field_names in INPUT_SECTIONS:
            section = ttk.LabelFrame(
                scroll_body,
                text=f"  {section_title}  ",
                style="Section.TLabelframe",
                padding=(12, 10),
            )
            section.pack(fill="x", pady=(0, 10))
            section.columnconfigure(1, weight=1)

            for row, field_name in enumerate(field_names):
                label_text = INPUT_FIELD_LABELS[field_name]
                ttk.Label(section, text=label_text, style="Field.TLabel").grid(
                    row=row, column=0, sticky="e", padx=(0, 12), pady=5
                )

                entry = ttk.Entry(section, width=22, font=("Helvetica", 11))
                entry.grid(row=row, column=1, sticky="ew", pady=5)
                self.entries[field_name] = entry

        abaqus_frame = ttk.LabelFrame(
            scroll_body,
            text="  Abaqus (tuỳ chọn khi chạy Bước 2)  ",
            style="Section.TLabelframe",
            padding=(12, 10),
        )
        abaqus_frame.pack(fill="x", pady=(0, 10))
        abaqus_frame.columnconfigure(1, weight=1)

        ttk.Label(
            abaqus_frame,
            text="Tên job (để trống = tự lấy từ .inp)",
            style="Field.TLabel",
        ).grid(row=0, column=0, sticky="e", padx=(0, 12), pady=5)
        self.abaqus_job_entry = ttk.Entry(abaqus_frame, font=("Helvetica", 11))
        self.abaqus_job_entry.grid(row=0, column=1, sticky="ew", pady=5)

        max_cpus = JOB_NUM_CPUS
        default_cpus = min(resolve_job_num_cpus(), max_cpus)
        self.abaqus_cpus_var = tk.StringVar(value=str(default_cpus))
        ttk.Label(
            abaqus_frame,
            text="Số CPU (1–8)",
            style="Field.TLabel",
        ).grid(row=1, column=0, sticky="e", padx=(0, 12), pady=5)
        cpus_wrap = ttk.Frame(abaqus_frame)
        cpus_wrap.grid(row=1, column=1, sticky="w", pady=5)
        self.abaqus_cpus_spin = ttk.Spinbox(
            cpus_wrap,
            from_=1,
            to=8,
            textvariable=self.abaqus_cpus_var,
            width=6,
            font=("Helvetica", 11),
        )
        self.abaqus_cpus_spin.pack(side="left")
        ttk.Label(
            cpus_wrap,
            text="luồng (Threads) — mặc định theo lõi vật lý",
            style="Sub.TLabel",
        ).pack(side="left", padx=(8, 0))

        self.run_abaqus_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            abaqus_frame,
            text="Chạy phân tích Abaqus tự động sau khi tạo *_IMPERFECTION.inp",
            variable=self.run_abaqus_var,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        ttk.Label(abaqus_frame, text="Lệnh Abaqus", style="Field.TLabel").grid(
            row=3, column=0, sticky="e", padx=(0, 12), pady=5
        )
        self.abaqus_path_var = tk.StringVar()
        abaqus_path_entry = ttk.Entry(
            abaqus_frame,
            textvariable=self.abaqus_path_var,
            font=("Helvetica", 10),
        )
        abaqus_path_entry.grid(row=3, column=1, sticky="ew", pady=5)
        abaqus_path_entry.bind("<FocusOut>", lambda _e: self._refresh_abaqus_status())

        abaqus_btn_frame = ttk.Frame(abaqus_frame)
        abaqus_btn_frame.grid(row=3, column=2, padx=(6, 0), pady=5)
        ttk.Button(
            abaqus_btn_frame,
            text="…",
            width=3,
            command=self._browse_abaqus,
        ).pack(side="left")
        ttk.Button(
            abaqus_btn_frame,
            text="Tìm",
            width=4,
            command=self._auto_find_abaqus,
        ).pack(side="left", padx=(4, 0))

        self.abaqus_status_label = ttk.Label(abaqus_frame, text="", style="Sub.TLabel")
        self.abaqus_status_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

        action_frame = ttk.LabelFrame(
            scroll_body,
            text="  Bước 2 — Chạy  ",
            style="Section.TLabelframe",
            padding=(12, 10),
        )
        action_frame.pack(fill="x", pady=(0, 12))

        self.run_button = ttk.Button(
            action_frame,
            text=STEP2_BUTTON_TEXT,
            style="Action.TButton",
            command=self._on_run_step2,
        )
        self.run_button.pack(fill="x")

        self.status_label = ttk.Label(
            action_frame,
            text="Sẵn sàng.",
            style="Sub.TLabel",
        )
        self.status_label.pack(anchor="w", pady=(8, 0))

        log_frame = ttk.LabelFrame(
            scroll_body,
            text="  Nhật ký xử lý  ",
            style="Section.TLabelframe",
            padding=(12, 10),
        )
        log_frame.pack(fill="both", expand=True, pady=(0, 8))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=8,
            font=("Menlo", 10),
            state="disabled",
            wrap="word",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        results_frame = ttk.LabelFrame(
            scroll_body,
            text="  Kết quả tính  ",
            style="Section.TLabelframe",
            padding=(12, 10),
        )
        results_frame.pack(fill="x")
        results_frame.columnconfigure(1, weight=1)

        for row, (field_name, label) in enumerate(CALCULATED_FIELD_LABELS.items()):
            ttk.Label(results_frame, text=label, style="Field.TLabel").grid(
                row=row, column=0, sticky="e", padx=(0, 12), pady=4
            )
            value_label = ttk.Label(
                results_frame,
                text="—",
                style="Result.TLabel",
                anchor="w",
            )
            value_label.grid(row=row, column=1, sticky="w", pady=4)
            self.result_labels[field_name] = value_label

    def _refresh_abaqus_status(self):
        if not self.abaqus_status_label:
            return
        hint = self.abaqus_path_var.get().strip() if self.abaqus_path_var else ""
        saved = auto_configure_abaqus(hint or None)
        if self.abaqus_path_var and not hint and saved:
            self.abaqus_path_var.set(saved)
        check = (self.abaqus_path_var.get().strip() if self.abaqus_path_var else "") or saved
        if check and is_valid_abaqus_command(check):
            self.abaqus_status_label.configure(
                text=f"Sẵn sàng Abaqus — {check}",
                foreground="#1a5276",
            )
            return
        self.abaqus_status_label.configure(
            text=(
                "Chưa có Abaqus — cài SIMULIA rồi bấm 「Tìm」 hoặc chọn abaqus.bat "
                f"({config_file_path().name})"
            ),
            foreground="#a04000",
        )

    def _browse_abaqus(self):
        path = filedialog.askopenfilename(
            title="Chọn lệnh Abaqus (abaqus.bat)",
            filetypes=[
                ("Abaqus", "abaqus.bat;abq*.bat"),
                ("Batch", "*.bat"),
                ("All", "*.*"),
            ],
        )
        if not path:
            return
        try:
            save_abaqus_command(path)
        except (ValueError, FileNotFoundError) as exc:
            messagebox.showerror("Lỗi Abaqus", str(exc))
            return
        if self.abaqus_path_var:
            self.abaqus_path_var.set(path)
        self._refresh_abaqus_status()
        self._log(f"Đã chọn Abaqus: {path}")

    def _auto_find_abaqus(self):
        candidates = search_abaqus_candidates()
        if not candidates:
            messagebox.showwarning(
                "Không tìm thấy Abaqus",
                "Không tìm thấy abaqus.bat trên máy.\n\n"
                "Cài Abaqus (SIMULIA) hoặc chọn thủ công file abaqus.bat.",
            )
            self._refresh_abaqus_status()
            return
        chosen = candidates[0]
        try:
            save_abaqus_command(chosen)
        except OSError:
            pass
        if self.abaqus_path_var:
            self.abaqus_path_var.set(chosen)
        self._refresh_abaqus_status()
        self._log(f"Đã tìm thấy Abaqus: {chosen}")
        if len(candidates) > 1:
            self._log(f"(Có {len(candidates)} bản cài — dùng bản đầu tiên)")

    def _get_abaqus_cmd_hint(self) -> str | None:
        if self.abaqus_path_var:
            text = self.abaqus_path_var.get().strip()
            if text:
                return text
        return None

    def _read_abaqus_cpus(self) -> int:
        if not self.abaqus_cpus_var:
            return resolve_job_num_cpus()
        text = self.abaqus_cpus_var.get().strip()
        try:
            value = int(text)
        except ValueError:
            value = resolve_job_num_cpus()
        return max(1, min(JOB_NUM_CPUS, value))

    def get_inp_model_paths(self) -> list[Path]:
        return list(self.inp_model_paths)

    @staticmethod
    def _model_key(path: Path) -> str:
        return str(path.resolve())

    @staticmethod
    def _node_count_from_inp(path: Path) -> int | None:
        try:
            return len(parse_nodes_from_inp(path))
        except (OSError, ValueError):
            return None

    def _default_l_text(self, path: Path) -> str:
        length = parse_length_mm_from_name(path.name)
        return f"{length:g}" if length is not None else ""

    def _default_n_text(self, path: Path) -> str:
        node_count = self._node_count_from_inp(path)
        return str(node_count) if node_count is not None else ""

    def _snapshot_inp_model_params(self) -> dict[str, tuple[str, str]]:
        saved: dict[str, tuple[str, str]] = {}
        for key, row in self.inp_model_rows.items():
            saved[key] = (row["l_var"].get(), row["n_var"].get())
        return saved

    def _sync_row_selection_styles(self):
        for key, row in self.inp_model_rows.items():
            bg = "#d6eaf8" if key in self._inp_model_selected else "#f0f0f0"
            row["row_frame"].configure(background=bg)
            row["name_entry"].configure(background=bg, readonlybackground=bg)

    def _on_model_row_click(self, event, key: str):
        additive = bool(event.state & 0x4 or event.state & 0x8 or event.state & 0x20000)
        if additive:
            if key in self._inp_model_selected:
                self._inp_model_selected.discard(key)
            else:
                self._inp_model_selected.add(key)
        else:
            self._inp_model_selected = {key}
        self._sync_row_selection_styles()

    def _rebuild_inp_models_table(self):
        if not self.inp_models_rows_frame:
            return

        saved = self._snapshot_inp_model_params()
        for row in self.inp_model_rows.values():
            row["row_frame"].destroy()
        self.inp_model_rows.clear()

        valid_keys = {self._model_key(p) for p in self.inp_model_paths}
        self._inp_model_selected &= valid_keys

        for index, path in enumerate(self.inp_model_paths):
            key = self._model_key(path)
            if key in saved:
                l_text, n_text = saved[key]
            else:
                l_text = self._default_l_text(path)
                n_text = self._default_n_text(path)

            l_var = tk.StringVar(value=l_text)
            n_var = tk.StringVar(value=n_text)

            row_frame = tk.Frame(self.inp_models_rows_frame, bg="#f0f0f0")
            row_frame.grid(row=index, column=0, columnspan=3, sticky="ew", pady=1)
            row_frame.columnconfigure(0, weight=1)
            row_frame.columnconfigure(1, weight=0, minsize=92)
            row_frame.columnconfigure(2, weight=0, minsize=92)

            name_entry = tk.Entry(
                row_frame,
                font=("Helvetica", 10),
                relief="flat",
                readonlybackground="#f0f0f0",
                bg="#f0f0f0",
                width=1,
            )
            name_entry.insert(0, path.name)
            name_entry.config(state="readonly")
            name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

            l_entry = ttk.Entry(row_frame, textvariable=l_var, width=10, font=("Helvetica", 10))
            l_entry.grid(row=0, column=1, sticky="ew")
            l_entry.bind("<FocusOut>", lambda _e: self._update_output_hint())

            n_entry = ttk.Entry(row_frame, textvariable=n_var, width=10, font=("Helvetica", 10))
            n_entry.grid(row=0, column=2, sticky="ew", padx=(6, 0))
            n_entry.bind("<FocusOut>", lambda _e: self._update_output_hint())

            for widget in (row_frame, name_entry):
                widget.bind(
                    "<Button-1>",
                    lambda e, k=key: self._on_model_row_click(e, k),
                )

            self.inp_model_rows[key] = {
                "path": path,
                "l_var": l_var,
                "n_var": n_var,
                "row_frame": row_frame,
                "name_entry": name_entry,
            }

        self._sync_row_selection_styles()
        self._update_output_hint()

    def _read_model_l_n(self, path: Path) -> tuple[float, float]:
        key = self._model_key(path)
        row = self.inp_model_rows.get(key)
        if not row:
            raise ValueError(f"Không tìm thấy tham số L/n cho {path.name}")

        l_text = row["l_var"].get().strip()
        n_text = row["n_var"].get().strip()
        if not l_text:
            raise ValueError(f"{path.name}: ô L (mm) đang trống.")
        if not n_text:
            raise ValueError(f"{path.name}: ô n (node) đang trống.")
        try:
            length_l = float(l_text)
            n = float(n_text)
        except ValueError as exc:
            raise ValueError(f"{path.name}: L và n phải là số.") from exc
        if length_l <= 0:
            raise ValueError(f"{path.name}: L phải > 0.")
        if n <= 0:
            raise ValueError(f"{path.name}: n phải > 0.")
        return length_l, n

    def _collect_per_model_overrides(
        self, paths: list[Path]
    ) -> dict[str, tuple[float, float]]:
        overrides: dict[str, tuple[float, float]] = {}
        for path in paths:
            length_l, n = self._read_model_l_n(path)
            overrides[self._model_key(path)] = (length_l, n)
        return overrides

    def _set_model_n(self, path: Path, node_count: int):
        key = self._model_key(path)
        row = self.inp_model_rows.get(key)
        if row:
            row["n_var"].set(str(node_count))

    def _refresh_inp_models_table(self):
        self._rebuild_inp_models_table()

    def _add_inp_models(self):
        paths = filedialog.askopenfilenames(
            title="Chọn file .inp nguồn (giữ Ctrl/Shift để chọn nhiều)",
            filetypes=[("Abaqus INP", "*.inp"), ("All", "*.*")],
        )
        if not paths:
            return

        added = 0
        skipped = []
        existing = {str(p.resolve()) for p in self.inp_model_paths}
        for raw in paths:
            path = Path(raw).resolve()
            if not is_source_inp(path):
                skipped.append(f"{path.name} (file IMPERFECTION/kết quả)")
                continue
            key = str(path)
            if key in existing:
                continue
            self.inp_model_paths.append(path)
            existing.add(key)
            added += 1

        self.inp_model_paths.sort(key=lambda p: p.name.lower())
        self._refresh_inp_models_table()

        if added:
            self._log(f"Đã thêm {added} file .inp nguồn.")
        if skipped:
            messagebox.showwarning(
                "Bỏ qua file",
                "Không thêm các file sau:\n" + "\n".join(skipped),
            )

    def _remove_inp_models(self):
        if not self.inp_model_rows:
            return
        if not self._inp_model_selected:
            messagebox.showinfo("Xóa file", "Click chọn dòng mô hình (Ctrl/⌘ để chọn nhiều).")
            return
        remove_keys = set(self._inp_model_selected)
        self.inp_model_paths = [
            p for p in self.inp_model_paths if self._model_key(p) not in remove_keys
        ]
        self._inp_model_selected -= remove_keys
        self._rebuild_inp_models_table()

    def _clear_inp_models(self):
        if not self.inp_model_paths:
            return
        if not messagebox.askyesno("Xóa hết", "Xóa toàn bộ file .inp đã chọn?"):
            return
        self.inp_model_paths.clear()
        self._refresh_inp_models_table()

    def get_paths(self) -> ProjectPaths:
        inp_files = self.get_inp_model_paths()
        if not inp_files:
            raise ValueError("Chưa chọn file .inp nguồn — bấm 「Thêm…」 để chọn mô hình.")
        inp_out_text = self.path_vars["inp_output"].get().strip()
        return ProjectPaths(
            inp_source=inp_files[0],
            excel_template=Path(self.path_vars["excel_template"].get().strip()),
            matlab_template=Path(self.path_vars["matlab_template"].get().strip()),
            output_dir=Path(self.path_vars["output_dir"].get().strip()),
            inp_output=Path(inp_out_text) if inp_out_text else None,
        ).resolve()

    def _update_output_hint(self):
        try:
            inp_files = self.get_inp_model_paths()
            if len(inp_files) == 1:
                path = inp_files[0]
                paths = self.get_paths()
                try:
                    length_l, n = self._read_model_l_n(path)
                    l_part = f"L={length_l:g} mm"
                    n_part = f"n={int(n)}"
                except ValueError:
                    l_part = "L=—"
                    n_part = "n=—"
                hint = (
                    f"1 mô hình — {l_part}, {n_part} — "
                    f"kết quả: {paths.inp_result.name}"
                )
            elif inp_files:
                hint = f"{len(inp_files)} mô hình đã chọn — mỗi file một thư mục con trong output"
            else:
                hint = "Chưa chọn file .inp — bấm 「Thêm…」"
        except Exception:
            hint = ""
        if self.output_hint_label:
            self.output_hint_label.configure(text=hint)

    def _browse(self, key: str, kind: str, filetypes):
        if kind == "dir":
            path = filedialog.askdirectory(title="Chọn thư mục lưu kết quả")
        elif kind == "save":
            path = filedialog.asksaveasfilename(
                title="Chọn file .inp kết quả",
                defaultextension=".inp",
                filetypes=filetypes or [("All", "*.*")],
            )
        else:
            path = filedialog.askopenfilename(
                title="Chọn file",
                filetypes=filetypes or [("All", "*.*")],
            )
        if path:
            self.path_vars[key].set(path)
            self._update_output_hint()

    def get_values(self, paths: ProjectPaths, *, require_matrix_n: bool = False) -> ProcessInputs:
        data = {}
        for field_name, entry in self.entries.items():
            text = entry.get().strip()
            data[field_name] = float(text) if text else 0.0

        length_l, n = self._read_model_l_n(paths.inp_source)
        data["length_l"] = length_l
        data["n"] = n

        return ProcessInputs(**data)

    def _log(self, message: str):
        """Ghi thông báo ra nhật ký GUI và console (thread-safe)."""

        def append():
            timestamp = datetime.now().strftime("%H:%M:%S")
            line = f"[{timestamp}] {message}\n"
            if self.log_text:
                self.log_text.configure(state="normal")
                self.log_text.insert("end", line)
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            print(message, flush=True)

        if threading.current_thread() is threading.main_thread():
            append()
        else:
            self.after(0, append)

    def _set_status(self, text: str):
        if self.status_label:
            self.status_label.configure(text=text)

    def _begin_operation(self, step: int):
        """Khóa nút ngay khi bắt đầu để tránh nhấn liên tục."""
        self._operation_running = True
        self._active_step = step

        if self.process_button:
            self.process_button.configure(state="disabled")
            if step == 1:
                self.process_button.configure(text="Đang chạy Bước 1…")

        if self.run_button:
            self.run_button.configure(state="disabled")
            if step == 2:
                self.run_button.configure(text="Đang chạy Bước 2…")

    def _end_operation(self):
        self._operation_running = False
        self._active_step = None

        if self.process_button:
            self.process_button.configure(state="normal", text=STEP1_BUTTON_TEXT)
        if self.run_button:
            self.run_button.configure(state="normal", text=STEP2_BUTTON_TEXT)

    def _on_run_step1(self):
        if self._operation_running:
            return

        selected = self.get_inp_model_paths()
        if not selected:
            messagebox.showwarning(
                "Bước 1",
                "Chưa chọn file .inp — bấm 「Thêm…」 để chọn mô hình.",
            )
            return

        try:
            base_paths = self.get_paths()
            base_paths.validate_sources()
        except (ValueError, FileNotFoundError) as exc:
            messagebox.showerror("Bước 1", str(exc))
            return

        count = len(selected)
        if count > 1 and not messagebox.askyesno(
            "Xác nhận Bước 1",
            f"Chạy Bước 1 cho {count} mô hình?\n\n"
            "Mỗi file → Excel, Matrix.txt, MATLAB trong thư mục output riêng.",
        ):
            return

        self._begin_operation(step=1)
        if count == 1:
            self._set_status("Đang chạy Bước 1…")
            self._log(f"——— Bắt đầu Bước 1: {selected[0].name} ———")
        else:
            self._set_status(f"Đang chạy Bước 1 — {count} mô hình…")
            self._log(f"——— Bắt đầu Bước 1 — {count} mô hình ———")

        def worker():
            outcomes: list[tuple[Path, int | str]] = []
            try:
                for index, inp_path in enumerate(selected, start=1):
                    if count > 1:
                        self._log(f"════ Bước 1 — mô hình {index}/{count}: {inp_path.name} ════")
                    paths = paths_for_model(base_paths, inp_path)
                    node_count = run_processing(paths, on_progress=self._log)
                    outcomes.append((inp_path, node_count))
            except Exception as exc:
                self.after(0, lambda msg=str(exc): self._on_step1_failed(msg))
                return
            self.after(0, lambda o=outcomes: self._on_step1_finished(o))

        threading.Thread(target=worker, daemon=True).start()

    def _on_step1_finished(self, outcomes: list[tuple[Path, int]]):
        self._end_operation()
        for inp_path, node_count in outcomes:
            self._set_model_n(inp_path, node_count)
        self._update_output_hint()

        if len(outcomes) == 1:
            inp_path, node_count = outcomes[0]
            self._set_status(f"Bước 1 hoàn tất — {node_count} node.")
            self._log(f"Bước 1: Xong ({node_count} node). Có thể chạy Bước 2.")
            messagebox.showinfo(
                "Bước 1 hoàn tất",
                f"{inp_path.name}\n\n"
                f"n = {node_count} node\n"
                "Chạy Bước 2 để incorporation & Abaqus.",
            )
            return

        lines = [f"✓ {p.name} — n={n} node" for p, n in outcomes]
        self._set_status(f"Bước 1 hoàn tất — {len(outcomes)} mô hình.")
        self._log(f"Bước 1: Xong {len(outcomes)} mô hình. Có thể chạy Bước 2.")
        messagebox.showinfo(
            "Bước 1 hoàn tất",
            f"Đã xử lý {len(outcomes)} mô hình:\n\n" + "\n".join(lines),
        )

    def _on_step1_failed(self, error: str):
        self._end_operation()
        self._set_status("Bước 1 lỗi.")
        self._log(f"Bước 1 lỗi: {error}")
        messagebox.showerror("Bước 1 lỗi", error)

    def _on_run_step2(self):
        if self._operation_running:
            return

        selected = self.get_inp_model_paths()
        if not selected:
            messagebox.showwarning(
                "Bước 2",
                "Chưa chọn file .inp — bấm 「Thêm…」 để chọn mô hình.",
            )
            return

        try:
            per_model_overrides = self._collect_per_model_overrides(selected)
        except ValueError as exc:
            messagebox.showerror("Bước 2", str(exc))
            return

        try:
            base_paths = self.get_paths()
            base_paths.validate_sources()
            inputs = self.get_values(base_paths, require_matrix_n=False)
        except (ValueError, FileNotFoundError) as exc:
            messagebox.showerror("Bước 2", str(exc))
            return
        except Exception:
            messagebox.showerror("Bước 2", "Giá trị nhập không hợp lệ. Kiểm tra lại các ô.")
            return

        count = len(selected)
        if count > 1 and not messagebox.askyesno(
            "Xác nhận Bước 2",
            f"Chạy {count} mô hình?\n\n"
            "L và n: lấy từ ô từng mô hình (có thể đã sửa thủ công).\n"
            "Các tham số khác giữ nguyên từ form.",
        ):
            return

        self._begin_operation(step=2)
        if count == 1:
            self._set_status("Đang chạy Bước 2…")
            self._log(f"——— Bắt đầu Bước 2: {selected[0].name} ———")
        else:
            self._set_status(f"Đang chạy Bước 2 — {count} mô hình…")
            self._log(f"——— Bắt đầu Bước 2 — {count} mô hình ———")

        run_abaqus = bool(self.run_abaqus_var and self.run_abaqus_var.get())
        job_name = ""
        if self.abaqus_job_entry:
            job_name = self.abaqus_job_entry.get().strip()
        abaqus_cpus = self._read_abaqus_cpus()
        if run_abaqus:
            self._log(f"Bước 2: Abaqus dùng {abaqus_cpus} CPU (Threads)")

        def worker():
            try:
                if count == 1:
                    key = self._model_key(selected[0])
                    length_l, n = per_model_overrides[key]
                    results = [
                        run_single_model_pipeline(
                            base_paths,
                            selected[0],
                            inputs,
                            run_abaqus=run_abaqus,
                            abaqus_cmd=self._get_abaqus_cmd_hint(),
                            job_name=job_name or None,
                            abaqus_cpus=abaqus_cpus,
                            include_step1=False,
                            length_l_override=length_l,
                            n_override=n,
                            on_progress=self._log,
                        )
                    ]
                else:
                    results = run_batch_models(
                        base_paths,
                        selected,
                        inputs,
                        run_abaqus=run_abaqus,
                        abaqus_cmd=self._get_abaqus_cmd_hint(),
                        job_name=job_name or None,
                        abaqus_cpus=abaqus_cpus,
                        include_step1=False,
                        per_model_overrides=per_model_overrides,
                        on_progress=self._log,
                    )
            except Exception as exc:
                self.after(0, lambda msg=str(exc): self._on_run_failed(msg))
                return
            self.after(0, lambda r=results: self._on_run_finished(r, base_paths, inputs))

        threading.Thread(target=worker, daemon=True).start()

    def _on_run_finished(self, results, base_paths: ProjectPaths, inputs: ProcessInputs):
        self._end_operation()
        ok = sum(1 for r in results if r.success)
        fail = len(results) - ok

        if len(results) == 1:
            result = results[0]
            if result.success:
                self._set_status("Bước 2 hoàn tất.")
                self._log("Bước 2: Hoàn tất.")
                self._update_result_labels(result, base_paths, inputs)
                extra = ""
                if result.max_rf3_bc1 is not None:
                    extra = f"\nMax RF3 (BC-1): {result.max_rf3_bc1:g}"
                excel = summary_excel_path(base_paths.output_dir)
                if excel.is_file():
                    extra += f"\nExcel tổng hợp: {excel}"
                messagebox.showinfo(
                    "Bước 2 hoàn tất",
                    f"Đã xử lý:\n{result.inp_path.name}\n\n"
                    f"Thư mục kết quả:\n{result.output_dir}"
                    f"{extra}",
                )
            else:
                self._set_status("Bước 2 lỗi.")
                self._log(f"Bước 2 lỗi: {result.error}")
                messagebox.showerror("Bước 2 lỗi", result.error or "Lỗi không xác định.")
            return

        self._set_status(f"Bước 2 xong — {ok} thành công, {fail} lỗi.")
        self._log(f"Bước 2: Hoàn tất — {ok}/{len(results)} thành công.")

        lines = []
        for result in results:
            if result.success:
                lines.append(f"✓ {result.inp_path.name} (L={result.length_l:g})")
            else:
                lines.append(f"✗ {result.inp_path.name}: {result.error}")

        excel = summary_excel_path(base_paths.output_dir)
        excel_note = f"\n\nExcel tổng hợp:\n{excel}" if excel.is_file() else ""
        messagebox.showinfo(
            "Bước 2 hoàn tất",
            f"Thành công: {ok}/{len(results)}\n\n" + "\n".join(lines) + excel_note,
        )

    def _update_result_labels(
        self,
        result,
        base_paths: ProjectPaths,
        inputs: ProcessInputs,
    ):
        paths = paths_for_model(base_paths, result.inp_path)
        try:
            length_l, n = self._read_model_l_n(result.inp_path)
            model_inputs = replace(inputs, length_l=length_l, n=n)
            outputs = compute_outputs(model_inputs)
        except (ValueError, FileNotFoundError):
            return

        for field_name, label_widget in self.result_labels.items():
            value = getattr(outputs, field_name)
            label_widget.configure(text=self._format_value(value))

    def _on_run_failed(self, error: str):
        self._end_operation()
        self._set_status("Bước 2 lỗi.")
        self._log(f"Bước 2 lỗi: {error}")
        messagebox.showerror("Bước 2 lỗi", error)

    @staticmethod
    def _format_value(value: float) -> str:
        if value == int(value):
            return str(int(value))
        return f"{value:.8g}"


def launch_gui(paths=None, node_count=None):
    app = InputForm(paths=paths, node_count=node_count)
    app.mainloop()


def main():
    launch_gui()


if __name__ == "__main__":
    main()
