from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Callable, Iterable

from markitdown import MarkItDown, StreamInfo

from .models import ConversionProgress, ConversionResult
from .ocr import TesseractOCRService

SCANNED_PAGE_CHARACTER_THRESHOLD = 20
PDF_STREAM_INFO = StreamInfo(extension=".pdf", mimetype="application/pdf")

ProgressCallback = Callable[[ConversionProgress], None]
CancellationCallback = Callable[[], bool]


class ConversionCancelled(Exception):
    pass


class LocalPdfConversionService:
    def __init__(
        self,
        converter: MarkItDown | None = None,
        ocr_service: TesseractOCRService | None = None,
    ) -> None:
        self.converter = converter or MarkItDown(enable_plugins=False)
        self.ocr_service = ocr_service or TesseractOCRService()

    def convert_file(
        self,
        source_path: Path,
        output_dir: Path,
        on_progress: ProgressCallback = lambda progress: None,
        is_cancelled: CancellationCallback = lambda: False,
    ) -> ConversionResult:
        warnings: list[str] = []
        try:
            source_path = Path(source_path)
            output_dir = Path(output_dir)
            if source_path.suffix.lower() != ".pdf":
                raise ValueError("Selecione apenas arquivos PDF.")

            pdf_bytes = source_path.read_bytes()
            reader = self._open_reader(pdf_bytes)
            total_pages = len(reader.pages)
            if not total_pages:
                raise ValueError("O PDF nao possui paginas.")

            page_texts: list[str] = []
            for index, page in enumerate(reader.pages, start=1):
                if is_cancelled():
                    raise ConversionCancelled()
                page_texts.append(page.extract_text() or "")
                on_progress(
                    ConversionProgress(source_path.name, index, total_pages, "Analisando")
                )
            scanned_pages = [
                self._is_scanned_page(text)
                for text in page_texts
            ]

            if is_cancelled():
                raise ConversionCancelled()

            if not any(scanned_pages):
                on_progress(
                    ConversionProgress(
                        source_path.name, total_pages, total_pages, "Convertendo"
                    )
                )
                markdown = self._convert_pdf_bytes(pdf_bytes)
            else:
                markdown_parts: list[str] = []
                pdfium_document = self._open_pdfium_document(pdf_bytes)
                try:
                    for index, (page, is_scanned) in enumerate(
                        zip(reader.pages, scanned_pages), start=1
                    ):
                        if is_cancelled():
                            raise ConversionCancelled()
                        status = "OCR local" if is_scanned else "Convertendo"
                        on_progress(
                            ConversionProgress(
                                source_path.name, index, total_pages, status
                            )
                        )
                        if is_scanned:
                            text = self._ocr_page(pdfium_document, index - 1)
                            markdown_parts.append(
                                f"<!-- página {index}: OCR local -->\n\n{text}".rstrip()
                            )
                            if not text:
                                warnings.append(
                                    f"Página {index}: o OCR local não retornou texto."
                                )
                        else:
                            markdown_parts.append(self._convert_single_page(page))
                finally:
                    close = getattr(pdfium_document, "close", None)
                    if close is not None:
                        close()
                markdown = "\n\n".join(part for part in markdown_parts if part).strip()

            if is_cancelled():
                raise ConversionCancelled()
            output_path = self._next_output_path(output_dir, source_path.stem)
            self._write_output(output_path, markdown)
            on_progress(
                ConversionProgress(source_path.name, total_pages, total_pages, "Concluido")
            )
            return ConversionResult(source_path.name, output_path, warnings)
        except ConversionCancelled:
            return ConversionResult(
                source_path.name, None, warnings, "Conversão cancelada pelo usuário."
            )
        except Exception as exc:
            return ConversionResult(
                source_path.name, None, warnings, self._friendly_error(exc)
            )

    def convert_batch(
        self,
        source_paths: Iterable[Path],
        output_dir: Path,
        on_progress: ProgressCallback = lambda progress: None,
        is_cancelled: CancellationCallback = lambda: False,
    ) -> list[ConversionResult]:
        results: list[ConversionResult] = []
        for source_path in source_paths:
            if is_cancelled():
                break
            results.append(
                self.convert_file(source_path, output_dir, on_progress, is_cancelled)
            )
        return results

    def _open_reader(self, pdf_bytes: bytes):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise ValueError("PDF protegido por senha.")
        return reader

    def _open_pdfium_document(self, pdf_bytes: bytes):
        import pypdfium2

        return pypdfium2.PdfDocument(pdf_bytes)

    def _convert_pdf_bytes(self, pdf_bytes: bytes) -> str:
        result = self.converter.convert_stream(io.BytesIO(pdf_bytes), stream_info=PDF_STREAM_INFO)
        return result.markdown

    def _convert_single_page(self, page) -> str:
        from pypdf import PdfWriter

        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_page(page)
        writer.write(output)
        return self._convert_pdf_bytes(output.getvalue())

    def _ocr_page(self, pdfium_document, page_index: int) -> str:
        page = pdfium_document[page_index]
        try:
            bitmap = page.render(scale=300 / 72)
            image = bitmap.to_pil()
            png_stream = io.BytesIO()
            image.save(png_stream, format="PNG")
            result = self.ocr_service.extract_text(png_stream.getvalue())
            if result.error:
                raise RuntimeError(result.error)
            return result.text.strip()
        finally:
            close = getattr(page, "close", None)
            if close is not None:
                close()

    @staticmethod
    def _is_scanned_page(text: str) -> bool:
        return len(re.sub(r"\s+", "", text)) < SCANNED_PAGE_CHARACTER_THRESHOLD

    @staticmethod
    def _next_output_path(output_dir: Path, stem: str) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        candidate = output_dir / f"{stem}.md"
        counter = 2
        while candidate.exists():
            candidate = output_dir / f"{stem}_{counter}.md"
            counter += 1
        return candidate

    @staticmethod
    def _write_output(output_path: Path, markdown: str) -> None:
        try:
            with output_path.open("x", encoding="utf-8", newline="\n") as output_file:
                output_file.write(markdown)
        except Exception:
            output_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        message = str(exc).strip()
        lowered = message.lower()
        if "password" in lowered or "senha" in lowered or "decrypt" in lowered:
            return "PDF protegido por senha."
        if "eof" in lowered or "xref" in lowered or "invalid" in lowered:
            return "PDF corrompido ou ilegível."
        return message or "Não foi possível converter o PDF."
