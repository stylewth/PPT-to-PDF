import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class V5FrontendReaderTest(unittest.TestCase):
    def test_reader_topbar_and_bbox_mapping(self):
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
              "#promptProfileSelect", "#includeImagesInput", "#exportAIButton", "#clearApiKeyButton", "#reader", "#pageTabs", "#guidePageStage",
              "#explanationPanel", "#sendPageButton", "#readerHint"
            ];
            const elements = new Map(selectors.map((selector) => [selector, new FakeElement()]));
            elements.set("#deckInput", new HTMLInputElement("input"));
            elements.set("#convertButton", new HTMLButtonElement("button"));
            elements.set("#composeButton", new HTMLButtonElement("button"));
            elements.set("#promptProfileSelect", new FakeElement("select"));
            elements.set("#includeImagesInput", new HTMLInputElement("input"));
            elements.set("#exportAIButton", new HTMLButtonElement("button"));
            elements.set("#clearApiKeyButton", new HTMLButtonElement("button"));
            elements.set("#sendPageButton", new HTMLButtonElement("button"));

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
              fetch: async () => ({{ ok: true, json: async () => ({{}}) }}),
              console,
              URL
            }};

            vm.runInNewContext(
              code + "\\nglobalThis.__setDownloads = setDownloads; globalThis.__bboxToStyle = bboxToStyle; globalThis.__downloadLinks = downloadLinks;",
              context
            );
            context.__setDownloads({{
              base_pdf_url: "/base.pdf",
              guide_pdf_url: "/guide.pdf",
              compare_url: "/compare.html",
              ai_guide_pdf_url: null,
              analysis_url: "/analysis.json",
              metrics_url: "/metrics.json"
            }});

            const labels = context.__downloadLinks.children.map((child) => child.textContent);
            if (labels.join("|") !== "Base PDF|Guide PDF|对比页|AI 解释版") {{
              throw new Error(labels.join("|"));
            }}
            if (!context.__downloadLinks.children[3].className.includes("disabled")) {{
              throw new Error("AI guide link should be disabled");
            }}
            const style = context.__bboxToStyle({{ x: 0.1, y: 0.2, w: 0.3, h: 0.4 }});
            if (style.left !== "10%" || style.top !== "20%" || style.width !== "30%" || style.height !== "40%") {{
              throw new Error(JSON.stringify(style));
            }}
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

    def test_export_ai_button_posts_existing_explanations(self):
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
              "#promptProfileSelect", "#includeImagesInput", "#exportAIButton", "#clearApiKeyButton", "#reader", "#pageTabs", "#guidePageStage",
              "#explanationPanel", "#sendPageButton", "#readerHint"
            ];
            const elements = new Map(selectors.map((selector) => [selector, new FakeElement()]));
            elements.set("#deckInput", new HTMLInputElement("input"));
            elements.set("#convertButton", new HTMLButtonElement("button"));
            elements.set("#composeButton", new HTMLButtonElement("button"));
            elements.set("#promptProfileSelect", new FakeElement("select"));
            elements.set("#includeImagesInput", new HTMLInputElement("input"));
            elements.set("#exportAIButton", new HTMLButtonElement("button"));
            elements.set("#clearApiKeyButton", new HTMLButtonElement("button"));
            elements.set("#sendPageButton", new HTMLButtonElement("button"));

            let postedBody = null;
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
              fetch: async (url, options) => {{
                if (url !== "/api/ai/export-guide") throw new Error(url);
                postedBody = JSON.parse(options.body);
                return {{
                  ok: true,
                  json: async () => ({{
                    status: "ok",
                    ai_guide_pdf_url: "/outputs/jobx/ai_guide.pdf",
                    ai_guide_manifest_url: "/outputs/jobx/ai_guide_manifest.json"
                  }})
                }};
              }},
              console,
              URL
            }};

            vm.runInNewContext(
              code + `
              currentJobId = "jobx";
              currentResult = {{ base_pdf_url: "/base.pdf", guide_pdf_url: "/guide.pdf", compare_url: "/compare.html" }};
              readerState.explanationsByBlockId.set("s1_b1", {{
                short_explanation: "Short",
                source_refs: [{{ kind: "slide_text", slide: 1, object_id: "shape1" }}]
              }});
              readerState.pageExplanationsByPage.set(1, {{
                short_explanation: "Whole page",
                source_refs: [{{ kind: "slide_text", slide: 1, object_id: "shape1" }}]
              }});
              globalThis.__exportAIGuidePdf = exportAIGuidePdf;
              globalThis.__downloadLinks = downloadLinks;
              `,
              context
            );
            (async () => {{
              await context.__exportAIGuidePdf();
              if (!postedBody || postedBody.job_id !== "jobx") throw new Error(JSON.stringify(postedBody));
              if (postedBody.api_key) throw new Error("API key leaked");
              if (postedBody.explanations.length !== 2 || postedBody.explanations[0].block_id !== "s1_b1" || postedBody.explanations[1].page_number !== 1) {{
                throw new Error(JSON.stringify(postedBody));
              }}
              const labels = context.__downloadLinks.children.map((child) => `${{child.textContent}}:${{child.className}}`);
              if (!labels.join("|").includes("AI 解释版:download-link")) {{
                throw new Error(labels.join("|"));
              }}
            }})().catch((error) => {{
              console.error(error.stack || error.message);
              process.exitCode = 1;
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

    def test_send_current_page_posts_one_whole_page_request_with_profile_and_images(self):
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
            elements.set("#deckInput", new HTMLInputElement("input"));
            elements.set("#apiKeyInput", new HTMLInputElement("input"));
            elements.set("#includeImagesInput", new HTMLInputElement("input"));
            elements.set("#convertButton", new HTMLButtonElement("button"));
            elements.set("#composeButton", new HTMLButtonElement("button"));
            elements.set("#exportAIButton", new HTMLButtonElement("button"));
            elements.set("#clearApiKeyButton", new HTMLButtonElement("button"));
            elements.set("#sendPageButton", new HTMLButtonElement("button"));

            let posts = [];
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
              posts,
              fetch: async (url, options = {{}}) => {{
                posts.push({{ url, body: options.body ? JSON.parse(options.body) : null }});
                return {{
                  ok: true,
                  json: async () => ({{
                    status: "ok",
                    mode: "whole_page",
                    explanation: {{
                      block_id: "page_1",
                      short_explanation: "整页解释",
                      detail: "整体说明",
                      source_refs: [{{ kind: "slide_text", slide: 1, object_id: "4" }}]
                    }}
                  }})
                }};
              }},
              console,
              URL
            }};

            vm.runInNewContext(
              code + `
              currentJobId = "jobx";
              apiKeyInput.value = "sk-test";
              promptProfileSelect.value = "training";
              includeImagesInput.checked = true;
              readerState.currentPage = 1;
              readerState.pages = [{{ number: 1, image_url: "/page.png" }}];
              readerState.slidesByPage.set(1, {{
                number: 1,
                mode: "blocks",
                blocks: [
                  {{ id: "s1_b1", title: "A", display_bbox: {{ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }}, source_refs: [] }},
                  {{ id: "s1_b2", title: "B", display_bbox: {{ x: 0.4, y: 0.4, w: 0.2, h: 0.2 }}, source_refs: [] }}
                ]
              }});
              globalThis.__sendCurrentPage = sendCurrentPage;
              globalThis.__posts = posts;
              `,
              context
            );
            (async () => {{
              await context.__sendCurrentPage();
              if (context.__posts.length !== 1) throw new Error(JSON.stringify(context.__posts));
              const post = context.__posts[0];
              if (post.url !== "/api/ai/explain-page") throw new Error(post.url);
              if (post.body.page_number !== 1 || post.body.prompt_profile !== "training" || post.body.include_images !== true) {{
                throw new Error(JSON.stringify(post.body));
              }}
              if (post.body.block_id || post.body.block_ids) throw new Error(JSON.stringify(post.body));
            }})().catch((error) => {{
              console.error(error.stack || error.message);
              process.exitCode = 1;
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

    def test_send_current_page_keeps_guide_visualization_visible(self):
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
                this._textContent = "";
                this._innerHTML = "";
              }}
              get textContent() {{ return this._textContent; }}
              set textContent(value) {{
                this._textContent = String(value);
                this.children = [];
                this._innerHTML = "";
              }}
              get innerHTML() {{ return this._innerHTML; }}
              set innerHTML(value) {{
                this._innerHTML = String(value);
                this.children = [];
                this._textContent = "";
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
            elements.set("#deckInput", new HTMLInputElement("input"));
            elements.set("#apiKeyInput", new HTMLInputElement("input"));
            elements.set("#includeImagesInput", new HTMLInputElement("input"));
            elements.set("#convertButton", new HTMLButtonElement("button"));
            elements.set("#composeButton", new HTMLButtonElement("button"));
            elements.set("#exportAIButton", new HTMLButtonElement("button"));
            elements.set("#clearApiKeyButton", new HTMLButtonElement("button"));
            elements.set("#sendPageButton", new HTMLButtonElement("button"));

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
              fetch: async () => ({{
                ok: true,
                json: async () => ({{
                  status: "ok",
                  mode: "whole_page",
                  prompt_profile: "training",
                  explanation: {{
                    block_id: "page_1",
                    short_explanation: "整页解释",
                    detail: "整体说明",
                    source_refs: [{{ kind: "slide_text", slide: 1, object_id: "4" }}]
                  }}
                }})
              }}),
              console,
              URL
            }};

            vm.runInNewContext(
              code + `
              currentJobId = "jobx";
              apiKeyInput.value = "sk-test";
              promptProfileSelect.value = "training";
              includeImagesInput.checked = true;
              readerState.currentPage = 1;
              readerState.pages = [{{ number: 1, image_url: "/page.png" }}];
              readerState.slidesByPage.set(1, {{
                number: 1,
                mode: "blocks",
                blocks: [
                  {{ id: "s1_b1", title: "A", display_bbox: {{ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }}, source_refs: [] }}
                ]
              }});
              renderReader();
              globalThis.__sendCurrentPage = sendCurrentPage;
              globalThis.__guidePageStage = guidePageStage;
              `,
              context
            );
            (async () => {{
              if (context.__guidePageStage.children.length !== 1) {{
                throw new Error("guide visualization did not render before request");
              }}
              await context.__sendCurrentPage();
              if (context.__guidePageStage.children.length !== 1) {{
                throw new Error("guide visualization disappeared");
              }}
            }})().catch((error) => {{
              console.error(error.stack || error.message);
              process.exitCode = 1;
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

    def test_role_sections_render_without_legacy_learning_labels(self):
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
              fetch: async () => ({{ ok: true, json: async () => ({{}}) }}),
              console,
              URL
            }};

            vm.runInNewContext(
              code + `
              const host = document.createElement("div");
              appendExplanationContent(host, {{
                short_explanation: "培训解释",
                detail: "培训细节",
                sections: [
                  {{ label: "操作步骤", items: ["第一步"] }},
                  {{ label: "风险提醒", items: ["注意边界"] }}
                ],
                source_refs: [{{ kind: "slide_text", slide: 1, object_id: "4" }}]
              }});
              globalThis.__texts = host.children.map((child) => child.textContent).join("|");
              `,
              context
            );
            if (!context.__texts.includes("操作步骤") || !context.__texts.includes("风险提醒")) {{
              throw new Error(context.__texts);
            }}
            if (context.__texts.includes("易错点") || context.__texts.includes("复习题")) {{
              throw new Error(context.__texts);
            }}
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
