import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class V4FrontendAIOutputTest(unittest.TestCase):
    def test_render_ai_result_accepts_scalar_model_fields(self):
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
                this.classList = {{ toggle() {{}} }};
                this.value = "";
                this.files = [];
                this.disabled = false;
                this.textContent = "";
                this.innerHTML = "";
              }}
              appendChild(child) {{
                this.children.push(child);
                return child;
              }}
              append(...children) {{
                this.children.push(...children);
              }}
              addEventListener() {{}}
              removeAttribute() {{}}
              setAttribute(name, value) {{
                this[name] = value;
              }}
              focus() {{}}
            }}
            class HTMLInputElement extends FakeElement {{}}
            class HTMLButtonElement extends FakeElement {{}}

            const elements = new Map();
            for (const selector of [
              "#uploadForm", "#deckInput", "#convertButton", "#warningList", "#previewFrame",
              "#resultTitle", "#downloadLinks", "#blockList", "#selectedSummary", "#aiOutput",
              "#apiKeyInput", "#baseUrlInput", "#modelInput", "#composeButton", "#clearApiKeyButton"
            ]) {{
              elements.set(selector, new FakeElement());
            }}
            elements.set("#deckInput", new HTMLInputElement("input"));
            elements.set("#convertButton", new HTMLButtonElement("button"));
            elements.set("#composeButton", new HTMLButtonElement("button"));
            elements.set("#clearApiKeyButton", new HTMLButtonElement("button"));

            const document = {{
              querySelector(selector) {{
                return elements.get(selector) || new FakeElement();
              }},
              querySelectorAll(selector) {{
                return [new FakeElement("li"), new FakeElement("li")];
              }},
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
              console
            }};

            vm.runInNewContext(code + "\\nglobalThis.__renderAIResult = renderAIResult; globalThis.__aiOutput = aiOutput;", context);
            context.__renderAIResult({{
              explanation: {{
                short_explanation: "一句解释",
                detail: "详细解释",
                key_points: "单个要点",
                common_misunderstanding: null,
                review_questions: {{ question: "为什么半径会变？" }},
                source_refs: "slide_text@p1#18"
              }}
            }});

            const rendered = JSON.stringify(context.__aiOutput.children, (key, value) => {{
              if (key === "classList") return undefined;
              return value;
            }});
            if (!rendered.includes("单个要点") || !rendered.includes("为什么半径会变？")) {{
              throw new Error(rendered);
            }}
            if (rendered.includes("slide_text@p1#18") || rendered.includes("来源")) {{
              throw new Error(rendered);
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


if __name__ == "__main__":
    unittest.main()
