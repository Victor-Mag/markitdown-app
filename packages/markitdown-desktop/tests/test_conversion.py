import subprocess
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

fake_markitdown = types.ModuleType("markitdown")


@dataclass(frozen=True)
class StreamInfo:
    extension: str | None = None
    mimetype: str | None = None


class MarkItDown:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


fake_markitdown.MarkItDown = MarkItDown
fake_markitdown.StreamInfo = StreamInfo
sys.modules["markitdown"] = fake_markitdown

from markitdown_desktop.conversion import (
    PDF_STREAM_INFO,
    SCANNED_PAGE_CHARACTER_THRESHOLD,
    LocalPdfConversionService,
)
from markitdown_desktop.ocr import OCRResult, TesseractOCRService


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.closed = False

    def extract_text(self) -> str:
        return self.text

    def close(self) -> None:
        self.closed = True


class FakeReader:
    def __init__(self, *texts: str) -> None:
        self.pages = [FakePage(text) for text in texts]


class FakeConverter:
    def __init__(self, markdown: str = "markdown") -> None:
        self.markdown = markdown
        self.calls = []

    def convert_stream(self, stream, *, stream_info):
        self.calls.append((stream.read(), stream_info))
        return SimpleNamespace(markdown=self.markdown)


class FakeImage:
    def save(self, stream, *, format: str) -> None:
        self.format = format
        stream.write(b"png bytes")


class FakeBitmap:
    def to_pil(self) -> FakeImage:
        return FakeImage()


class FakePdfiumPage:
    def __init__(self) -> None:
        self.scale = None
        self.closed = False

    def render(self, *, scale: float) -> FakeBitmap:
        self.scale = scale
        return FakeBitmap()

    def close(self) -> None:
        self.closed = True


class FakePdfiumDocument:
    def __init__(self, page_count: int) -> None:
        self.pages = [FakePdfiumPage() for _ in range(page_count)]
        self.closed = False

    def __getitem__(self, index: int) -> FakePdfiumPage:
        return self.pages[index]

    def close(self) -> None:
        self.closed = True


class FakeOCR:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = []

    def extract_text(self, png_bytes: bytes) -> OCRResult:
        self.calls.append(png_bytes)
        return OCRResult(self.text)


class LocalPdfConversionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "documento.pdf"
        self.source.write_bytes(b"pdf bytes")
        self.output = self.root / "output"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_text_pdf_uses_markitdown_convert_stream(self) -> None:
        converter = FakeConverter("texto convertido")
        service = LocalPdfConversionService(converter=converter, ocr_service=FakeOCR(""))
        service._open_reader = lambda data: FakeReader("x" * 30)

        result = service.convert_file(self.source, self.output)

        self.assertIsNone(result.error)
        self.assertEqual(result.output_path.read_text(encoding="utf-8"), "texto convertido")
        self.assertEqual(converter.calls, [(b"pdf bytes", PDF_STREAM_INFO)])

    def test_text_pdf_converts_with_network_blocked(self) -> None:
        converter = FakeConverter("offline")
        service = LocalPdfConversionService(converter=converter, ocr_service=FakeOCR(""))
        service._open_reader = lambda data: FakeReader("x" * 30)

        with patch(
            "socket.create_connection",
            side_effect=AssertionError("network access is forbidden"),
        ):
            result = service.convert_file(self.source, self.output)

        self.assertIsNone(result.error)
        self.assertEqual(result.output_path.read_text(encoding="utf-8"), "offline")

    def test_fully_scanned_pdf_uses_local_ocr(self) -> None:
        service = LocalPdfConversionService(
            converter=FakeConverter(), ocr_service=FakeOCR("texto OCR")
        )
        service._open_reader = lambda data: FakeReader("")
        service._open_pdfium_document = lambda data: FakePdfiumDocument(1)

        result = service.convert_file(self.source, self.output)

        self.assertEqual(
            result.output_path.read_text(encoding="utf-8"),
            "<!-- página 1: OCR local -->\n\ntexto OCR",
        )

    def test_mixed_pdf_preserves_page_order_and_uses_local_ocr(self) -> None:
        ocr = FakeOCR("pagina digitalizada")
        pdfium = FakePdfiumDocument(2)
        service = LocalPdfConversionService(converter=FakeConverter(), ocr_service=ocr)
        service._open_reader = lambda data: FakeReader("texto suficiente " * 3, "")
        service._open_pdfium_document = lambda data: pdfium
        service._convert_single_page = lambda page: "pagina textual"

        result = service.convert_file(self.source, self.output)

        markdown = result.output_path.read_text(encoding="utf-8")
        self.assertEqual(
            markdown,
            "pagina textual\n\n<!-- página 2: OCR local -->\n\npagina digitalizada",
        )
        self.assertEqual(ocr.calls, [b"png bytes"])
        self.assertAlmostEqual(pdfium.pages[1].scale, 300 / 72)
        self.assertTrue(pdfium.pages[1].closed)
        self.assertTrue(pdfium.closed)

    def test_empty_ocr_adds_warning(self) -> None:
        service = LocalPdfConversionService(converter=FakeConverter(), ocr_service=FakeOCR(""))
        service._open_reader = lambda data: FakeReader("")
        service._open_pdfium_document = lambda data: FakePdfiumDocument(1)

        result = service.convert_file(self.source, self.output)

        self.assertIsNone(result.error)
        self.assertEqual(result.warnings, ["Página 1: o OCR local não retornou texto."])

    def test_existing_destination_uses_incremental_name(self) -> None:
        self.output.mkdir()
        (self.output / "documento.md").write_text("existing", encoding="utf-8")
        service = LocalPdfConversionService(converter=FakeConverter(), ocr_service=FakeOCR(""))
        service._open_reader = lambda data: FakeReader("x" * 30)

        result = service.convert_file(self.source, self.output)

        self.assertEqual(result.output_path.name, "documento_2.md")

    def test_cancel_does_not_write_partial_markdown(self) -> None:
        service = LocalPdfConversionService(converter=FakeConverter(), ocr_service=FakeOCR(""))
        service._open_reader = lambda data: FakeReader("x" * 30)

        result = service.convert_file(self.source, self.output, is_cancelled=lambda: True)

        self.assertEqual(result.error, "Conversão cancelada pelo usuário.")
        self.assertFalse(self.output.exists())

    def test_batch_continues_after_individual_failure(self) -> None:
        second = self.root / "segundo.pdf"
        second.write_bytes(b"second")
        service = LocalPdfConversionService(converter=FakeConverter(), ocr_service=FakeOCR(""))
        calls = 0

        def open_reader(data):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("invalid xref")
            return FakeReader("x" * 30)

        service._open_reader = open_reader
        results = service.convert_batch([self.source, second], self.output)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].error, "PDF corrompido ou ilegível.")
        self.assertIsNotNone(results[1].output_path)

    def test_password_protected_pdf_has_friendly_error(self) -> None:
        service = LocalPdfConversionService(converter=FakeConverter(), ocr_service=FakeOCR(""))
        service._open_reader = lambda data: (_ for _ in ()).throw(ValueError("decrypt"))

        result = service.convert_file(self.source, self.output)

        self.assertEqual(result.error, "PDF protegido por senha.")

    def test_scanned_page_threshold_is_internal_constant(self) -> None:
        self.assertEqual(SCANNED_PAGE_CHARACTER_THRESHOLD, 20)
        self.assertTrue(LocalPdfConversionService._is_scanned_page("a " * 19))
        self.assertFalse(LocalPdfConversionService._is_scanned_page("a " * 20))


class TesseractOCRServiceTests(unittest.TestCase):
    def test_tesseract_uses_stdin_stdout_languages_and_local_tessdata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tesseract.exe").write_bytes(b"")
            (root / "tessdata").mkdir()
            service = TesseractOCRService(root)
            completed = SimpleNamespace(returncode=0, stdout=b"texto", stderr=b"")
            paths_before = sorted(path.relative_to(root) for path in root.rglob("*"))

            with patch("markitdown_desktop.ocr.subprocess.run", return_value=completed) as run:
                result = service.extract_text(b"png")

            paths_after = sorted(path.relative_to(root) for path in root.rglob("*"))
            self.assertEqual(result.text, "texto")
            self.assertEqual(paths_after, paths_before)
            args = run.call_args.args[0]
            self.assertEqual(args[1:3], ["stdin", "stdout"])
            self.assertIn(str(root / "tessdata"), args)
            self.assertIn("por+eng", args)
            self.assertEqual(run.call_args.kwargs["input"], b"png")
            self.assertEqual(run.call_args.kwargs["stdout"], subprocess.PIPE)
            self.assertEqual(run.call_args.kwargs["stderr"], subprocess.PIPE)


if __name__ == "__main__":
    unittest.main()
