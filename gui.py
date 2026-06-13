import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from branding import APP_NAME, APP_TAGLINE
from inputs import (
    CALCULATED_FIELD_LABELS,
    INPUT_FIELD_LABELS,
    ProcessInputs,
    compute_outputs,
    count_matrix_rows,
)
from main import run_processing
from matlab_runner import run_matlab_script
from matlab_writer import update_matlab_parameters
from paths import DEFAULT_PATHS, ProjectPaths

INPUT_SECTIONS = [
    (
        "Thông số chung",
        ["length_l", "n", "flexural_imperfections"],
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
STEP2_BUTTON_TEXT = "Bước 2 — Tính toán & Chạy incorporation"

PATH_FIELDS = [
    ("inp_source", "File .inp nguồn", "file", [("Abaqus INP", "*.inp"), ("All", "*.*")]),
    ("excel_template", "File Excel mẫu", "file", [("Excel", "*.xlsx"), ("All", "*.*")]),
    ("matlab_template", "File MATLAB mẫu", "file", [("MATLAB", "*.m"), ("All", "*.*")]),
    ("output_dir", "Thư mục lưu kết quả", "dir", None),
    ("inp_output", "File .inp kết quả (tùy chọn)", "save", [("Abaqus INP", "*.inp"), ("All", "*.*")]),
]


class InputForm(tk.Tk):
    """GUI: chọn file/thư mục, xử lý bước 1, nhập tham số, chạy incorporation."""

    def __init__(self, paths=None, node_count=None):
        super().__init__()
        self.title(APP_NAME)
        self.minsize(560, 680)
        self.geometry("620x860")
        self.configure(bg="#f0f0f0")

        self.paths = (paths or DEFAULT_PATHS).resolve()
        self.initial_node_count = node_count

        self.path_vars: dict[str, tk.StringVar] = {}
        self.entries: dict[str, ttk.Entry] = {}
        self.result_labels: dict[str, ttk.Label] = {}
        self.run_button: ttk.Button | None = None
        self.process_button: ttk.Button | None = None
        self.status_label: ttk.Label | None = None
        self.output_hint_label: ttk.Label | None = None
        self.log_text: scrolledtext.ScrolledText | None = None
        self._operation_running = False
        self._active_step: int | None = None

        self._setup_style()
        self._build_ui()
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
        self.path_vars["inp_source"].set(str(self.paths.inp_source))
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
            text="Chọn file, bấm Bước 1 để xử lý, nhập tham số rồi bấm Bước 2",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        canvas = tk.Canvas(self, bg="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scroll_body = ttk.Frame(canvas, padding=(16, 8, 16, 16))

        scroll_body.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_body, anchor="nw", width=580)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # --- Chọn file / thư mục ---
        paths_frame = ttk.LabelFrame(
            scroll_body,
            text="  Tệp & thư mục  ",
            style="Section.TLabelframe",
            padding=(12, 10),
        )
        paths_frame.pack(fill="x", pady=(0, 10))
        paths_frame.columnconfigure(1, weight=1)

        for row, (key, label, kind, filetypes) in enumerate(PATH_FIELDS):
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
            row=len(PATH_FIELDS), column=0, columnspan=3, sticky="w", pady=(6, 0)
        )
        self._update_output_hint()

        step1_frame = ttk.Frame(scroll_body, padding=(0, 0, 0, 10))
        step1_frame.pack(fill="x")
        self.process_button = ttk.Button(
            step1_frame,
            text=STEP1_BUTTON_TEXT,
            style="Action.TButton",
            command=self._on_process_step1,
        )
        self.process_button.pack(fill="x")

        # --- Ô nhập theo nhóm ---
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

                if field_name == "n" and self.initial_node_count:
                    entry.insert(0, str(self.initial_node_count))

        action_frame = ttk.Frame(scroll_body, padding=(0, 4, 0, 12))
        action_frame.pack(fill="x")

        self.run_button = ttk.Button(
            action_frame,
            text=STEP2_BUTTON_TEXT,
            style="Action.TButton",
            command=self._on_calculate,
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

    def get_paths(self) -> ProjectPaths:
        inp_out_text = self.path_vars["inp_output"].get().strip()
        return ProjectPaths(
            inp_source=Path(self.path_vars["inp_source"].get().strip()),
            excel_template=Path(self.path_vars["excel_template"].get().strip()),
            matlab_template=Path(self.path_vars["matlab_template"].get().strip()),
            output_dir=Path(self.path_vars["output_dir"].get().strip()),
            inp_output=Path(inp_out_text) if inp_out_text else None,
        ).resolve()

    def _update_output_hint(self):
        try:
            paths = self.get_paths()
            hint = (
                f"Lưu: {paths.matlab_output.name}, Matrix.txt, myfile.txt, "
                f"{paths.inp_result.name}"
            )
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

    def get_values(self, paths: ProjectPaths) -> ProcessInputs:
        data = {}
        for field_name, entry in self.entries.items():
            text = entry.get().strip()
            data[field_name] = float(text) if text else 0.0

        if data["n"] == 0.0:
            data["n"] = count_matrix_rows(paths.matrix_output)

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
                self.process_button.configure(text="Đang xử lý bước 1…")

        if self.run_button:
            self.run_button.configure(state="disabled")
            if step == 2:
                self.run_button.configure(text="Đang chạy bước 2…")

    def _end_operation(self):
        self._operation_running = False
        self._active_step = None

        if self.process_button:
            self.process_button.configure(state="normal", text=STEP1_BUTTON_TEXT)
        if self.run_button:
            self.run_button.configure(state="normal", text=STEP2_BUTTON_TEXT)

    def _on_process_step1(self):
        if self._operation_running:
            return

        self._begin_operation(step=1)
        self._set_status("Đang xử lý bước 1…")
        self._log("——— Bắt đầu Bước 1 ———")

        try:
            paths = self.get_paths()
            paths.validate_sources()
        except (ValueError, FileNotFoundError) as exc:
            self._log(f"Lỗi: {exc}")
            self._end_operation()
            self._set_status("Lỗi đường dẫn.")
            messagebox.showerror("Lỗi đường dẫn", str(exc))
            return

        def worker():
            try:
                node_count = run_processing(paths, on_progress=self._log)
            except Exception as exc:
                self.after(0, lambda msg=str(exc): self._on_step1_failed(msg))
                return
            self.after(0, lambda n=node_count: self._on_step1_success(n))

        threading.Thread(target=worker, daemon=True).start()

    def _on_step1_success(self, node_count: int):
        self._end_operation()
        self._set_status(f"Bước 1 hoàn tất — {node_count} node.")
        self._log(f"Bước 1: Xong ({node_count} node). Có thể nhập tham số và chạy Bước 2.")
        if "n" in self.entries:
            self.entries["n"].delete(0, tk.END)
            self.entries["n"].insert(0, str(node_count))
        self._update_output_hint()
        messagebox.showinfo(
            "Bước 1 hoàn tất",
            f"Đã xử lý {node_count} node.\nKết quả lưu trong thư mục đã chọn.",
        )

    def _on_step1_failed(self, error: str):
        self._end_operation()
        self._set_status("Lỗi bước 1.")
        self._log(f"Lỗi bước 1: {error}")
        messagebox.showerror("Lỗi bước 1", error)

    def _on_calculate(self):
        if self._operation_running:
            return

        self._begin_operation(step=2)
        self._set_status("Đang chạy bước 2…")
        self._log("——— Bắt đầu Bước 2 ———")

        try:
            paths = self.get_paths()
            self._log("Bước 2: Đang tính toán tham số D, T, Nl, Nd…")
            inputs = self.get_values(paths)
            outputs = compute_outputs(inputs)
        except ValueError as exc:
            self._log(f"Lỗi: {exc}")
            self._end_operation()
            self._set_status("Lỗi nhập liệu.")
            messagebox.showerror("Lỗi", str(exc))
            return
        except Exception:
            self._log("Lỗi: Giá trị nhập không hợp lệ.")
            self._end_operation()
            self._set_status("Lỗi nhập liệu.")
            messagebox.showerror("Lỗi", "Giá trị nhập không hợp lệ. Kiểm tra lại các ô.")
            return

        for field_name, label_widget in self.result_labels.items():
            value = getattr(outputs, field_name)
            label_widget.configure(text=self._format_value(value))
        self._log("Bước 2: Đã tính xong MD, D1–D9, L5, T2–T8, Nl, Nd.")

        try:
            self._log(f"Bước 2: Đang ghi tham số → {paths.matlab_output.name}…")
            update_matlab_parameters(inputs, outputs, str(paths.matlab_output))
            self._log("Bước 2: Đã ghi tham số vào file MATLAB.")
        except FileNotFoundError:
            self._log("Lỗi: Chưa có file MATLAB. Chạy Bước 1 trước.")
            self._end_operation()
            self._set_status("Cần chạy Bước 1 trước.")
            messagebox.showwarning(
                "Chưa có file MATLAB",
                "Chạy Bước 1 trước để tạo file MATLAB trong thư mục lưu.",
            )
            return

        threading.Thread(
            target=self._run_matlab_thread,
            args=(paths,),
            daemon=True,
        ).start()

    def _run_matlab_thread(self, paths: ProjectPaths):
        try:
            detail = run_matlab_script(paths=paths, on_progress=self._log)
        except Exception as exc:
            error_msg = str(exc)
            self.after(0, lambda msg=error_msg: self._on_matlab_failed(msg))
            return
        self.after(0, lambda d=detail, p=paths: self._on_matlab_success(d, p))

    def _on_matlab_success(self, detail: str, paths: ProjectPaths):
        self._end_operation()
        self._set_status("Bước 2 hoàn tất.")
        self._log("Bước 2: Hoàn tất.")
        messagebox.showinfo(
            "Bước 2 hoàn tất",
            f"Đã ghi tham số và tạo file kết quả trong:\n{paths.output_dir}\n\n"
            f"• {paths.myfile_output.name}\n"
            f"• {paths.inp_result.name}",
        )

    def _on_matlab_failed(self, error: str):
        self._end_operation()
        self._set_status("Lỗi bước 2.")
        self._log(f"Lỗi bước 2: {error}")
        messagebox.showerror(
            "Lỗi bước 2",
            f"Đã ghi tham số nhưng chạy incorporation thất bại:\n\n{error}",
        )

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
