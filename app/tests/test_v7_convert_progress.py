import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "app" / "backend"
sys.path.insert(0, str(BACKEND_DIR))


class ConvertProgressBackendTest(unittest.TestCase):
    def test_job_store_tracks_running_progress_and_done_result(self):
        from server import ConvertJobStore

        store = ConvertJobStore()
        store.create("job123", message="等待上传")
        store.update("job123", percent=45, message="生成分析和导读计划", stage="analysis", next_percent=58)

        running = store.snapshot("job123")
        self.assertEqual(running["status"], "running")
        self.assertEqual(running["percent"], 45)
        self.assertEqual(running["message"], "生成分析和导读计划")
        self.assertEqual(running["stage"], "analysis")
        self.assertEqual(running["next_percent"], 58)

        store.finish("job123", {"status": "ok", "job_id": "job123"})
        done = store.snapshot("job123")
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["percent"], 100)
        self.assertEqual(done["message"], "转换完成")
        self.assertEqual(done["result"]["job_id"], "job123")

    def test_converter_emits_ordered_coarse_progress_events(self):
        import converter

        originals = {}

        def replace(name, value):
            originals[name] = getattr(converter, name)
            setattr(converter, name, value)

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            pptx_path = tmp / "deck.pptx"
            pptx_path.write_bytes(b"pptx")
            events = []

            replace("parse_pptx", lambda path: {"presentation": "fake"})
            replace(
                "build_study_document",
                lambda presentation: {"source": {"name": "deck.pptx", "slide_count": 1}, "slides": []},
            )
            replace("analyze_presentation", lambda presentation: {"slides": []})
            replace("build_augment_plan", lambda analysis: {"slides": []})
            replace("process_presentation_media", lambda path, presentation, output: {"items": []})
            replace("build_knowledge_blocks", lambda presentation, analysis, plan, media: {"slides": []})
            replace(
                "write_knowledge_blocks",
                lambda path, blocks: Path(path).write_text('{"slides":[]}', encoding="utf-8"),
            )
            replace("write_study_html", lambda document, path: Path(path).write_text("<html></html>", encoding="utf-8"))
            replace("build_metrics", lambda *args, **kwargs: {"runtime_seconds": 0})
            replace("write_metrics", lambda path, metrics: Path(path).write_text("{}", encoding="utf-8"))
            replace("_build_reflow_intent_check", lambda plan: {"passed": True})
            replace("_build_render_visual_check", lambda *args, **kwargs: {"passed": True})
            replace("summarize_analysis", lambda analysis: {"slide_count": 1})

            try:
                converter.convert_pptx(
                    pptx_path,
                    tmp / "out",
                    render_pdf=False,
                    progress=lambda event: events.append(event),
                )
            finally:
                for name, value in originals.items():
                    setattr(converter, name, value)

        stages = [event["stage"] for event in events]
        percents = [event["percent"] for event in events]
        self.assertIn("parse", stages)
        self.assertIn("analysis", stages)
        self.assertIn("plan", stages)
        self.assertIn("report", stages)
        self.assertEqual(percents, sorted(percents))
        self.assertGreaterEqual(percents[-1], 95)


class ConvertProgressFrontendTest(unittest.TestCase):
    def test_frontend_polls_status_until_done_and_loads_result(self):
        script = textwrap.dedent(
            f"""
            const fs = require("fs");
            const vm = require("vm");
            const code = fs.readFileSync({str(ROOT_DIR / "app" / "frontend" / "app.js")!r}, "utf8");

            class FakeElement {{
              constructor(tag = "div") {{
                this.tagName = tag.toUpperCase();
                this.children = [];
                this.dataset = {{}};
                this.style = {{}};
                this.className = "";
                this.classList = {{ toggle() {{}}, add() {{}}, remove() {{}} }};
                this.value = "";
                this.files = [];
                this.disabled = false;
                this.hidden = false;
                this.href = "";
                this.textContent = "";
                this.innerHTML = "";
                this.attributes = {{}};
              }}
              appendChild(child) {{ this.children.push(child); return child; }}
              append(...children) {{ this.children.push(...children); }}
              addEventListener() {{}}
              removeAttribute(name) {{ delete this[name]; }}
              setAttribute(name, value) {{ this.attributes[name] = value; }}
              getAttribute(name) {{ return this.attributes[name]; }}
              focus() {{}}
              querySelector() {{ return new FakeElement(); }}
              scrollIntoView() {{}}
            }}
            class HTMLInputElement extends FakeElement {{}}
            class HTMLButtonElement extends FakeElement {{}}

            const selectors = [
              "#uploadForm", "#deckInput", "#convertButton", ".status-block", "#statusProgressBar",
              "#statusProgressFill", "#statusProgressText", "#statusProgressPercent", "#warningList",
              "#previewFrame", "#resultTitle", "#downloadLinks", "#debugLinks", "#blockList",
              "#selectedSummary", "#aiOutput", "#apiKeyInput", "#baseUrlInput", "#modelInput",
              "#composeButton", "#promptProfileSelect", "#includeImagesInput", "#exportAIButton",
              "#clearApiKeyButton", "#reader", "#pageTabs", "#guidePageStage", "#explanationPanel",
              "#sendPageButton", "#readerHint"
            ];
            const elements = new Map(selectors.map((selector) => [selector, new FakeElement()]));
            elements.set("#deckInput", new HTMLInputElement("input"));
            elements.set("#apiKeyInput", new HTMLInputElement("input"));
            elements.set("#includeImagesInput", new HTMLInputElement("input"));
            elements.set("#convertButton", new HTMLButtonElement("button"));
            elements.set("#composeButton", new HTMLButtonElement("button"));
            elements.set("#exportAIButton", new HTMLButtonElement("button"));
            elements.set("#clearApiKeyButton", new HTMLButtonElement("button"));
            elements.set("#sendPageButton", new HTMLButtonElement("button"));

            const document = {{
              querySelector(selector) {{ return elements.get(selector) || null; }},
              querySelectorAll() {{ return []; }},
              createElement(tag) {{
                if (tag === "input") return new HTMLInputElement(tag);
                if (tag === "button") return new HTMLButtonElement(tag);
                return new FakeElement(tag);
              }},
              addEventListener() {{}},
              dispatchEvent() {{}}
            }};

            const calls = [];
            const responses = [
              {{ status: "running", percent: 45, next_percent: 58, message: "生成分析和导读计划" }},
              {{
                status: "done",
                percent: 100,
                message: "转换完成",
                result: {{
                  status: "ok",
                  job_id: "job123",
                  warnings: [],
                  base_pdf_url: "/outputs/job123/base.pdf",
                  guide_pdf_url: "/outputs/job123/guide.pdf",
                  compare_url: "/outputs/job123/compare.html"
                }}
              }}
            ];
            const context = {{
              document,
              window: {{ setTimeout, clearTimeout, setInterval, clearInterval }},
              HTMLInputElement,
              HTMLButtonElement,
              FormData: class FormData {{}},
              fetch: async (url) => {{
                calls.push(String(url));
                return {{ ok: true, json: async () => responses.shift() }};
              }},
              console,
              URL,
              setTimeout,
              clearTimeout,
              setInterval,
              clearInterval,
              CustomEvent: function CustomEvent(name, options) {{ return {{ name, ...options }}; }}
            }};
            vm.createContext(context);
            vm.runInContext(
              code + "\\nglobalThis.__poll = pollConvertStatus; globalThis.__state = () => ({{ currentJobId, currentResult }});",
              context
            );

            (async () => {{
              const result = await context.__poll("job123", 0);
              if (calls.join("|") !== "/api/convert-status?job_id=job123|/api/convert-status?job_id=job123") {{
                throw new Error(calls.join("|"));
              }}
              if (result.job_id !== "job123") throw new Error("missing final result");
              if (elements.get("#statusProgressPercent").textContent !== "100%") {{
                throw new Error("percent=" + elements.get("#statusProgressPercent").textContent);
              }}
              if (context.__state().currentJobId !== "job123") throw new Error("job id not stored");
              if (!context.__state().currentResult.guide_pdf_url) throw new Error("result not stored");
            }})().catch((error) => {{
              console.error(error.stack || error.message);
              process.exit(1);
            }});
            """
        )
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as file:
            file.write(script)
            script_path = file.name
        try:
            result = subprocess.run(
                ["node", script_path],
                cwd=ROOT_DIR,
                text=True,
                capture_output=True,
                timeout=30,
            )
        finally:
            Path(script_path).unlink(missing_ok=True)

        self.assertEqual(result.returncode, 0, result.stderr)
