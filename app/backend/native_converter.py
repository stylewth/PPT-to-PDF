from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence


class NativeConversionError(RuntimeError):
    pass


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ProgressCallback = Callable[[dict[str, Any]], None]

DEFAULT_WINDOWS_SOFFICE_PATHS = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)

_cached_soffice_path: Path | None = None


def convert_pptx_to_pdf(
    pptx_path: str | Path,
    output_dir: str | Path,
    *,
    soffice_path: str | Path | None = None,
    search_paths: Sequence[str | Path] | None = None,
    timeout_seconds: int = 120,
    command_runner: CommandRunner | None = None,
    output_name: str = "base.pdf",
    progress: ProgressCallback | None = None,
) -> Path:
    source = Path(pptx_path)
    if source.suffix.lower() != ".pptx":
        raise NativeConversionError("Only .pptx files can be converted by the native converter.")
    if not source.exists():
        raise NativeConversionError(f"PPTX file not found: {source}")

    soffice = find_soffice(soffice_path=soffice_path, search_paths=search_paths)
    if soffice is None:
        raise NativeConversionError(
            "LibreOffice soffice was not found. Install LibreOffice or configure an Unoserver/LibreOffice path."
        )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    work_dir = output / f".native_conversion_{uuid.uuid4().hex}"
    import tempfile as _tempfile
    profile_dir = Path(_tempfile.gettempdir()) / "slide2study_lo_profile"
    work_dir.mkdir(parents=True, exist_ok=False)
    profile_dir.mkdir(parents=True, exist_ok=True)
    runner = command_runner or subprocess.run

    if progress:
        progress({"message": "启动 LibreOffice 转换...", "stage": "native_convert"})

    command = [
        str(soffice),
        "--headless",
        "--nologo",
        "--nofirststartwizard",
        "--norestore",
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(work_dir.resolve()),
        str(source.resolve()),
    ]

    try:
        result = runner(
            command,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        generated_pdf = work_dir / f"{source.stem}.pdf"
        if result.returncode != 0:
            raise NativeConversionError(_conversion_error_message(result))
        if not generated_pdf.exists():
            raise NativeConversionError(_conversion_error_message(result, "LibreOffice did not create a PDF file."))
        if generated_pdf.stat().st_size == 0:
            raise NativeConversionError(_conversion_error_message(result, "LibreOffice created an empty PDF file."))

        final_pdf = output / output_name
        generated_pdf.replace(final_pdf)
        return final_pdf
    except subprocess.TimeoutExpired as exc:
        raise NativeConversionError(f"LibreOffice conversion timed out after {timeout_seconds} seconds.") from exc
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def find_soffice(
    *,
    soffice_path: str | Path | None = None,
    search_paths: Sequence[str | Path] | None = None,
) -> Path | None:
    global _cached_soffice_path
    if soffice_path is not None:
        explicit = Path(soffice_path)
        if explicit.exists():
            _cached_soffice_path = explicit
            return explicit
        raise NativeConversionError(f"Configured LibreOffice soffice path does not exist: {explicit}")

    if _cached_soffice_path is not None and _cached_soffice_path.exists():
        return _cached_soffice_path

    candidates: list[str | Path] = []
    if search_paths is None:
        for executable_name in ("soffice", "libreoffice"):
            found = shutil.which(executable_name)
            if found:
                candidates.append(found)
        candidates.extend(DEFAULT_WINDOWS_SOFFICE_PATHS)
    else:
        candidates.extend(search_paths)

    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            _cached_soffice_path = path
            return path
    return None


def _conversion_error_message(
    result: subprocess.CompletedProcess[str],
    prefix: str = "LibreOffice conversion failed.",
) -> str:
    details = "\n".join(
        part.strip()
        for part in (prefix, result.stdout or "", result.stderr or "")
        if part and part.strip()
    )
    return details or prefix
