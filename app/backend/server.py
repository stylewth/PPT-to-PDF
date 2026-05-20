from __future__ import annotations

import json
import mimetypes
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from converter import convert_pptx


APP_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = APP_ROOT / "frontend"
WORKSPACE_DIR = APP_ROOT / "workspace"
UPLOADS_DIR = WORKSPACE_DIR / "uploads"
OUTPUTS_DIR = WORKSPACE_DIR / "outputs"


def extract_uploaded_file(content_type: str, body: bytes) -> dict[str, Any]:
    match = re.search(r"boundary=\"?([^\";]+)\"?", content_type)
    if not match:
        raise ValueError("Missing multipart boundary.")

    boundary = match.group(1).encode("utf-8")
    delimiter = b"--" + boundary
    for raw_part in body.split(delimiter):
        part = raw_part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].rstrip(b"\r\n")
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, content = part.split(b"\r\n\r\n", 1)
        headers = raw_headers.decode("utf-8", errors="replace")
        if 'name="deck"' not in headers:
            continue
        filename_match = re.search(r'filename="([^"]+)"', headers)
        if not filename_match:
            raise ValueError("Missing filename.")
        if content.endswith(b"\r\n"):
            content = content[:-2]
        return {
            "filename": _safe_filename(filename_match.group(1)),
            "content": content,
        }
    raise ValueError("No deck file part found.")


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), Slide2StudyHandler)
    _safe_log(f"Slide2Study V3D running at http://{host}:{port}")
    server.serve_forever()


class Slide2StudyHandler(BaseHTTPRequestHandler):
    server_version = "Slide2StudyV3G/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"status": "ok"})
            return
        if parsed.path.startswith("/outputs/"):
            self._serve_file(OUTPUTS_DIR / unquote(parsed.path.removeprefix("/outputs/")))
            return
        relative = "index.html" if parsed.path in {"/", ""} else parsed.path.lstrip("/")
        self._serve_file(FRONTEND_DIR / unquote(relative))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/convert":
            self._send_json({"error": "not_found"}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            upload = extract_uploaded_file(self.headers.get("Content-Type", ""), self.rfile.read(length))
            if not upload["filename"].lower().endswith(".pptx"):
                raise ValueError("Only .pptx files are supported.")

            job_id = uuid.uuid4().hex
            upload_dir = UPLOADS_DIR / job_id
            output_dir = OUTPUTS_DIR / job_id
            upload_dir.mkdir(parents=True, exist_ok=False)
            output_dir.mkdir(parents=True, exist_ok=False)
            deck_path = upload_dir / upload["filename"]
            deck_path.write_bytes(upload["content"])

            result = convert_pptx(deck_path, output_dir, render_pdf=True)
            self._send_json(build_convert_response(job_id, result))
        except Exception as exc:
            self._send_json({"status": "error", "error": str(exc)}, status=500)

    def log_message(self, format: str, *args: Any) -> None:
        _safe_log(f"{self.address_string()} - {format % args}")

    def _serve_file(self, path: Path) -> None:
        root = FRONTEND_DIR if not str(path).startswith(str(OUTPUTS_DIR)) else OUTPUTS_DIR
        try:
            resolved = path.resolve()
            resolved.relative_to(root.resolve())
        except ValueError:
            self._send_json({"error": "forbidden"}, status=403)
            return
        if not resolved.exists() or not resolved.is_file():
            self._send_json({"error": "not_found"}, status=404)
            return
        mime_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        data = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8" if mime_type.startswith("text/") else mime_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    return re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", name)


def build_convert_response(job_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        "job_id": job_id,
        "source": result["source"],
        "warnings": result["warnings"],
        "base_pdf_url": f"/outputs/{job_id}/base.pdf" if result.get("base_pdf_path") else None,
        "guide_pdf_url": f"/outputs/{job_id}/guide.pdf" if result.get("guide_pdf_path") else None,
        "compare_url": f"/outputs/{job_id}/compare.html" if result.get("compare_html_path") else None,
        "analysis_url": f"/outputs/{job_id}/analysis.json",
        "augment_plan_url": f"/outputs/{job_id}/augment_plan.json",
        "metrics_url": f"/outputs/{job_id}/metrics.json",
        "media_manifest_url": f"/outputs/{job_id}/media_manifest.json" if result.get("media_manifest_path") else None,
        "report_url": f"/outputs/{job_id}/report.json",
        "preview_url": f"/outputs/{job_id}/preview.html",
    }


def _safe_log(message: str) -> None:
    try:
        print(message, flush=True)
    except OSError:
        pass


if __name__ == "__main__":
    run_server()
