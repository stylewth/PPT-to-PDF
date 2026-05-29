import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class V5FrontendReaderTest(unittest.TestCase):
    def test_frontend_no_longer_shows_problem_report_panel(self):
        html = (ROOT_DIR / "app" / "frontend" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("问题报告", html)
        self.assertNotIn('id="warningList"', html)

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

    def test_export_collects_only_selected_block_explanations(self):
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
            elements.set("#exportAIButton", new HTMLButtonElement("button"));
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
              promptProfileSelect.value = "study";
              readerState.selectedBlockIds.add("s1_b2");
              readerState.explanationsByBlockId.set("s1_b1", {{
                short_explanation: "未选中解释",
                source_refs: []
              }});
              readerState.explanationsByBlockId.set("s1_b2", {{
                short_explanation: "已选中解释",
                source_refs: []
              }});
              readerState.pageExplanationsByPage.set(1, {{
                short_explanation: "整页解释不应进入选块导出",
                source_refs: []
              }});
              const exported = collectExportExplanations();
              if (exported.length !== 1 || exported[0].block_id !== "s1_b2") {{
                throw new Error(JSON.stringify(exported));
              }}
              `,
              context
            );
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

    def test_right_panel_can_select_block_and_selection_scrolls_to_card(self):
        script = textwrap.dedent(
            f"""
            const fs = require("fs");
            const vm = require("vm");
            const code = fs.readFileSync({str(ROOT_DIR / "app" / "frontend" / "app.js")!r}, "utf8");

            let scrollCalls = 0;
            const scrollTarget = {{ scrollIntoView() {{ scrollCalls += 1; }} }};

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
              querySelector(selector) {{
                if (selector === `[data-focus-block="s1_b1"]`) return scrollTarget;
                return new FakeElement();
              }}
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
              scrollCalls: () => scrollCalls,
              console,
              URL
            }};

            vm.runInNewContext(
              code + `
              promptProfileSelect.value = "study";
              readerState.currentPage = 1;
              readerState.pages = [{{ number: 1, image_url: "/page1.png" }}];
              readerState.slidesByPage.set(1, {{
                number: 1,
                blocks: [
                  {{ id: "s1_b1", title: "块 1", summary: "摘要", display_bbox: {{ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }}, source_refs: [] }}
                ]
              }});
              renderExplanationPanel({{ number: 1 }});
              function collectPanelSelectors(node, acc = []) {{
                if (node.dataset && node.dataset.panelSelectBlock) acc.push(node.dataset.panelSelectBlock);
                (node.children || []).forEach((child) => collectPanelSelectors(child, acc));
                return acc;
              }}
              const selectors = collectPanelSelectors(explanationPanel);
              if (selectors.join("|") !== "s1_b1") throw new Error(selectors.join("|"));
              toggleBlockSelection("s1_b1");
              if (scrollCalls() !== 1) throw new Error(String(scrollCalls()));
              `,
              context
            );
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

    def test_export_keeps_selected_explanations_when_pdf_editor_drops_them(self):
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
            elements.set("#exportAIButton", new HTMLButtonElement("button"));
            const posts = [];
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
              fetch: async (url, options) => {{
                posts.push({{ url, body: JSON.parse(options.body) }});
                if (url === "/api/ai/edit-pdf") {{
                  return {{
                    ok: true,
                    json: async () => ({{
                      status: "ok",
                      export_explanations: [
                        {{
                          block_id: "s1_b1",
                          include_in_pdf: false,
                          explanation: {{
                            short_explanation: "",
                            source_refs: [{{ kind: "slide_text", slide: 1, object_id: "shape1" }}]
                          }}
                        }}
                      ]
                    }})
                  }};
                }}
                if (url === "/api/ai/export-guide") {{
                  return {{
                    ok: true,
                    json: async () => ({{
                      status: "ok",
                      ai_guide_pdf_url: "/outputs/jobx/ai_guide.pdf",
                      ai_guide_manifest_url: "/outputs/jobx/ai_guide_manifest.json"
                    }})
                  }};
                }}
                throw new Error("unexpected call: " + url);
              }},
              console,
              URL
            }};

            vm.runInNewContext(
              code + `
              currentJobId = "jobx";
              apiKeyInput.value = "sk-test";
              promptProfileSelect.value = "study";
              readerState.selectedBlockIds.add("s1_b1");
              readerState.explanationsByBlockId.set("s1_b1", {{
                short_explanation: "完整讲解",
                source_refs: [{{ kind: "slide_text", slide: 1, object_id: "shape1" }}]
              }});
              globalThis.__exportAIGuidePdf = exportAIGuidePdf;
              globalThis.__posts = posts;
              `,
              context
            );
            (async () => {{
              await context.__exportAIGuidePdf();
              if (context.__posts.length !== 2) throw new Error(JSON.stringify(context.__posts));
              if (context.__posts[0].url !== "/api/ai/edit-pdf") throw new Error(context.__posts[0].url);
              if (context.__posts[1].url !== "/api/ai/export-guide") throw new Error(context.__posts[1].url);
              const exported = context.__posts[1].body.explanations;
              if (exported.length !== 1 || exported[0].block_id !== "s1_b1") {{
                throw new Error(JSON.stringify(exported));
              }}
              if (exported[0].include_in_pdf !== true) {{
                throw new Error(JSON.stringify(exported[0]));
              }}
              if (exported[0].explanation.short_explanation !== "完整讲解") {{
                throw new Error(JSON.stringify(exported[0]));
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

    def test_export_ai_button_requires_api_key_for_pdf_editor(self):
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

            let fetchCalled = false;
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
                fetchCalled = true;
                throw new Error(url);
              }},
              console,
              URL
            }};

            vm.runInNewContext(
              code + `
              currentJobId = "jobx";
              currentResult = {{ base_pdf_url: "/base.pdf", guide_pdf_url: "/guide.pdf", compare_url: "/compare.html" }};
              readerState.selectedBlockIds.add("s1_b1");
              readerState.explanationsByBlockId.set("s1_b1", {{
                short_explanation: "Short",
                source_refs: [{{ kind: "slide_text", slide: 1, object_id: "shape1" }}]
              }});
              readerState.pageExplanationsByPage.set(1, {{
                short_explanation: "Whole page",
                source_refs: [{{ kind: "slide_text", slide: 1, object_id: "shape1" }}]
              }});
              globalThis.__exportAIGuidePdf = exportAIGuidePdf;
              `,
              context
            );
            (async () => {{
              try {{
                await context.__exportAIGuidePdf();
              }} catch (error) {{
                if (!error.message.includes("请先填写 API Key")) throw error;
                if (fetchCalled) throw new Error("fetch should not be called without API key");
                return;
              }}
              throw new Error("expected API key error");
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

    def test_export_ai_button_asks_agent_to_edit_before_export(self):
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
              "#promptProfileSelect", "#includeImagesInput", "#exportAIButton", "#clearApiKeyButton",
              "#reader", "#pageTabs", "#guidePageStage", "#explanationPanel", "#sendPageButton", "#readerHint"
            ];
            const elements = new Map(selectors.map((selector) => [selector, new FakeElement()]));
            elements.set("#deckInput", new HTMLInputElement("input"));
            elements.set("#apiKeyInput", new HTMLInputElement("input"));
            elements.set("#convertButton", new HTMLButtonElement("button"));
            elements.set("#composeButton", new HTMLButtonElement("button"));
            elements.set("#exportAIButton", new HTMLButtonElement("button"));
            elements.set("#clearApiKeyButton", new HTMLButtonElement("button"));
            elements.set("#sendPageButton", new HTMLButtonElement("button"));

            const posts = [];
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
              fetch: async (url, options) => {{
                posts.push({{ url, body: JSON.parse(options.body) }});
                if (url === "/api/ai/edit-pdf") {{
                  return {{
                    ok: true,
                    json: async () => ({{
                      status: "ok",
                      decisions: [
                        {{
                          block_id: "s1_b1",
                          include_in_pdf: true,
                          pdf_snippet: "短补充",
                          importance_reason: "不要展示",
                          layout_intent: "extension_panel"
                        }}
                      ],
                      export_explanations: [
                        {{
                          block_id: "s1_b1",
                          include_in_pdf: true,
                          explanation: {{
                            short_explanation: "短补充",
                            pdf_snippet: "短补充",
                            source_refs: [{{ kind: "slide_text", slide: 1, object_id: "shape1" }}]
                          }}
                        }}
                      ]
                    }})
                  }};
                }}
                if (url === "/api/ai/export-guide") {{
                  return {{
                    ok: true,
                    json: async () => ({{
                      status: "ok",
                      ai_guide_pdf_url: "/outputs/jobx/ai_guide.pdf",
                      ai_guide_manifest_url: "/outputs/jobx/ai_guide_manifest.json"
                    }})
                  }};
                }}
                throw new Error(url);
              }},
              console,
              URL
            }};

            vm.runInNewContext(
              code + `
              currentJobId = "jobx";
              currentResult = {{ base_pdf_url: "/base.pdf", guide_pdf_url: "/guide.pdf", compare_url: "/compare.html" }};
              apiKeyInput.value = "sk-test";
              readerState.selectedBlockIds.add("s1_b1");
              readerState.explanationsByBlockId.set("s1_b1", {{
                short_explanation: "完整讲解",
                detail: "完整长讲解",
                source_refs: [{{ kind: "slide_text", slide: 1, object_id: "shape1" }}]
              }});
              globalThis.__exportAIGuidePdf = exportAIGuidePdf;
              globalThis.__posts = posts;
              globalThis.__readerHint = readerHint;
              `,
              context
            );
            (async () => {{
              await context.__exportAIGuidePdf();
              if (context.__posts.length !== 2) throw new Error(JSON.stringify(context.__posts));
              if (context.__posts[0].url !== "/api/ai/edit-pdf") throw new Error(context.__posts[0].url);
              if (context.__posts[1].url !== "/api/ai/export-guide") throw new Error(context.__posts[1].url);
              if (context.__posts[1].body.api_key) throw new Error("API key leaked to export");
              if (context.__posts[1].body.explanations[0].explanation.short_explanation !== "短补充") {{
                throw new Error(JSON.stringify(context.__posts[1].body));
              }}
              if (context.__readerHint.textContent.includes("不要展示")) {{
                throw new Error("reason leaked to main UI");
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

    def test_hit_blocks_at_point_returns_all_overlapping_blocks(self):
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
              const slide = {{
                blocks: [
                  {{ id: "bottom", display_bbox: {{ x: 0.1, y: 0.1, w: 0.4, h: 0.4 }} }},
                  {{ id: "top", display_bbox: {{ x: 0.2, y: 0.2, w: 0.4, h: 0.4 }} }}
                ]
              }};
              globalThis.__hits = hitBlocksAtPoint(slide, 0.25, 0.25).map((block) => block.id).join("|");
              `,
              context
            );
            if (context.__hits !== "top|bottom") {{
              throw new Error(context.__hits);
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

    def test_error_card_keeps_retry_button_for_failed_block(self):
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
              readerState.currentPage = 1;
              readerState.slidesByPage.set(1, {{
                number: 1,
                blocks: [
                  {{ id: "s1_b1", title: "A", display_bbox: {{ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }}, source_refs: [] }}
                ]
              }});
              readerState.errorsByBlockId.set("s1_b1", "模型不支持图片输入");
              renderExplanationPanel({{ number: 1 }});
              function hasRetry(node) {{
                if (node.dataset && node.dataset.explainBlock === "s1_b1") return true;
                return (node.children || []).some(hasRetry);
              }}
              globalThis.__hasRetry = hasRetry(explanationPanel);
              `,
              context
            );
            if (!context.__hasRetry) {{
              throw new Error("retry button missing");
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

    def test_generated_block_explanation_offers_other_profile_actions(self):
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
              promptProfileSelect.value = "study";
              readerState.currentPage = 1;
              readerState.slidesByPage.set(1, {{
                number: 1,
                blocks: [
                  {{ id: "s1_b1", title: "A", display_bbox: {{ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }}, source_refs: [] }}
                ]
              }});
              readerState.explanationsByBlockId.set("s1_b1", {{
                short_explanation: "学习版解释",
                detail: "学习版解释",
                prompt_profile: "study",
                source_refs: [{{ kind: "slide_text", slide: 1, object_id: "4" }}]
              }});
              renderExplanationPanel({{ number: 1 }});
              function collectProfiles(node, acc = []) {{
                if (node.dataset && node.dataset.promptProfile) acc.push(node.dataset.promptProfile);
                (node.children || []).forEach((child) => collectProfiles(child, acc));
                return acc;
              }}
              globalThis.__profiles = collectProfiles(explanationPanel).join("|");
              `,
              context
            );
            if (context.__profiles !== "training|simple") {{
              throw new Error(context.__profiles);
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

    def test_generated_page_explanation_offers_other_profile_actions(self):
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
              promptProfileSelect.value = "study";
              readerState.currentPage = 1;
              readerState.slidesByPage.set(1, {{
                number: 1,
                blocks: [
                  {{ id: "s1_b1", title: "A", display_bbox: {{ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }}, source_refs: [] }}
                ]
              }});
              readerState.pageExplanationsByPage.set(1, {{
                short_explanation: "学习版整页解释",
                detail: "学习版整页解释",
                prompt_profile: "study",
                source_refs: [{{ kind: "slide_text", slide: 1, object_id: "4" }}]
              }});
              renderExplanationPanel({{ number: 1 }});
              function collectProfiles(node, acc = []) {{
                if (node.dataset && node.dataset.explainPage) acc.push(node.dataset.explainPage + ":" + node.dataset.promptProfile);
                (node.children || []).forEach((child) => collectProfiles(child, acc));
                return acc;
              }}
              globalThis.__profiles = collectProfiles(explanationPanel).join("|");
              `,
              context
            );
            if (context.__profiles !== "1:training|1:simple") {{
              throw new Error(context.__profiles);
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

    def test_explanation_content_typesets_latex_with_mathjax(self):
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
            const calls = [];
            const context = {{
              document,
              HTMLInputElement,
              HTMLButtonElement,
              FormData: class FormData {{}},
              fetch: async () => ({{ ok: true, json: async () => ({{}}) }}),
              MathJax: {{
                typesetPromise(nodes) {{
                  calls.push(nodes.length);
                  return Promise.resolve();
                }}
              }},
              calls,
              console,
              URL
            }};

            vm.runInNewContext(
              code + `
              const host = document.createElement("div");
              appendExplanationContent(host, {{
                short_explanation: "公式为 \\\\(C = q / V\\\\)",
                detail: "推导为 $$C = C_1 + C_2$$",
                source_refs: [{{ kind: "slide_text", slide: 1, object_id: "4" }}]
              }});
              globalThis.__calls = calls.length;
              `,
              context
            );
            if (context.__calls !== 1) {{
              throw new Error(String(context.__calls));
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
