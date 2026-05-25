from __future__ import annotations

import json
import mimetypes
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from ai_pdf_exporter import export_ai_guide_pdf
from ai_explainer import DEFAULT_MODEL, explain_blocks, explain_page
from ai_visuals import build_block_visual_inputs, build_page_visual_inputs
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
        try:
            if parsed.path in {"/api/ai/explain", "/api/ai/compose", "/api/ai/explain-page"}:
                if parsed.path.endswith("/compose"):
                    self._handle_ai_request("compose")
                elif parsed.path.endswith("/explain-page"):
                    self._handle_ai_page_request()
                else:
                    self._handle_ai_request("explain")
                return
            if parsed.path == "/api/ai/export-guide":
                self._handle_ai_export_guide()
                return
            if parsed.path != "/api/convert":
                self._send_json({"error": "not_found"}, status=404)
                return
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
        except ValueError as exc:
            self._send_json({"status": "error", "error": str(exc)}, status=400)
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

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("Missing JSON body.")
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON body.") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def _handle_ai_request(self, mode: str) -> None:
        payload = self._read_json()
        job_id = _safe_job_id(str(payload.get("job_id") or ""))
        block_ids = payload.get("block_ids") or []
        if isinstance(payload.get("block_id"), str):
            block_ids = [payload["block_id"]]
        if not isinstance(block_ids, list) or not all(isinstance(item, str) for item in block_ids):
            raise ValueError("block_ids must be a list of strings.")
        api_key = str(payload.get("api_key") or "").strip()
        model = str(payload.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        base_url = str(payload.get("base_url") or "").strip() or None
        output_dir = OUTPUTS_DIR / job_id
        result = explain_blocks_for_job(
            job_id,
            output_dir,
            block_ids,
            api_key=api_key,
            model=model,
            base_url=base_url,
            mode=mode,
            prompt_profile=str(payload.get("prompt_profile") or "study"),
            include_images=_truthy(payload.get("include_images")),
        )
        self._send_json(result)

    def _handle_ai_export_guide(self) -> None:
        payload = self._read_json()
        job_id = _safe_job_id(str(payload.get("job_id") or ""))
        explanations = payload.get("explanations") or []
        if not isinstance(explanations, list):
            raise ValueError("explanations must be a list.")
        response = export_ai_guide_for_job(job_id, OUTPUTS_DIR / job_id, explanations)
        self._send_json(response)

    def _handle_ai_page_request(self) -> None:
        payload = self._read_json()
        job_id = _safe_job_id(str(payload.get("job_id") or ""))
        page_number = int(payload.get("page_number") or 0)
        if page_number <= 0:
            raise ValueError("page_number is required.")
        api_key = str(payload.get("api_key") or "").strip()
        model = str(payload.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        base_url = str(payload.get("base_url") or "").strip() or None
        output_dir = OUTPUTS_DIR / job_id
        result = explain_page_for_job(
            job_id,
            output_dir,
            page_number,
            api_key=api_key,
            model=model,
            base_url=base_url,
            prompt_profile=str(payload.get("prompt_profile") or "study"),
            include_images=_truthy(payload.get("include_images")),
        )
        self._send_json(result)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    return re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", name)


def _safe_job_id(job_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id):
        raise ValueError("Invalid job id.")
    return job_id


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def build_convert_response(job_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        "job_id": job_id,
        "source": result["source"],
        "warnings": result["warnings"],
        "base_pdf_url": f"/outputs/{job_id}/base.pdf" if result.get("base_pdf_path") else None,
        "guide_pdf_url": f"/outputs/{job_id}/guide.pdf" if result.get("guide_pdf_path") else None,
        "guide_preview_manifest_url": (
            f"/outputs/{job_id}/guide_preview_manifest.json"
            if result.get("guide_preview_manifest_path")
            else None
        ),
        "compare_url": f"/outputs/{job_id}/compare.html" if result.get("compare_html_path") else None,
        "analysis_url": f"/outputs/{job_id}/analysis.json",
        "augment_plan_url": f"/outputs/{job_id}/augment_plan.json",
        "metrics_url": f"/outputs/{job_id}/metrics.json",
        "media_manifest_url": f"/outputs/{job_id}/media_manifest.json" if result.get("media_manifest_path") else None,
        "knowledge_blocks_url": f"/outputs/{job_id}/knowledge_blocks.json" if result.get("knowledge_blocks_path") else None,
        "report_url": f"/outputs/{job_id}/report.json",
        "preview_url": f"/outputs/{job_id}/preview.html",
        "ai_guide_pdf_url": f"/outputs/{job_id}/ai_guide.pdf" if result.get("ai_guide_pdf_path") else None,
    }


def explain_blocks_for_job(
    job_id: str,
    output_dir: Path,
    block_ids: list[str],
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str | None = None,
    mode: str = "explain",
    prompt_profile: str = "study",
    include_images: bool = False,
    provider: Any | None = None,
) -> dict[str, Any]:
    _safe_job_id(job_id)
    knowledge_blocks = _read_job_knowledge(output_dir)
    visual_inputs = _block_visual_inputs_for_job(output_dir, knowledge_blocks, block_ids, include_images)
    return explain_blocks(
        knowledge_blocks,
        block_ids,
        api_key=api_key,
        model=model,
        base_url=base_url,
        mode=mode,
        provider=provider,
        cache_dir=output_dir / "ai_cache",
        prompt_profile=prompt_profile,
        visual_inputs=visual_inputs,
    )


def explain_page_for_job(
    job_id: str,
    output_dir: Path,
    page_number: int,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str | None = None,
    prompt_profile: str = "study",
    include_images: bool = False,
    provider: Any | None = None,
) -> dict[str, Any]:
    _safe_job_id(job_id)
    knowledge_blocks = _read_job_knowledge(output_dir)
    page = _find_slide(knowledge_blocks, page_number)
    if not page:
        raise ValueError("Knowledge blocks for this page were not found.")
    visual_inputs = build_page_visual_inputs(output_dir, page_number, include_images=include_images)
    return explain_page(
        page,
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider=provider,
        cache_dir=output_dir / "ai_cache",
        prompt_profile=prompt_profile,
        visual_inputs=visual_inputs,
    )


def _read_job_knowledge(output_dir: Path) -> dict[str, Any]:
    knowledge_path = output_dir / "knowledge_blocks.json"
    if not knowledge_path.exists():
        raise ValueError("Knowledge blocks for this job were not found.")
    return json.loads(knowledge_path.read_text(encoding="utf-8"))


def _block_visual_inputs_for_job(
    output_dir: Path,
    knowledge_blocks: dict[str, Any],
    block_ids: list[str],
    include_images: bool,
) -> list[dict[str, str]]:
    if not include_images:
        return []
    visuals: list[dict[str, str]] = []
    for block_id in block_ids:
        match = _find_block_with_slide(knowledge_blocks, block_id)
        if not match:
            raise ValueError(f"Knowledge block not found: {block_id}")
        slide_number, block = match
        visuals.extend(build_block_visual_inputs(output_dir, slide_number, block, include_images=True))
    return visuals


def _find_block_with_slide(knowledge_blocks: dict[str, Any], block_id: str) -> tuple[int, dict[str, Any]] | None:
    for slide in knowledge_blocks.get("slides", []) or []:
        slide_number = int(slide.get("number") or 0)
        for block in slide.get("blocks", []) or []:
            if str(block.get("id") or "") == block_id:
                return slide_number, block
    return None


def export_ai_guide_for_job(job_id: str, output_dir: Path, explanations: list[dict[str, Any]]) -> dict[str, Any]:
    safe_job_id = _safe_job_id(job_id)
    guide_path = output_dir / "guide.pdf"
    knowledge_path = output_dir / "knowledge_blocks.json"
    if not guide_path.exists():
        raise ValueError("Guide PDF for this job was not found.")
    if not knowledge_path.exists():
        raise ValueError("Knowledge blocks for this job were not found.")
    knowledge_blocks = json.loads(knowledge_path.read_text(encoding="utf-8"))
    ai_guide_path = export_ai_guide_pdf(guide_path, knowledge_blocks, explanations, output_dir)
    return {
        "status": "ok",
        "ai_guide_pdf": ai_guide_path.name,
        "ai_guide_pdf_url": f"/outputs/{safe_job_id}/ai_guide.pdf",
        "ai_guide_manifest_url": f"/outputs/{safe_job_id}/ai_guide_manifest.json",
    }


def _find_slide(knowledge_blocks: dict[str, Any], page_number: int) -> dict[str, Any] | None:
    for slide in knowledge_blocks.get("slides", []) or []:
        if int(slide.get("number") or 0) == page_number:
            return slide
    return None


def _safe_log(message: str) -> None:
    try:
        print(message, flush=True)
    except OSError:
        pass


if __name__ == "__main__":
    run_server()
