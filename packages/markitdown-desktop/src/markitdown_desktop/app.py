from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .conversion import LocalPdfConversionService
from .models import ConversionProgress, ConversionResult


class PdfToMarkdownApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PDF para Markdown")
        self.root.geometry("720x520")
        self.source_paths: list[Path] = []
        self.output_dir: Path | None = None
        self.cancel_event = threading.Event()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self._build_ui()
        self.root.after(100, self._consume_events)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Processamento local. Nenhum documento é enviado pela internet.",
            foreground="#176b2c",
        ).pack(anchor=tk.W, pady=(0, 12))

        button_row = ttk.Frame(frame)
        button_row.pack(fill=tk.X)
        ttk.Button(button_row, text="Selecionar PDFs", command=self._select_pdfs).pack(
            side=tk.LEFT
        )
        ttk.Button(
            button_row, text="Escolher pasta de saída", command=self._select_output_dir
        ).pack(side=tk.LEFT, padx=8)

        self.file_list = tk.Listbox(frame, height=10)
        self.file_list.pack(fill=tk.BOTH, expand=True, pady=12)

        self.output_label = ttk.Label(frame, text="Pasta de saída: não selecionada")
        self.output_label.pack(anchor=tk.W)
        self.status_label = ttk.Label(frame, text="Pronto")
        self.status_label.pack(anchor=tk.W, pady=(12, 4))
        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.pack(fill=tk.X)

        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X, pady=(12, 0))
        self.convert_button = ttk.Button(
            action_row, text="Converter", command=self._start_conversion
        )
        self.convert_button.pack(side=tk.LEFT)
        self.cancel_button = ttk.Button(
            action_row, text="Cancelar", command=self.cancel_event.set, state=tk.DISABLED
        )
        self.cancel_button.pack(side=tk.LEFT, padx=8)

    def _select_pdfs(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecione os PDFs",
            filetypes=[("Arquivos PDF", "*.pdf")],
        )
        if not paths:
            return
        self.source_paths = [Path(path) for path in paths]
        self.file_list.delete(0, tk.END)
        for path in self.source_paths:
            self.file_list.insert(tk.END, path.name)

    def _select_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Escolha a pasta de saida")
        if path:
            self.output_dir = Path(path)
            self.output_label.config(text=f"Pasta de saída: {self.output_dir}")

    def _start_conversion(self) -> None:
        if not self.source_paths or self.output_dir is None:
            messagebox.showwarning(
                "Seleção incompleta", "Selecione ao menos um PDF e a pasta de saída."
            )
            return
        self.cancel_event.clear()
        self.convert_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        self.worker = threading.Thread(target=self._run_conversion, daemon=True)
        self.worker.start()

    def _run_conversion(self) -> None:
        try:
            service = LocalPdfConversionService()
            results = service.convert_batch(
                self.source_paths,
                self.output_dir or Path.cwd(),
                on_progress=lambda progress: self.events.put(("progress", progress)),
                is_cancelled=self.cancel_event.is_set,
            )
        except Exception as exc:
            results = [
                ConversionResult(
                    source_name=path.name,
                    output_path=None,
                    error=f"Falha ao iniciar a conversão: {exc}",
                )
                for path in self.source_paths
            ]
        self.events.put(("finished", results))

    def _consume_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "progress":
                    self._show_progress(payload)  # type: ignore[arg-type]
                elif event == "finished":
                    self._show_results(payload)  # type: ignore[arg-type]
        except queue.Empty:
            pass
        self.root.after(100, self._consume_events)

    def _show_progress(self, progress: ConversionProgress) -> None:
        self.progress["maximum"] = max(progress.total_pages, 1)
        self.progress["value"] = progress.current_page
        self.status_label.config(
            text=(
                f"{progress.file_name}: {progress.status} "
                f"({progress.current_page}/{progress.total_pages})"
            )
        )

    def _show_results(self, results: list[ConversionResult]) -> None:
        self.convert_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.DISABLED)
        completed = [result for result in results if result.output_path]
        failed = [result for result in results if result.error]
        warnings = [warning for result in results for warning in result.warnings]
        lines = [
            f"Concluídos: {len(completed)}",
            f"Falhas ou cancelamentos: {len(failed)}",
        ]
        lines.extend(f"- Gerado: {result.output_path}" for result in completed)
        lines.extend(f"- {result.source_name}: {result.error}" for result in failed)
        lines.extend(f"- Aviso: {warning}" for warning in warnings)
        self.status_label.config(text="Processamento finalizado")
        messagebox.showinfo("Resumo da conversão", "\n".join(lines))


def main() -> None:
    root = tk.Tk()
    PdfToMarkdownApp(root)
    root.mainloop()
