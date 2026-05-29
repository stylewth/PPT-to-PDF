import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "app" / "backend"
sys.path.insert(0, str(BACKEND_DIR))


class V6PerformanceFlowTest(unittest.TestCase):
    def test_render_visual_check_empty_pages_does_not_render_whole_pdf(self):
        import fitz
        from render_visual_check import check_rendered_pdf

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            pdf_path = tmp / "sample.pdf"
            doc = fitz.open()
            doc.new_page(width=120, height=90)
            doc.new_page(width=120, height=90)
            doc.save(pdf_path)
            doc.close()

            result = check_rendered_pdf(
                pdf_path,
                pages=[],
                screenshot_dir=tmp / "screens",
            )

            self.assertTrue(result["passed"])
            self.assertEqual(result["pages"], [])
            self.assertEqual(list((tmp / "screens").glob("*.png")), [])

    def test_render_visual_check_can_reuse_existing_preview_images(self):
        from render_visual_check import check_rendered_preview_images

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            preview_dir = tmp / "guide_preview"
            preview_dir.mkdir()
            Image.new("RGB", (160, 90), "white").save(preview_dir / "page_001.png")
            manifest_path = tmp / "guide_preview_manifest.json"
            manifest_path.write_text(
                """
                {
                  "kind": "guide_preview",
                  "pages": [
                    {
                      "number": 1,
                      "image": "guide_preview/page_001.png",
                      "image_width": 160,
                      "image_height": 90
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            result = check_rendered_preview_images(
                manifest_path,
                pages=[1],
                formula_regions={1: []},
                screenshot_dir=tmp / "render_visual_check",
            )

            self.assertTrue(result["passed"])
            self.assertEqual(result["pages"][0]["page"], 1)
            self.assertTrue((tmp / "render_visual_check" / "page_01.png").exists())

            empty_result = check_rendered_preview_images(
                manifest_path,
                pages=[],
                screenshot_dir=tmp / "empty_render_visual_check",
            )
            self.assertTrue(empty_result["passed"])
            self.assertEqual(empty_result["pages"], [])
            self.assertEqual(list((tmp / "empty_render_visual_check").glob("*.png")), [])

    def test_converter_render_check_uses_preview_manifest_when_available(self):
        import converter

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            manifest_path = tmp / "guide_preview_manifest.json"
            manifest_path.write_text('{"pages":[]}', encoding="utf-8")
            calls = []

            original_preview = getattr(converter, "check_rendered_preview_images", None)
            original_pdf = converter.check_rendered_pdf

            def fake_preview(manifest, *, pages, formula_regions, screenshot_dir, scale=None):
                calls.append(
                    {
                        "manifest": Path(manifest).name,
                        "pages": pages,
                        "formula_pages": sorted(formula_regions),
                        "screenshot_dir": Path(screenshot_dir).name,
                        "scale": scale,
                    }
                )
                return {"passed": True, "warnings": [], "pages": [], "screenshot_dir": str(screenshot_dir)}

            def fail_pdf(*args, **kwargs):
                raise AssertionError("PDF should not be rendered again when preview images exist")

            converter.check_rendered_preview_images = fake_preview
            converter.check_rendered_pdf = fail_pdf
            try:
                plan = {
                    "slides": [
                        {
                            "source_slide": 1,
                            "size": {"width": 1000, "height": 1000},
                            "object_reflow": {
                                "operations": [
                                    {
                                        "id": "formula1",
                                        "object_type": "graphicFrame",
                                        "render_mode": "pdf_region_overlay",
                                        "op": "move",
                                        "from": {"x": 10, "y": 20, "w": 100, "h": 80},
                                        "to": {"x": 50, "y": 60, "w": 100, "h": 80},
                                    }
                                ]
                            },
                            "object_boxes": [
                                {
                                    "id": "formula1",
                                    "type": "graphicFrame",
                                    "bbox": {"x": 10, "y": 20, "w": 100, "h": 80},
                                }
                            ],
                        }
                    ]
                }

                result = converter._build_render_visual_check(
                    tmp / "guide.pdf",
                    tmp,
                    plan,
                    guide_preview_manifest_path=manifest_path,
                )
            finally:
                if original_preview is None:
                    delattr(converter, "check_rendered_preview_images")
                else:
                    converter.check_rendered_preview_images = original_preview
                converter.check_rendered_pdf = original_pdf

            self.assertTrue(result["passed"])
            self.assertEqual(calls[0]["manifest"], "guide_preview_manifest.json")
            self.assertEqual(calls[0]["pages"], [1])
            self.assertEqual(calls[0]["formula_pages"], [1])

    def test_frontend_ai_queue_runs_limited_parallel_requests(self):
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
                this.checked = false;
                this.files = [];
                this.disabled = false;
                this.hidden = false;
                this.href = "";
                this.textContent = "";
                this.innerHTML = "";
              }}
              appendChild(child) {{ this.children.push(child); return child; }}
              append(...children) {{ this.children.push(...children); }}
              addEventListener() {{}}
              removeAttribute(name) {{ delete this[name]; }}
              setAttribute(name, value) {{ this[name] = value; }}
              focus() {{}}
              querySelector() {{ return new FakeElement(); }}
              scrollIntoView() {{}}
            }}
            class HTMLInputElement extends FakeElement {{}}
            class HTMLButtonElement extends FakeElement {{}}

            const selectors = [
              "#uploadForm", "#deckInput", "#convertButton", "#warningList", "#previewFrame",
              "#resultTitle", "#downloadLinks", "#debugLinks", "#blockList", "#selectedSummary",
              "#aiOutput", "#apiKeyInput", "#baseUrlInput", "#modelInput", "#composeButton",
              "#promptProfileSelect", "#includeImagesInput", "#exportAIButton", "#clearApiKeyButton",
              "#reader", "#pageTabs", "#guidePageStage", "#explanationPanel", "#sendPageButton", "#readerHint"
            ];
            const elements = new Map(selectors.map((selector) => [selector, new FakeElement()]));
            elements.set("#apiKeyInput", new HTMLInputElement("input"));
            elements.set("#includeImagesInput", new HTMLInputElement("input"));
            elements.set("#promptProfileSelect", new FakeElement("select"));

            let active = 0;
            let maxActive = 0;
            let calls = 0;
            const document = {{
              querySelector(selector) {{ return elements.get(selector) || new FakeElement(); }},
              querySelectorAll() {{ return [new FakeElement("li"), new FakeElement("li")]; }},
              createElement(tag) {{
                if (tag === "input") return new HTMLInputElement(tag);
                if (tag === "button") return new HTMLButtonElement(tag);
                return new FakeElement(tag);
              }}
            }};
            const context = {{
              document,
              HTMLInputElement,
              HTMLButtonElement,
              FormData: class FormData {{}},
              fetch: async () => {{
                active += 1;
                calls += 1;
                maxActive = Math.max(maxActive, active);
                await new Promise((resolve) => setTimeout(resolve, 25));
                active -= 1;
                return {{
                  ok: true,
                  json: async () => ({{
                    status: "ok",
                    explanation: {{
                      short_explanation: "ok",
                      detail: "ok",
                      sections: [],
                      source_refs: []
                    }}
                  }})
                }};
              }},
              getCalls: () => calls,
              getMaxActive: () => maxActive,
              setTimeout,
              console,
              URL
            }};

            const promise = vm.runInNewContext(
              code + `
              currentJobId = "jobx";
              apiKeyInput.value = "sk-test";
              promptProfileSelect.value = "study";
              renderReader = () => {{}};
              renderAIResult = () => {{}};
              readerState.queue.push(
                {{ blockId: "s1_b1", wholePage: false, profile: "study" }},
                {{ blockId: "s1_b2", wholePage: false, profile: "study" }},
                {{ blockId: "s1_b3", wholePage: false, profile: "study" }}
              );
              (async () => {{
                await runExplanationQueue();
                if (getCalls() !== 3) throw new Error("calls=" + getCalls());
                if (getMaxActive() < 2) throw new Error("queue ran serially: " + getMaxActive());
              }})();
              `,
              context
            );
            promise.catch((error) => {{
              console.error(error && error.stack ? error.stack : error);
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

    def test_frontend_whole_page_explanation_uses_local_cache(self):
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
                this.checked = false;
                this.files = [];
                this.disabled = false;
                this.hidden = false;
                this.href = "";
                this.textContent = "";
                this.innerHTML = "";
              }}
              appendChild(child) {{ this.children.push(child); return child; }}
              append(...children) {{ this.children.push(...children); }}
              addEventListener() {{}}
              removeAttribute(name) {{ delete this[name]; }}
              setAttribute(name, value) {{ this[name] = value; }}
              focus() {{}}
              querySelector() {{ return new FakeElement(); }}
              scrollIntoView() {{}}
            }}
            class HTMLInputElement extends FakeElement {{}}
            class HTMLButtonElement extends FakeElement {{}}

            const selectors = [
              "#uploadForm", "#deckInput", "#convertButton", "#warningList", "#previewFrame",
              "#resultTitle", "#downloadLinks", "#debugLinks", "#blockList", "#selectedSummary",
              "#aiOutput", "#apiKeyInput", "#baseUrlInput", "#modelInput", "#composeButton",
              "#promptProfileSelect", "#includeImagesInput", "#exportAIButton", "#clearApiKeyButton",
              "#reader", "#pageTabs", "#guidePageStage", "#explanationPanel", "#sendPageButton", "#readerHint"
            ];
            const elements = new Map(selectors.map((selector) => [selector, new FakeElement()]));
            elements.set("#apiKeyInput", new HTMLInputElement("input"));
            elements.set("#promptProfileSelect", new FakeElement("select"));
            const document = {{
              querySelector(selector) {{ return elements.get(selector) || new FakeElement(); }},
              querySelectorAll() {{ return [new FakeElement("li"), new FakeElement("li")]; }},
              createElement(tag) {{
                if (tag === "input") return new HTMLInputElement(tag);
                if (tag === "button") return new HTMLButtonElement(tag);
                return new FakeElement(tag);
              }}
            }};
            let fetchCalls = 0;
            let rendered = "";
            const context = {{
              document,
              HTMLInputElement,
              HTMLButtonElement,
              FormData: class FormData {{}},
              fetch: async () => {{
                fetchCalls += 1;
                return {{ ok: true, json: async () => ({{ status: "ok", explanation: {{}} }}) }};
              }},
              setRendered: (value) => {{ rendered = value; }},
              getFetchCalls: () => fetchCalls,
              getRendered: () => rendered,
              console,
              URL
            }};

            const promise = vm.runInNewContext(
              code + `
              currentJobId = "jobx";
              apiKeyInput.value = "sk-test";
              promptProfileSelect.value = "study";
              renderReader = () => {{}};
              renderAIResult = (result) => {{ setRendered(result.explanation.short_explanation); }};
              readerState.pageExplanationsByProfileKey.set("1::study", {{
                short_explanation: "缓存整页解释",
                detail: "缓存整页解释",
                prompt_profile: "study",
                source_refs: []
              }});
              (async () => {{
                await explainWholePage(1, "study");
                if (getFetchCalls() !== 0) throw new Error("fetch calls=" + getFetchCalls());
                if (getRendered() !== "缓存整页解释") throw new Error(getRendered());
              }})();
              `,
              context
            );
            promise.catch((error) => {{
              console.error(error && error.stack ? error.stack : error);
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

    def test_frontend_reuses_pdf_edit_for_same_selection(self):
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
                this.checked = false;
                this.files = [];
                this.disabled = false;
                this.hidden = false;
                this.href = "";
                this.textContent = "";
                this.innerHTML = "";
              }}
              appendChild(child) {{ this.children.push(child); return child; }}
              append(...children) {{ this.children.push(...children); }}
              addEventListener() {{}}
              removeAttribute(name) {{ delete this[name]; }}
              setAttribute(name, value) {{ this[name] = value; }}
              focus() {{}}
              querySelector() {{ return new FakeElement(); }}
              scrollIntoView() {{}}
            }}
            class HTMLInputElement extends FakeElement {{}}
            class HTMLButtonElement extends FakeElement {{}}

            const selectors = [
              "#uploadForm", "#deckInput", "#convertButton", "#warningList", "#previewFrame",
              "#resultTitle", "#downloadLinks", "#debugLinks", "#blockList", "#selectedSummary",
              "#aiOutput", "#apiKeyInput", "#baseUrlInput", "#modelInput", "#composeButton",
              "#promptProfileSelect", "#includeImagesInput", "#exportAIButton", "#clearApiKeyButton",
              "#reader", "#pageTabs", "#guidePageStage", "#explanationPanel", "#sendPageButton", "#readerHint"
            ];
            const elements = new Map(selectors.map((selector) => [selector, new FakeElement()]));
            elements.set("#apiKeyInput", new HTMLInputElement("input"));
            elements.set("#baseUrlInput", new HTMLInputElement("input"));
            elements.set("#modelInput", new HTMLInputElement("input"));
            elements.set("#includeImagesInput", new HTMLInputElement("input"));
            elements.set("#promptProfileSelect", new FakeElement("select"));
            const document = {{
              querySelector(selector) {{ return elements.get(selector) || new FakeElement(); }},
              querySelectorAll() {{ return [new FakeElement("li"), new FakeElement("li")]; }},
              createElement(tag) {{
                if (tag === "input") return new HTMLInputElement(tag);
                if (tag === "button") return new HTMLButtonElement(tag);
                return new FakeElement(tag);
              }}
            }};
            let fetchCalls = 0;
            const context = {{
              document,
              HTMLInputElement,
              HTMLButtonElement,
              FormData: class FormData {{}},
              fetch: async (url) => {{
                fetchCalls += 1;
                if (url !== "/api/ai/edit-pdf") throw new Error(url);
                return {{
                  ok: true,
                  json: async () => ({{
                    status: "ok",
                    export_explanations: [
                      {{
                        block_id: "s1_b1",
                        include_in_pdf: true,
                        explanation: {{
                          pdf_snippet: "短稿",
                          source_refs: [{{ kind: "slide_text", slide: 1, object_id: "shape1" }}]
                        }}
                      }}
                    ]
                  }})
                }};
              }},
              getFetchCalls: () => fetchCalls,
              console,
              URL
            }};

            const promise = vm.runInNewContext(
              code + `
              currentJobId = "jobx";
              apiKeyInput.value = "sk-test";
              modelInput.value = "gpt-4.1-mini";
              promptProfileSelect.value = "study";
              const explanations = [
                {{
                  block_id: "s1_b1",
                  explanation: {{
                    short_explanation: "原解释",
                    detail: "原解释详情",
                    sections: [],
                    source_refs: [{{ kind: "slide_text", slide: 1, object_id: "shape1" }}]
                  }}
                }}
              ];
              (async () => {{
                await editExplanationsForPdf(explanations);
                await editExplanationsForPdf(explanations);
                if (getFetchCalls() !== 1) throw new Error("fetch calls=" + getFetchCalls());
              }})();
              `,
              context
            );
            promise.catch((error) => {{
              console.error(error && error.stack ? error.stack : error);
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

    def test_frontend_retry_after_ai_error_requeues_block(self):
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
                this.checked = false;
                this.files = [];
                this.disabled = false;
                this.hidden = false;
                this.href = "";
                this.textContent = "";
                this.innerHTML = "";
              }}
              appendChild(child) {{ this.children.push(child); return child; }}
              append(...children) {{ this.children.push(...children); }}
              addEventListener() {{}}
              removeAttribute(name) {{ delete this[name]; }}
              setAttribute(name, value) {{ this[name] = value; }}
              focus() {{}}
              querySelector() {{ return new FakeElement(); }}
              scrollIntoView() {{}}
            }}
            class HTMLInputElement extends FakeElement {{}}
            class HTMLButtonElement extends FakeElement {{}}

            const selectors = [
              "#uploadForm", "#deckInput", "#convertButton", "#warningList", "#previewFrame",
              "#resultTitle", "#downloadLinks", "#debugLinks", "#blockList", "#selectedSummary",
              "#aiOutput", "#apiKeyInput", "#baseUrlInput", "#modelInput", "#composeButton",
              "#promptProfileSelect", "#includeImagesInput", "#exportAIButton", "#clearApiKeyButton",
              "#reader", "#pageTabs", "#guidePageStage", "#explanationPanel", "#sendPageButton", "#readerHint"
            ];
            const elements = new Map(selectors.map((selector) => [selector, new FakeElement()]));
            elements.set("#apiKeyInput", new HTMLInputElement("input"));
            elements.set("#includeImagesInput", new HTMLInputElement("input"));
            elements.set("#promptProfileSelect", new FakeElement("select"));
            const document = {{
              querySelector(selector) {{ return elements.get(selector) || new FakeElement(); }},
              querySelectorAll() {{ return [new FakeElement("li"), new FakeElement("li")]; }},
              createElement(tag) {{
                if (tag === "input") return new HTMLInputElement(tag);
                if (tag === "button") return new HTMLButtonElement(tag);
                return new FakeElement(tag);
              }}
            }};
            let fetchCalls = 0;
            const context = {{
              document,
              HTMLInputElement,
              HTMLButtonElement,
              FormData: class FormData {{}},
              fetch: async () => {{
                fetchCalls += 1;
                return {{
                  ok: true,
                  json: async () => ({{
                    status: "ok",
                    explanation: {{
                      short_explanation: "重试成功",
                      detail: "重试成功",
                      sections: [],
                      source_refs: []
                    }}
                  }})
                }};
              }},
              getFetchCalls: () => fetchCalls,
              setTimeout,
              console,
              URL
            }};

            const promise = vm.runInNewContext(
              code + `
              currentJobId = "jobx";
              apiKeyInput.value = "sk-test";
              promptProfileSelect.value = "study";
              renderReader = () => {{}};
              renderAIResult = () => {{}};
              const key = profileKey("s1_b1", "study");
              readerState.queueStatusByBlockId.set(key, "error");
              readerState.errorsByBlockId.set(key, "模型返回错误");
              (async () => {{
                enqueueBlockExplanation("s1_b1", "study");
                await new Promise((resolve) => setTimeout(resolve, 20));
                if (getFetchCalls() !== 1) throw new Error("retry did not call AI");
                if (readerState.queueStatusByBlockId.has(key)) throw new Error("retry status not cleared");
                if (readerState.errorsByBlockId.has(key)) throw new Error("old error not cleared");
              }})();
              `,
              context
            );
            promise.catch((error) => {{
              console.error(error && error.stack ? error.stack : error);
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


if __name__ == "__main__":
    unittest.main()
