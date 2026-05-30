import sys
from pathlib import Path

from markitdown_desktop.app import main
from markitdown_desktop.conversion import LocalPdfConversionService


def diagnostic_main(source: str, output_dir: str) -> int:
    result = LocalPdfConversionService().convert_file(Path(source), Path(output_dir))
    if result.error:
        print(result.error, file=sys.stderr)
        return 1
    print(result.output_path)
    return 0

if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--diagnostic-convert":
        raise SystemExit(diagnostic_main(sys.argv[2], sys.argv[3]))
    main()
