from __future__ import annotations

import argparse
import json
from pathlib import Path

from converter import convert_pptx


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a PPTX deck into a study PDF package.")
    parser.add_argument("pptx", type=Path, help="Input .pptx file")
    parser.add_argument("output_dir", type=Path, help="Output directory")
    parser.add_argument("--no-pdf", action="store_true", help="Only write report.json and preview.html")
    parser.add_argument("--soffice-path", type=Path, help="Explicit LibreOffice soffice path")
    args = parser.parse_args()

    result = convert_pptx(
        args.pptx,
        args.output_dir,
        render_pdf=not args.no_pdf,
        soffice_path=args.soffice_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
