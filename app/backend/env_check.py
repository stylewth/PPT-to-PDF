from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Any, Sequence

from native_converter import NativeConversionError, find_soffice


def check_environment(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    soffice_path: str | Path | None = None,
    soffice_search_paths: Sequence[str | Path] | None = None,
) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    checks["python"] = {
        "ok": sys.version_info >= (3, 10),
        "message": f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }
    try:
        soffice = find_soffice(soffice_path=soffice_path, search_paths=soffice_search_paths)
        checks["libreoffice"] = {
            "ok": soffice is not None,
            "message": f"LibreOffice: {soffice}" if soffice else "LibreOffice soffice not found. Install LibreOffice.",
        }
    except NativeConversionError as exc:
        checks["libreoffice"] = {"ok": False, "message": str(exc)}
    try:
        import fitz  # noqa: F401
        checks["pymupdf"] = {"ok": True, "message": "PyMuPDF available."}
    except ModuleNotFoundError:
        checks["pymupdf"] = {
            "ok": False,
            "message": "PyMuPDF not found. Run: python -m pip install PyMuPDF",
        }
    try:
        import PIL  # noqa: F401
        checks["pillow"] = {"ok": True, "message": "Pillow available."}
    except ModuleNotFoundError:
        checks["pillow"] = {
            "ok": False,
            "message": "Pillow not found. Run: python -m pip install Pillow",
        }
    checks["port"] = _port_check(host, port)
    return {"ok": all(item["ok"] for item in checks.values()), "checks": checks}


def _port_check(host: str, port: int) -> dict[str, Any]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex((host, port))
    if result == 0:
        return {"ok": False, "message": f"Port {port} is already in use."}
    return {"ok": True, "message": f"Port {port} is available."}


if __name__ == "__main__":
    import json

    result = check_environment()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
