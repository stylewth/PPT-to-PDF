const form = document.querySelector("#uploadForm");
const input = document.querySelector("#deckInput");
const button = document.querySelector("#convertButton");
const statusItems = [...document.querySelectorAll("#statusList li")];
const warningList = document.querySelector("#warningList");
const frame = document.querySelector("#previewFrame");
const resultTitle = document.querySelector("#resultTitle");
const downloadLinks = document.querySelector("#downloadLinks");
const blockList = document.querySelector("#blockList");
const selectedSummary = document.querySelector("#selectedSummary");
const aiOutput = document.querySelector("#aiOutput");
const apiKeyInput = document.querySelector("#apiKeyInput");
const baseUrlInput = document.querySelector("#baseUrlInput");
const modelInput = document.querySelector("#modelInput");
const composeButton = document.querySelector("#composeButton");
const clearApiKeyButton = document.querySelector("#clearApiKeyButton");

let currentJobId = "";
let currentKnowledge = null;
let selectedBlockIds = new Set();

function setStep(index) {
  statusItems.forEach((item, itemIndex) => {
    item.classList.toggle("done", itemIndex < index);
    item.classList.toggle("active", itemIndex === index);
  });
}

function setWarnings(warnings) {
  warningList.innerHTML = "";
  if (!warnings.length) {
    warningList.textContent = "未发现明显遮挡或不支持动画";
    return;
  }
  warnings.forEach((warning) => {
    const node = document.createElement("div");
    node.className = "warning-item";
    node.textContent = `${warning.code}: ${warning.message}`;
    warningList.appendChild(node);
  });
}

function setDownloads(result) {
  downloadLinks.innerHTML = "";
  [
    ["Base PDF", result.base_pdf_url],
    ["Guide PDF", result.guide_pdf_url],
    ["对比页", result.compare_url],
    ["预览", result.preview_url],
    ["分析", result.analysis_url],
    ["导读计划", result.augment_plan_url],
    ["指标", result.metrics_url],
    ["媒体清单", result.media_manifest_url],
    ["知识块", result.knowledge_blocks_url],
    ["报告", result.report_url],
  ].filter(([, href]) => Boolean(href)).forEach(([label, href]) => {
    const link = document.createElement("a");
    link.className = "download-link";
    link.href = href;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = label;
    downloadLinks.appendChild(link);
  });
}

async function loadKnowledgeBlocks(url) {
  resetAIState();
  if (!url) {
    blockList.textContent = "未生成知识块";
    return;
  }
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("知识块加载失败");
  }
  currentKnowledge = await response.json();
  renderKnowledgeBlocks(currentKnowledge);
}

function resetAIState() {
  currentKnowledge = null;
  selectedBlockIds = new Set();
  blockList.textContent = "转换后显示知识块";
  aiOutput.textContent = "";
  updateSelectedSummary();
}

function renderKnowledgeBlocks(index) {
  blockList.innerHTML = "";
  const slides = index.slides || [];
  if (!slides.length) {
    blockList.textContent = "未识别到可解释知识块";
    return;
  }
  slides.forEach((slide) => {
    const group = document.createElement("section");
    group.className = "slide-block-group";

    const heading = document.createElement("h3");
    heading.textContent = `第 ${slide.number} 页 ${slide.title || ""}`.trim();
    group.appendChild(heading);

    (slide.blocks || []).forEach((block) => {
      const row = document.createElement("article");
      row.className = "knowledge-block";

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.id = `block-${block.id}`;
      checkbox.dataset.blockId = block.id;

      const body = document.createElement("label");
      body.htmlFor = checkbox.id;
      body.className = "block-body";

      const title = document.createElement("span");
      title.className = "block-title";
      title.textContent = block.title || block.id;

      const meta = document.createElement("span");
      meta.className = "block-meta";
      meta.textContent = `${blockTypeLabel(block.type)} · ${block.token_estimate || 0} tokens`;

      const summary = document.createElement("span");
      summary.className = "block-summary";
      summary.textContent = block.summary || "";

      body.append(title, meta, summary);

      const explainButton = document.createElement("button");
      explainButton.type = "button";
      explainButton.className = "icon-button";
      explainButton.dataset.explainBlock = block.id;
      explainButton.title = "解释此知识块";
      explainButton.setAttribute("aria-label", "解释此知识块");
      explainButton.textContent = "解";

      row.append(checkbox, body, explainButton);
      group.appendChild(row);
    });
    blockList.appendChild(group);
  });
  updateSelectedSummary();
}

function blockTypeLabel(type) {
  return {
    formula_group: "公式",
    media_timeline: "媒体",
    diagram_group: "图示",
    animation_flow: "动画",
    text_concept: "文本",
  }[type] || "知识点";
}

function updateSelectedSummary() {
  const count = selectedBlockIds.size;
  selectedSummary.textContent = count ? `已选择 ${count} 个知识块` : "尚未选择知识块";
  composeButton.disabled = !count;
}

function selectedApiConfig() {
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) {
    throw new Error("请先填写 API Key");
  }
  return {
    api_key: apiKey,
    base_url: baseUrlInput.value.trim(),
    model: modelInput.value.trim() || "gpt-4.1-mini",
  };
}

async function explainBlocks(blockIds, mode) {
  if (!currentJobId) {
    throw new Error("请先完成转换");
  }
  if (!blockIds.length) {
    throw new Error("请先选择知识块");
  }
  const config = selectedApiConfig();
  aiOutput.textContent = "生成中";
  const response = await fetch(mode === "compose" ? "/api/ai/compose" : "/api/ai/explain", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      job_id: currentJobId,
      block_ids: blockIds,
      ...config,
    }),
  });
  const result = await response.json();
  if (!response.ok || result.status !== "ok") {
    throw new Error(result.error || "AI 讲解失败");
  }
  renderAIResult(result);
}

function renderAIResult(result) {
  const explanation = result.explanation || {};
  aiOutput.innerHTML = "";

  const title = document.createElement("h3");
  title.textContent = explanation.short_explanation || "AI 讲解";
  aiOutput.appendChild(title);

  const detail = document.createElement("p");
  detail.textContent = asText(explanation.detail);
  aiOutput.appendChild(detail);

  appendList("要点", explanation.key_points);
  appendList("易错点", explanation.common_misunderstanding);
  appendList("复习题", explanation.review_questions);

  const refs = document.createElement("div");
  refs.className = "source-refs";
  refs.textContent = `来源：${asList(explanation.source_refs).map(formatSourceRef).join("，")}`;
  aiOutput.appendChild(refs);

  function appendList(label, items) {
    const values = asList(items);
    if (!values.length) return;
    const heading = document.createElement("strong");
    heading.textContent = label;
    const list = document.createElement("ul");
    values.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = asText(item);
      list.appendChild(li);
    });
    aiOutput.append(heading, list);
  }
}

function asList(value) {
  if (Array.isArray(value)) return value.filter((item) => item !== null && item !== undefined && item !== "");
  if (value === null || value === undefined || value === "") return [];
  return [value];
}

function asText(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (typeof value === "object") {
    return value.question || value.text || value.value || JSON.stringify(value);
  }
  return String(value);
}

function formatSourceRef(ref) {
  if (typeof ref === "string") return ref;
  if (!ref || typeof ref !== "object") return "";
  return `${ref.kind || "source"}@${ref.slide ? `p${ref.slide}` : "p?"}#${ref.object_id || ref.block_id || "?"}`;
}

blockList.addEventListener("change", (event) => {
  const checkbox = event.target;
  if (!(checkbox instanceof HTMLInputElement) || checkbox.type !== "checkbox") return;
  const blockId = checkbox.dataset.blockId;
  if (!blockId) return;
  if (checkbox.checked) {
    selectedBlockIds.add(blockId);
  } else {
    selectedBlockIds.delete(blockId);
  }
  updateSelectedSummary();
});

blockList.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement) || !target.dataset.explainBlock) return;
  try {
    await explainBlocks([target.dataset.explainBlock], "explain");
  } catch (error) {
    aiOutput.textContent = error.message;
  }
});

composeButton.addEventListener("click", async () => {
  try {
    await explainBlocks([...selectedBlockIds], "compose");
  } catch (error) {
    aiOutput.textContent = error.message;
  }
});

clearApiKeyButton.addEventListener("click", () => {
  apiKeyInput.value = "";
  apiKeyInput.focus();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!input.files.length) return;

  button.disabled = true;
  button.textContent = "转换中";
  setStep(1);
  setWarnings([]);
  frame.removeAttribute("src");
  downloadLinks.innerHTML = "";
  currentJobId = "";
  resetAIState();
  resultTitle.textContent = input.files[0].name;

  const data = new FormData();
  data.append("deck", input.files[0]);

  try {
    setStep(2);
    const response = await fetch("/api/convert", {
      method: "POST",
      body: data,
    });
    const result = await response.json();
    if (!response.ok || result.status !== "ok") {
      throw new Error(result.error || "转换失败");
    }
    currentJobId = result.job_id;
    setStep(statusItems.length);
    setWarnings(result.warnings || []);
    setDownloads(result);
    await loadKnowledgeBlocks(result.knowledge_blocks_url);
    frame.src = result.preview_url;
  } catch (error) {
    setStep(0);
    warningList.innerHTML = "";
    const node = document.createElement("div");
    node.className = "warning-item";
    node.textContent = error.message;
    warningList.appendChild(node);
  } finally {
    button.disabled = false;
    button.textContent = "重新转换";
  }
});

updateSelectedSummary();
