from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path


WINDOWS_BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def render_pdf_from_html(html_path: str | Path, pdf_path: str | Path) -> Path:
    html_file = Path(html_path).resolve()
    pdf_file = Path(pdf_path).resolve()
    pdf_file.parent.mkdir(parents=True, exist_ok=True)

    browser = find_browser()
    profile_dir = pdf_file.parent / f"browser_profile_{uuid.uuid4().hex}"
    profile_dir.mkdir(parents=True, exist_ok=False)
    try:
        command = [
            str(browser),
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            f"--user-data-dir={profile_dir}",
            f"--print-to-pdf={pdf_file}",
            html_file.as_uri(),
        ]
        subprocess.run(command, check=True, timeout=60)
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)

    if not pdf_file.exists() or pdf_file.stat().st_size == 0:
        raise RuntimeError("Browser did not produce a PDF file.")
    return pdf_file


def find_browser() -> Path:
    env_path = os.environ.get("SLIDE2STUDY_CHROME")
    candidates = [env_path] if env_path else []
    candidates.extend(WINDOWS_BROWSER_CANDIDATES)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise RuntimeError("No supported Chromium or Edge executable was found.")
