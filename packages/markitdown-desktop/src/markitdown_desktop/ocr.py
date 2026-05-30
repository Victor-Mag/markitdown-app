from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OCRResult:
    text: str
    error: str | None = None


def bundled_tesseract_dir() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return bundle_root / "resources" / "tesseract"


class TesseractOCRService:
    def __init__(self, tesseract_dir: Path | None = None) -> None:
        self.tesseract_dir = tesseract_dir or bundled_tesseract_dir()
        self.executable = self.tesseract_dir / "tesseract.exe"
        self.tessdata_dir = self.tesseract_dir / "tessdata"

    def extract_text(self, png_bytes: bytes) -> OCRResult:
        if not self.executable.is_file():
            return OCRResult("", f"Tesseract nao encontrado: {self.executable}")
        if not self.tessdata_dir.is_dir():
            return OCRResult("", f"Dados de idioma nao encontrados: {self.tessdata_dir}")

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(
                [
                    str(self.executable),
                    "stdin",
                    "stdout",
                    "--tessdata-dir",
                    str(self.tessdata_dir),
                    "-l",
                    "por+eng",
                    "--psm",
                    "3",
                ],
                input=png_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                creationflags=creationflags if os.name == "nt" else 0,
            )
        except OSError as exc:
            return OCRResult("", f"Nao foi possivel iniciar o Tesseract: {exc}")

        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            return OCRResult("", f"Tesseract falhou: {detail or completed.returncode}")

        return OCRResult(completed.stdout.decode("utf-8", errors="replace").strip())

