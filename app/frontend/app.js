const form = document.querySelector("#uploadForm");
const input = document.querySelector("#deckInput");
const button = document.querySelector("#convertButton");
const statusItems = [...document.querySelectorAll("#statusList li")];
const warningList = document.querySelector("#warningList");
const frame = document.querySelector("#previewFrame");
const resultTitle = document.querySelector("#resultTitle");
const downloadLinks = document.querySelector("#downloadLinks");
const debugLinks = document.querySelector("#debugLinks");
const blockList = document.querySelector("#blockList");
const selectedSummary = document.querySelector("#selectedSummary");
const aiOutput = document.querySelector("#aiOutput");
const apiKeyInput = document.querySelector("#apiKeyInput");
const baseUrlInput = document.querySelector("#baseUrlInput");
const modelInput = document.querySelector("#modelInput");
const promptProfileSelect = document.querySelector("#promptProfileSelect");
const includeImagesInput = document.querySelector("#includeImagesInput");
const composeButton = document.querySelector("#composeButton");
const exportAIButton = document.querySelector("#exportAIButton");
const clearApiKeyButton = document.querySelector("#clearApiKeyButton");
const reader = document.querySelector("#reader");
const pageTabs = document.querySelector("#pageTabs");
const guidePageStage = document.querySelector("#guidePageStage");
const explanationPanel = document.querySelector("#explanationPanel");
const sendPageButton = document.querySelector("#sendPageButton");
const readerHint = document.querySelector("#readerHint");

let currentJobId = "";
let currentResult = null;
let currentKnowledge = null;
const readerState = {
  pages: [],
  slidesByPage: new Map(),
  currentPage: 1,
  selectedBlockIds: new Set(),
  explanationsByBlockId: new Map(),
  pageExplanationsByPage: new Map(),
  queue: [],
  queueStatusByBlockId: new Map(),
  errorsByBlockId: new Map(),
  activeBlockId: "",
  running: false
};
let selectedBlockIds = readerState.selectedBlockIds;

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
    node.textContent = `${warning.code || "warning"}: ${warning.message || warning}`;
    warningList.appendChild(node);
  });
}

function setDownloads(result) {
  downloadLinks.innerHTML = "";
  [
    ["Base PDF", result.base_pdf_url],
    ["Guide PDF", result.guide_pdf_url],
    ["对比页", result.compare_url],
    ["AI 解释版", result.ai_guide_pdf_url, !result.ai_guide_pdf_url]
  ].forEach(([label, href, disabled]) => {
    downloadLinks.appendChild(createOutputLink(label, href, Boolean(disabled)));
  });

  if (!debugLinks) return;
  debugLinks.innerHTML = "";
  [
    ["原始预览", result.preview_url],
    ["分析", result.analysis_url],
    ["导读计划", result.augment_plan_url],
    ["指标", result.metrics_url],
    ["媒体清单", result.media_manifest_url],
    ["知识块", result.knowledge_blocks_url],
    ["报告", result.report_url]
  ].filter(([, href]) => Boolean(href)).forEach(([label, href]) => {
    debugLinks.appendChild(createOutputLink(label, href, false, "debug-link"));
  });
}

function createOutputLink(label, href, disabled = false, className = "download-link") {
  const node = document.createElement(disabled ? "span" : "a");
  node.className = `${className}${disabled ? " disabled" : ""}`;
  node.textContent = label;
  if (!disabled) {
    node.href = href;
    node.target = "_blank";
    node.rel = "noreferrer";
  }
  return node;
}

async function loadReaderAssets(result) {
  resetAIState();
  if (!result.knowledge_blocks_url || !result.guide_preview_manifest_url) {
    setReaderMessage("未生成 guide 阅读器资产");
    return;
  }
  const [knowledge, manifest] = await Promise.all([
    fetchJson(result.knowledge_blocks_url, "知识块加载失败"),
    fetchJson(result.guide_preview_manifest_url, "Guide 预览加载失败")
  ]);
  currentKnowledge = knowledge;
  readerState.pages = (manifest.pages || []).map((page) => ({
    ...page,
    image_url: resolveAssetUrl(result.guide_preview_manifest_url, page.image)
  }));
  readerState.slidesByPage = new Map();
  (knowledge.slides || []).forEach((slide) => {
    readerState.slidesByPage.set(Number(slide.number), {
      mode: slide.mode || "blocks",
      fallback_reason: slide.fallback_reason || "",
      ...slide
    });
  });
  readerState.currentPage = readerState.pages[0]?.number || knowledge.slides?.[0]?.number || 1;
  if (reader) reader.hidden = false;
  renderReader();
}

async function fetchJson(url, message) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(message);
  }
  return response.json();
}

function resolveAssetUrl(baseUrl, relativePath) {
  const base = new URL(baseUrl, "http://local");
  return new URL(relativePath, base).pathname;
}

function resetAIState() {
  currentKnowledge = null;
  readerState.pages = [];
  readerState.slidesByPage = new Map();
  readerState.currentPage = 1;
  readerState.selectedBlockIds = new Set();
  selectedBlockIds = readerState.selectedBlockIds;
  readerState.explanationsByBlockId = new Map();
  readerState.pageExplanationsByPage = new Map();
  readerState.queue = [];
  readerState.queueStatusByBlockId = new Map();
  readerState.errorsByBlockId = new Map();
  readerState.activeBlockId = "";
  readerState.running = false;
  blockList.textContent = "转换后显示当前页知识块";
  aiOutput.textContent = "";
  if (guidePageStage) guidePageStage.textContent = "转换后显示 guide 页图";
  if (explanationPanel) explanationPanel.textContent = "";
  if (pageTabs) pageTabs.innerHTML = "";
  if (reader) reader.hidden = true;
  updateSelectedSummary();
}

function setReaderMessage(message) {
  if (readerHint) readerHint.textContent = message;
  if (guidePageStage && !getCurrentReaderPage()) guidePageStage.textContent = message;
}

function renderReader() {
  const page = getCurrentReaderPage();
  renderPageTabs();
  renderGuidePage(page);
  renderCurrentBlockList(page);
  renderExplanationPanel(page);
  updateSelectedSummary();
  if (sendPageButton) {
    sendPageButton.disabled = !page || !hasApiKey();
  }
  if (readerHint) {
    readerHint.textContent = hasApiKey() ? "" : "请先填写 API Key 后再生成解释";
  }
}

function renderPageTabs() {
  if (!pageTabs) return;
  pageTabs.innerHTML = "";
  readerState.pages.forEach((page) => {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = `page-tab${Number(page.number) === Number(readerState.currentPage) ? " active" : ""}`;
    tab.dataset.page = String(page.number);
    tab.textContent = String(page.number);
    pageTabs.appendChild(tab);
  });
}

function renderGuidePage(page) {
  if (!guidePageStage) return;
  guidePageStage.innerHTML = "";
  if (!page) {
    guidePageStage.textContent = "没有可预览页面";
    return;
  }
  const slide = getCurrentSlide();
  const wrapper = document.createElement("div");
  wrapper.className = "guide-page";

  const image = document.createElement("img");
  image.src = page.image_url;
  image.alt = `第 ${page.number} 页 guide 预览`;
  wrapper.appendChild(image);

  const layer = document.createElement("div");
  layer.className = "overlay-layer";
  (slide?.blocks || []).forEach((block, index) => {
    if (!isValidBbox(block.display_bbox)) {
      console.warn(`Invalid block bbox: ${block.id}`);
      return;
    }
    const overlay = document.createElement("button");
    overlay.type = "button";
    overlay.className = [
      "block-overlay",
      readerState.selectedBlockIds.has(block.id) ? "selected" : "",
      readerState.activeBlockId === block.id ? "active" : "",
      getBlockStatus(block.id)
    ].filter(Boolean).join(" ");
    overlay.dataset.blockId = block.id;
    overlay.title = block.title || block.id;
    overlay.setAttribute("aria-label", `选择 ${block.title || block.id}`);
    Object.assign(overlay.style, bboxToStyle(block.display_bbox));

    const mark = document.createElement("span");
    mark.className = "overlay-mark";
    mark.textContent = readerState.selectedBlockIds.has(block.id) ? "✓" : String(index + 1);
    overlay.appendChild(mark);
    layer.appendChild(overlay);
  });
  wrapper.appendChild(layer);
  guidePageStage.appendChild(wrapper);
}

function renderCurrentBlockList(page) {
  blockList.innerHTML = "";
  const slide = getCurrentSlide();
  if (!page || !slide || !(slide.blocks || []).length) {
    blockList.textContent = "当前页没有可解释知识块";
    return;
  }
  const heading = document.createElement("h3");
  heading.textContent = `第 ${slide.number} 页知识块`;
  blockList.appendChild(heading);

  (slide.blocks || []).forEach((block) => {
    const row = document.createElement("article");
    row.className = `knowledge-block ${readerState.activeBlockId === block.id ? "active" : ""}`;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.id = `block-${block.id}`;
    checkbox.dataset.blockId = block.id;
    checkbox.checked = readerState.selectedBlockIds.has(block.id);

    const body = document.createElement("label");
    body.htmlFor = checkbox.id;
    body.className = "block-body";
    body.dataset.focusBlock = block.id;

    const title = document.createElement("span");
    title.className = "block-title";
    title.textContent = block.title || block.id;

    const meta = document.createElement("span");
    meta.className = "block-meta";
    meta.textContent = `${blockTypeLabel(block.type)} · ${block.token_estimate || 0} tokens · ${statusLabel(getBlockStatus(block.id))}`;

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
    explainButton.textContent = getBlockStatus(block.id) === "done" ? "✓" : "解";

    row.append(checkbox, body, explainButton);
    blockList.appendChild(row);
  });
}

function renderExplanationPanel(page) {
  if (!explanationPanel) return;
  explanationPanel.innerHTML = "";
  const slide = getCurrentSlide();
  const header = document.createElement("div");
  header.className = "explanation-header";
  const title = document.createElement("h3");
  title.textContent = slide ? `第 ${slide.number} 页 · AI 解释` : "AI 解释";
  const meta = document.createElement("p");
  meta.textContent = "发送本页会生成整页解释；点击块可生成局部解释";
  header.append(title, meta);
  explanationPanel.appendChild(header);

  if (!page || !slide || !(slide.blocks || []).length) {
    const empty = document.createElement("p");
    empty.className = "empty-copy";
    empty.textContent = "转换后在这里查看对应原文的 AI 解释";
    explanationPanel.appendChild(empty);
    return;
  }

  const pageExplanation = readerState.pageExplanationsByPage.get(Number(slide.number));
  if (pageExplanation) {
    const card = document.createElement("article");
    card.className = "explanation-card page-explanation-card";
    const cardHeader = document.createElement("div");
    cardHeader.className = "explanation-card-header";
    const blockTitle = document.createElement("h4");
    blockTitle.textContent = "整页解释";
    const source = document.createElement("span");
    source.textContent = `第 ${slide.number} 页`;
    cardHeader.append(blockTitle, source);
    card.appendChild(cardHeader);
    appendExplanationContent(card, pageExplanation);
    explanationPanel.appendChild(card);
  }

  (slide.blocks || []).forEach((block) => {
    const card = document.createElement("article");
    card.className = `explanation-card ${readerState.activeBlockId === block.id ? "active" : ""}`;
    card.dataset.focusBlock = block.id;

    const cardHeader = document.createElement("div");
    cardHeader.className = "explanation-card-header";
    const blockTitle = document.createElement("h4");
    blockTitle.textContent = block.title || block.id;
    const source = document.createElement("span");
    source.textContent = `第 ${slide.number} 页 · ${block.id}`;
    cardHeader.append(blockTitle, source);
    card.appendChild(cardHeader);

    const explanation = readerState.explanationsByBlockId.get(block.id);
    const error = readerState.errorsByBlockId.get(block.id);
    if (explanation) {
      appendExplanationContent(card, explanation);
    } else if (error) {
      const errorNode = document.createElement("p");
      errorNode.className = "error-copy";
      errorNode.textContent = error;
      card.appendChild(errorNode);
    } else {
      const summary = document.createElement("p");
      summary.textContent = block.summary || "尚未生成解释";
      card.appendChild(summary);
      const action = document.createElement("button");
      action.type = "button";
      action.className = "secondary-button";
      action.dataset.explainBlock = block.id;
      action.textContent = statusLabel(getBlockStatus(block.id));
      action.disabled = getBlockStatus(block.id) === "pending" || getBlockStatus(block.id) === "running";
      card.appendChild(action);
    }
    explanationPanel.appendChild(card);
  });
}

function appendExplanationContent(parent, explanation) {
  const lead = document.createElement("p");
  lead.className = "explanation-lead";
  lead.textContent = asText(explanation.short_explanation || explanation.detail);
  parent.appendChild(lead);

  const detail = document.createElement("p");
  detail.textContent = asText(explanation.detail);
  parent.appendChild(detail);

  const sections = asSections(explanation.sections);
  if (sections.length) {
    sections.forEach((section) => appendList(parent, section.label, section.items));
  } else {
    appendList(parent, "要点", explanation.key_points);
    appendList(parent, "易错点", explanation.common_misunderstanding);
    appendList(parent, "复习题", explanation.review_questions);
  }

  const refs = document.createElement("div");
  refs.className = "source-refs";
  refs.textContent = `来源：${asList(explanation.source_refs).map(formatSourceRef).filter(Boolean).join("，")}`;
  parent.appendChild(refs);
}

function appendList(parent, label, items) {
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
  parent.append(heading, list);
}

function bboxToStyle(bbox) {
  return {
    left: `${bbox.x * 100}%`,
    top: `${bbox.y * 100}%`,
    width: `${bbox.w * 100}%`,
    height: `${bbox.h * 100}%`
  };
}

function isValidBbox(bbox) {
  if (!bbox || typeof bbox !== "object") return false;
  const values = ["x", "y", "w", "h"].map((key) => Number(bbox[key]));
  if (values.some((value) => !Number.isFinite(value))) return false;
  const [x, y, w, h] = values;
  return x >= 0 && y >= 0 && w > 0 && h > 0 && x + w <= 1.001 && y + h <= 1.001;
}

function getCurrentReaderPage() {
  return readerState.pages.find((page) => Number(page.number) === Number(readerState.currentPage));
}

function getCurrentSlide() {
  return readerState.slidesByPage.get(Number(readerState.currentPage));
}

function getBlockById(blockId) {
  for (const slide of readerState.slidesByPage.values()) {
    const block = (slide.blocks || []).find((item) => item.id === blockId);
    if (block) return block;
  }
  return null;
}

function blockTypeLabel(type) {
  return {
    formula_group: "公式",
    media_timeline: "媒体",
    diagram_group: "图示",
    animation_flow: "动画",
    text_concept: "文本",
    whole_page: "整页"
  }[type] || "知识点";
}

function getBlockStatus(blockId) {
  if (readerState.explanationsByBlockId.has(blockId)) return "done";
  return readerState.queueStatusByBlockId.get(blockId) || "idle";
}

function statusLabel(status) {
  return {
    idle: "解释",
    pending: "排队中",
    running: "生成中",
    done: "已生成",
    error: "重试"
  }[status] || "解释";
}

function updateSelectedSummary() {
  const count = readerState.selectedBlockIds.size;
  selectedSummary.textContent = count ? `已选择 ${count} 个知识块` : "尚未选择知识块";
  composeButton.disabled = !count || !hasApiKey();
  exportAIButton.disabled =
    !currentJobId || (!readerState.explanationsByBlockId.size && !readerState.pageExplanationsByPage.size);
}

function hasApiKey() {
  return Boolean(apiKeyInput.value.trim());
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
    prompt_profile: promptProfileSelect.value || "study",
    include_images: Boolean(includeImagesInput.checked)
  };
}

function enqueueBlockExplanation(blockId) {
  if (readerState.explanationsByBlockId.has(blockId)) return;
  if (readerState.queue.some((item) => item.blockId === blockId)) return;
  readerState.queueStatusByBlockId.set(blockId, "pending");
  readerState.queue.push({ blockId, wholePage: false });
  renderReader();
  runExplanationQueue();
}

function enqueueWholePageExplanation(pageNumber) {
  const slide = readerState.slidesByPage.get(Number(pageNumber));
  const block = slide?.blocks?.[0];
  if (!block) return;
  if (readerState.explanationsByBlockId.has(block.id)) return;
  if (readerState.queue.some((item) => item.blockId === block.id)) return;
  readerState.queueStatusByBlockId.set(block.id, "pending");
  readerState.queue.push({ blockId: block.id, wholePage: true, pageNumber: Number(pageNumber) });
  renderReader();
  runExplanationQueue();
}

async function runExplanationQueue() {
  if (readerState.running) return;
  readerState.running = true;
  try {
    while (readerState.queue.length > 0) {
      const item = readerState.queue.shift();
      readerState.queueStatusByBlockId.set(item.blockId, "running");
      renderReader();
      try {
        await explainSingleBlock(item.blockId, item);
        readerState.queueStatusByBlockId.delete(item.blockId);
      } catch (error) {
        readerState.queueStatusByBlockId.set(item.blockId, "error");
        readerState.errorsByBlockId.set(item.blockId, error.message);
      }
      renderReader();
    }
  } finally {
    readerState.running = false;
    renderReader();
  }
}

async function explainSingleBlock(blockId, options = {}) {
  if (!currentJobId) {
    throw new Error("请先完成转换");
  }
  const config = selectedApiConfig();
  const endpoint = options.wholePage ? "/api/ai/explain-page" : "/api/ai/explain";
  const body = options.wholePage
    ? { job_id: currentJobId, page_number: options.pageNumber, ...config }
    : { job_id: currentJobId, block_id: blockId, ...config };
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok || result.status !== "ok") {
    throw new Error(result.error || "AI 讲解失败");
  }
  readerState.errorsByBlockId.delete(blockId);
  readerState.explanationsByBlockId.set(blockId, result.explanation || {});
  renderAIResult(result, blockId);
}

async function explainWholePage(pageNumber) {
  if (!currentJobId) {
    throw new Error("请先完成转换");
  }
  const config = selectedApiConfig();
  const response = await fetch("/api/ai/explain-page", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: currentJobId,
      page_number: Number(pageNumber),
      ...config
    })
  });
  const result = await response.json();
  if (!response.ok || result.status !== "ok") {
    throw new Error(result.error || "AI 整页讲解失败");
  }
  readerState.pageExplanationsByPage.set(Number(pageNumber), result.explanation || {});
  renderAIResult(result);
  renderReader();
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: currentJobId,
      block_ids: blockIds,
      ...config
    })
  });
  const result = await response.json();
  if (!response.ok || result.status !== "ok") {
    throw new Error(result.error || "AI 讲解失败");
  }
  renderAIResult(result);
}

async function sendCurrentPage() {
  const slide = getCurrentSlide();
  if (!slide) return;
  if (!hasApiKey()) {
    setReaderMessage("请先填写 API Key");
    renderReader();
    return;
  }
  try {
    setReaderMessage("整页解释生成中");
    await explainWholePage(slide.number);
    setReaderMessage("整页解释已生成");
  } catch (error) {
    setReaderMessage(error.message);
  }
}

function renderAIResult(result, blockId = "") {
  const explanation = result.explanation || {};
  aiOutput.innerHTML = "";
  if (blockId) {
    readerState.explanationsByBlockId.set(blockId, explanation);
  }
  appendExplanationContent(aiOutput, explanation);
  updateSelectedSummary();
}

function collectExportExplanations() {
  const blockExplanations = [...readerState.explanationsByBlockId.entries()].map(([blockId, explanation]) => ({
    block_id: blockId,
    explanation
  }));
  const pageExplanations = [...readerState.pageExplanationsByPage.entries()].map(([pageNumber, explanation]) => ({
    page_number: Number(pageNumber),
    explanation
  }));
  return [...blockExplanations, ...pageExplanations];
}

async function exportAIGuidePdf() {
  if (!currentJobId) {
    throw new Error("请先完成转换");
  }
  const explanations = collectExportExplanations();
  if (!explanations.length) {
    throw new Error("请先生成至少一个 AI 解释");
  }
  exportAIButton.disabled = true;
  const originalText = exportAIButton.textContent;
  exportAIButton.textContent = "生成中";
  try {
    const response = await fetch("/api/ai/export-guide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: currentJobId,
        explanations
      })
    });
    const result = await response.json();
    if (!response.ok || result.status !== "ok") {
      throw new Error(result.error || "AI PDF 生成失败");
    }
    currentResult = {
      ...(currentResult || {}),
      ai_guide_pdf_url: result.ai_guide_pdf_url
    };
    setDownloads(currentResult);
    setReaderMessage("AI PDF 已生成，可在顶部下载");
  } finally {
    exportAIButton.textContent = originalText;
    updateSelectedSummary();
  }
}

function asList(value) {
  if (Array.isArray(value)) return value.filter((item) => item !== null && item !== undefined && item !== "");
  if (value === null || value === undefined || value === "") return [];
  return [value];
}

function asSections(value) {
  const rawSections = Array.isArray(value)
    ? value
    : value && typeof value === "object"
      ? Object.entries(value).map(([label, items]) => ({ label, items }))
      : [];
  return rawSections
    .map((section) => {
      if (typeof section === "string") {
        return { label: "说明", items: [section] };
      }
      const label = asText(section?.label || section?.title);
      const items = asList(section?.items ?? section?.text).map(asText).filter(Boolean);
      return { label, items };
    })
    .filter((section) => section.label && section.items.length);
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

function toggleBlockSelection(blockId) {
  if (!blockId) return;
  if (readerState.selectedBlockIds.has(blockId)) {
    readerState.selectedBlockIds.delete(blockId);
  } else {
    readerState.selectedBlockIds.add(blockId);
  }
  readerState.activeBlockId = blockId;
  renderReader();
}

function focusBlock(blockId) {
  if (!blockId) return;
  readerState.activeBlockId = blockId;
  renderReader();
  const card = explanationPanel?.querySelector?.(`[data-focus-block="${blockId}"]`);
  if (card?.scrollIntoView) {
    card.scrollIntoView({ block: "nearest" });
  }
}

pageTabs?.addEventListener("click", (event) => {
  const page = event.target?.dataset?.page;
  if (!page) return;
  readerState.currentPage = Number(page);
  readerState.activeBlockId = "";
  renderReader();
});

guidePageStage?.addEventListener("click", (event) => {
  const blockId = event.target?.dataset?.blockId || event.target?.parentElement?.dataset?.blockId;
  toggleBlockSelection(blockId);
});

blockList.addEventListener("change", (event) => {
  const checkbox = event.target;
  if (!(checkbox instanceof HTMLInputElement) || checkbox.type !== "checkbox") return;
  const blockId = checkbox.dataset.blockId;
  if (!blockId) return;
  if (checkbox.checked) {
    readerState.selectedBlockIds.add(blockId);
  } else {
    readerState.selectedBlockIds.delete(blockId);
  }
  readerState.activeBlockId = blockId;
  renderReader();
});

blockList.addEventListener("click", (event) => {
  const target = event.target;
  const explainBlock = target?.dataset?.explainBlock;
  const focusTarget = target?.dataset?.focusBlock;
  if (explainBlock) {
    if (!hasApiKey()) {
      setReaderMessage("请先填写 API Key");
      return;
    }
    enqueueBlockExplanation(explainBlock);
    return;
  }
  if (focusTarget) {
    focusBlock(focusTarget);
  }
});

explanationPanel?.addEventListener("click", (event) => {
  const explainBlock = event.target?.dataset?.explainBlock;
  const focusTarget = event.target?.dataset?.focusBlock || event.target?.parentElement?.dataset?.focusBlock;
  if (explainBlock) {
    if (!hasApiKey()) {
      setReaderMessage("请先填写 API Key");
      return;
    }
    enqueueBlockExplanation(explainBlock);
    return;
  }
  if (focusTarget) {
    focusBlock(focusTarget);
  }
});

sendPageButton?.addEventListener("click", () => {
  sendCurrentPage();
});

composeButton.addEventListener("click", async () => {
  try {
    await explainBlocks([...readerState.selectedBlockIds], "compose");
  } catch (error) {
    aiOutput.textContent = error.message;
  }
});

exportAIButton.addEventListener("click", async () => {
  try {
    await exportAIGuidePdf();
  } catch (error) {
    setReaderMessage(error.message);
  }
});

clearApiKeyButton.addEventListener("click", () => {
  apiKeyInput.value = "";
  renderReader();
  apiKeyInput.focus();
});

apiKeyInput.addEventListener("input", renderReader);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!input.files.length) return;

  button.disabled = true;
  button.textContent = "转换中";
  setStep(1);
  setWarnings([]);
  frame?.removeAttribute("src");
  downloadLinks.innerHTML = "";
  if (debugLinks) debugLinks.innerHTML = "";
  currentJobId = "";
  currentResult = null;
  resetAIState();
  resultTitle.textContent = input.files[0].name;

  const data = new FormData();
  data.append("deck", input.files[0]);

  try {
    setStep(2);
    const response = await fetch("/api/convert", {
      method: "POST",
      body: data
    });
    const result = await response.json();
    if (!response.ok || result.status !== "ok") {
      throw new Error(result.error || "转换失败");
    }
    currentJobId = result.job_id;
    currentResult = result;
    setStep(statusItems.length);
    setWarnings(result.warnings || []);
    setDownloads(result);
    await loadReaderAssets(result);
    if (frame && result.guide_pdf_url) frame.src = result.guide_pdf_url;
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

if (typeof window !== "undefined") {
  window.slide2studyReader = {
    async loadResult(result) {
      currentJobId = result.job_id || "";
      currentResult = result;
      setDownloads(result);
      await loadReaderAssets(result);
    },
    state: readerState
  };
}

if (document.addEventListener && document.dispatchEvent) {
  document.addEventListener("slide2study:loadResult", async (event) => {
    const result = event.detail || {};
    try {
      currentJobId = result.job_id || "";
      currentResult = result;
      setDownloads(result);
      await loadReaderAssets(result);
      dispatchReaderEvent("slide2study:loaded", { ok: true });
    } catch (error) {
      dispatchReaderEvent("slide2study:loaded", { ok: false, error: error.message });
    }
  });
}

updateSelectedSummary();

function dispatchReaderEvent(name, detail) {
  if (typeof CustomEvent === "function") {
    document.dispatchEvent(new CustomEvent(name, { detail }));
    return;
  }
  const event = document.createEvent("CustomEvent");
  event.initCustomEvent(name, false, false, detail);
  document.dispatchEvent(event);
}
