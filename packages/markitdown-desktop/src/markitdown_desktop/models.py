from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConversionProgress:
    file_name: str
    current_page: int
    total_pages: int
    status: str


@dataclass
class ConversionResult:
    source_name: str
    output_path: Path | None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

