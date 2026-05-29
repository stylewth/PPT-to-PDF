const form = document.querySelector("#uploadForm");
const input = document.querySelector("#deckInput");
const button = document.querySelector("#convertButton");
const statusBlock = document.querySelector(".status-block");
const statusProgressBar = document.querySelector("#statusProgressBar");
const statusProgressFill = document.querySelector("#statusProgressFill");
const statusProgressText = document.querySelector("#statusProgressText");
const statusProgressPercent = document.querySelector("#statusProgressPercent");
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

const BLOCK_COLORS = ["#237a57", "#0b77bd", "#b35b00", "#7b3bb2", "#c21f39", "#65740b", "#006d6f", "#a33b7a"];
const PROMPT_PROFILE_LABELS = {
  study: "学习讲义版",
  training: "工作培训版",
  simple: "简单解释版"
};
const CONVERT_PROGRESS_STEPS = [
  { percent: 0, label: "等待上传" },
  { percent: 12, label: "上传 PPTX" },
  { percent: 28, label: "解析课件结构" },
  { percent: 45, label: "生成分析和导读计划" },
  { percent: 88, label: "整理 PDF 输出" },
  { percent: 100, label: "转换完成" }
];
const EXPLANATION_QUEUE_CONCURRENCY = 2;
const CONVERT_STATUS_POLL_MS = 700;

let currentJobId = "";
let currentResult = null;
let currentKnowledge = null;
let convertProgressTimers = [];
let activeConvertProgressKey = "";
const readerState = {
  pages: [],
  slidesByPage: new Map(),
  currentPage: 1,
  selectedBlockIds: new Set(),
  explanationsByBlockId: new Map(),
  explanationsByProfileKey: new Map(),
  pageExplanationsByPage: new Map(),
  pageExplanationsByProfileKey: new Map(),
  latestPdfEdit: null,
  queue: [],
  queueStatusByBlockId: new Map(),
  errorsByBlockId: new Map(),
  activeBlockId: "",
  hitCandidates: null,
  running: false
};
let selectedBlockIds = readerState.selectedBlockIds;

function setStep(index) {
  const total = CONVERT_PROGRESS_STEPS.length - 1;
  const clamped = Math.min(Math.max(index, 0), total);
  const step = CONVERT_PROGRESS_STEPS[clamped] || CONVERT_PROGRESS_STEPS[0];
  const isComplete = clamped >= total;
  setProgress(step.percent, step.label, isComplete ? "done" : clamped > 0 ? "running" : "idle");

  statusItems.forEach((item, itemIndex) => {
    item.classList.toggle("done", itemIndex < clamped);
    item.classList.toggle("active", itemIndex === clamped && !isComplete);
  });
}

function setProgress(percent, label, state = "running") {
  const value = Math.min(Math.max(Math.round(percent), 0), 100);
  if (statusBlock) statusBlock.dataset.state = state;
  if (statusProgressFill?.style) statusProgressFill.style.width = `${value}%`;
  if (statusProgressText) statusProgressText.textContent = label;
  if (statusProgressPercent) statusProgressPercent.textContent = state === "error" ? "失败" : `${value}%`;
  if (statusProgressBar) statusProgressBar.setAttribute("aria-valuenow", String(value));
}

function setStepError(message) {
  stopConvertProgress();
  setProgress(100, message || "转换失败", "error");
  statusItems.forEach((item) => {
    item.classList.remove("done");
    item.classList.remove("active");
  });
}

function startConvertProgress() {
  stopConvertProgress();
  activeConvertProgressKey = "";
  setProgress(8, "准备上传", "running");
  queueProgressStep(180, () => setProgress(12, "上传 PPTX", "running"));
  queueProgressStep(420, () => setProgress(28, "解析课件结构", "running"));
  queueProgressStep(780, () => beginAnalysisProgress());
}

function beginAnalysisProgress() {
  const startTime = Date.now();
  setProgress(45, "生成分析和导读计划", "running");
  const timer = window.setInterval(() => {
    const elapsed = Date.now() - startTime;
    const eased = 45 + Math.log1p(elapsed / 900) * 10.5;
    const percent = Math.min(88, eased);
    const label = percent >= 78 ? "整理 PDF 输出" : "生成分析和导读计划";
    setProgress(percent, label, "running");
  }, 450);
  convertProgressTimers.push(timer);
}

function finishConvertProgress() {
  stopConvertProgress();
  activeConvertProgressKey = "";
  setProgress(100, "转换完成", "done");
}

function stopConvertProgress() {
  convertProgressTimers.forEach((timer) => window.clearTimeout(timer));
  convertProgressTimers = [];
}

function queueProgressStep(delay, callback) {
  convertProgressTimers.push(window.setTimeout(callback, delay));
}

function applyConvertStatus(status) {
  if (status.status === "done") {
    finishConvertProgress();
    return status.result || null;
  }
  if (status.status === "error") {
    throw new Error(status.error || status.message || "转换失败");
  }
  const percent = Number(status.percent || 0);
  const nextPercent = Number(status.next_percent || Math.min(95, percent + 8));
  const message = status.message || "转换中";
  const key = `${status.stage || "running"}:${Math.round(percent)}:${Math.round(nextPercent)}:${message}`;
  if (key !== activeConvertProgressKey) {
    beginBackendProgress(percent, nextPercent, message, key);
  }
  return null;
}

function beginBackendProgress(percent, nextPercent, message, key) {
  stopConvertProgress();
  activeConvertProgressKey = key;
  const base = Math.min(Math.max(Number(percent) || 0, 0), 99);
  const ceiling = Math.min(Math.max(Number(nextPercent) || base, base), 99);
  const startTime = Date.now();
  setProgress(base, message, "running");
  const timer = window.setInterval(() => {
    const elapsed = Date.now() - startTime;
    const eased = base + Math.log1p(elapsed / 900) * Math.max(2, (ceiling - base) * 0.45);
    setProgress(Math.min(ceiling, eased), message, "running");
  }, 450);
  convertProgressTimers.push(timer);
}

async function pollConvertStatus(jobId, delayMs = CONVERT_STATUS_POLL_MS) {
  while (true) {
    const response = await fetch(`/api/convert-status?job_id=${encodeURIComponent(jobId)}`);
    const status = await response.json();
    if (!response.ok) {
      throw new Error(status.error || "转换状态获取失败");
    }
    const result = applyConvertStatus(status);
    if (result) {
      await loadConvertResult(result);
      return result;
    }
    if (delayMs > 0) {
      await wait(delayMs);
    }
  }
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function setWarnings(warnings) {
  if (!warningList) return;
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
  readerState.explanationsByProfileKey = new Map();
  readerState.pageExplanationsByPage = new Map();
  readerState.pageExplanationsByProfileKey = new Map();
  readerState.latestPdfEdit = null;
  readerState.queue = [];
  readerState.queueStatusByBlockId = new Map();
  readerState.errorsByBlockId = new Map();
  readerState.activeBlockId = "";
  readerState.hitCandidates = null;
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
    setStyleProperty(overlay, "--block-color", blockColor(index));
    overlay.style.zIndex = String(index + 1);

    const mark = document.createElement("span");
    mark.className = "overlay-mark";
    mark.textContent = readerState.selectedBlockIds.has(block.id) ? "✓" : String(index + 1);
    overlay.appendChild(mark);
    layer.appendChild(overlay);
  });
  renderHitCandidates(layer, slide);
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
    const blockIndex = (slide.blocks || []).findIndex((item) => item.id === block.id);
    const row = document.createElement("article");
    row.className = `knowledge-block ${readerState.activeBlockId === block.id ? "active" : ""}`;
    setStyleProperty(row, "--block-color", blockColor(blockIndex));

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

  const pageExplanation = getPageExplanation(slide.number);
  if (pageExplanation) {
    const card = document.createElement("article");
    card.className = "explanation-card page-explanation-card";
    const cardHeader = document.createElement("div");
    cardHeader.className = "explanation-card-header";
    const cardHeading = document.createElement("div");
    cardHeading.className = "explanation-card-heading";
    const blockTitle = document.createElement("h4");
    blockTitle.textContent = "整页解释";
    const source = document.createElement("span");
    source.textContent = `第 ${slide.number} 页`;
    cardHeading.append(blockTitle, source);
    cardHeader.appendChild(cardHeading);
    card.appendChild(cardHeader);
    appendExplanationContent(card, pageExplanation);
    appendPageProfileActions(card, slide.number);
    explanationPanel.appendChild(card);
  }

  (slide.blocks || []).forEach((block, index) => {
    const isSelected = readerState.selectedBlockIds.has(block.id);
    const card = document.createElement("article");
    card.className = [
      "explanation-card",
      isSelected ? "selected" : "",
      readerState.activeBlockId === block.id ? "active" : ""
    ].filter(Boolean).join(" ");
    card.dataset.focusBlock = block.id;
    setStyleProperty(card, "--block-color", blockColor(index));

    const cardHeader = document.createElement("div");
    cardHeader.className = "explanation-card-header";
    const cardHeading = document.createElement("div");
    cardHeading.className = "explanation-card-heading";
    const blockTitle = document.createElement("h4");
    blockTitle.textContent = block.title || block.id;
    const source = document.createElement("span");
    source.textContent = `第 ${slide.number} 页 · ${block.id}`;
    cardHeading.append(blockTitle, source);
    const selectLabel = document.createElement("label");
    selectLabel.className = "card-select-control";
    const selectInput = document.createElement("input");
    selectInput.type = "checkbox";
    selectInput.dataset.panelSelectBlock = block.id;
    selectInput.checked = isSelected;
    selectInput.setAttribute("aria-label", `选择 ${block.title || block.id} 进入 AI PDF`);
    const selectText = document.createElement("span");
    selectText.textContent = "入 AI PDF";
    selectLabel.append(selectInput, selectText);
    cardHeader.append(cardHeading, selectLabel);
    card.appendChild(cardHeader);

    const explanation = getBlockExplanation(block.id);
    const error = getBlockError(block.id);
    if (explanation) {
      appendExplanationContent(card, explanation);
      appendProfileActions(card, block.id);
    } else if (error) {
      const errorNode = document.createElement("p");
      errorNode.className = "error-copy";
      errorNode.textContent = error;
      card.appendChild(errorNode);
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "secondary-button";
      retry.dataset.explainBlock = block.id;
      retry.dataset.promptProfile = activePromptProfile();
      retry.textContent = "重试";
      retry.disabled = getBlockStatus(block.id) === "pending" || getBlockStatus(block.id) === "running";
      card.appendChild(retry);
    } else {
      const summary = document.createElement("p");
      summary.textContent = block.summary || "尚未生成解释";
      card.appendChild(summary);
      const action = document.createElement("button");
      action.type = "button";
      action.className = "secondary-button";
      action.dataset.explainBlock = block.id;
      action.dataset.promptProfile = activePromptProfile();
      action.textContent = statusLabel(getBlockStatus(block.id));
      action.disabled = getBlockStatus(block.id) === "pending" || getBlockStatus(block.id) === "running";
      card.appendChild(action);
    }
    explanationPanel.appendChild(card);
  });
}

function appendProfileActions(parent, blockId) {
  const current = activePromptProfile();
  const actions = document.createElement("div");
  actions.className = "profile-actions";
  Object.entries(PROMPT_PROFILE_LABELS).forEach(([profile, label]) => {
    if (profile === current) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-button";
    button.dataset.explainBlock = blockId;
    button.dataset.promptProfile = profile;
    button.textContent = hasBlockExplanation(blockId, profile) ? `查看${label}` : `用${label}再讲`;
    button.disabled = getBlockStatus(blockId, profile) === "pending" || getBlockStatus(blockId, profile) === "running";
    actions.appendChild(button);
  });
  if (actions.children.length) parent.appendChild(actions);
}

function appendPageProfileActions(parent, pageNumber) {
  const current = activePromptProfile();
  const actions = document.createElement("div");
  actions.className = "profile-actions";
  Object.entries(PROMPT_PROFILE_LABELS).forEach(([profile, label]) => {
    if (profile === current) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-button";
    button.dataset.explainPage = String(pageNumber);
    button.dataset.promptProfile = profile;
    button.textContent = hasPageExplanation(pageNumber, profile) ? `查看${label}` : `用${label}再讲`;
    actions.appendChild(button);
  });
  if (actions.children.length) parent.appendChild(actions);
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

  typesetMath(parent);
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

function hitBlocksAtPoint(slide, x, y) {
  return (slide?.blocks || [])
    .map((block, index) => ({ block, index }))
    .filter(({ block }) => {
      const bbox = block.display_bbox || {};
      if (!isValidBbox(bbox)) return false;
      return x >= bbox.x && y >= bbox.y && x <= bbox.x + bbox.w && y <= bbox.y + bbox.h;
    })
    .sort((first, second) => second.index - first.index)
    .map(({ block }) => block);
}

function renderHitCandidates(layer, slide) {
  const hit = readerState.hitCandidates;
  if (!hit || Number(hit.page) !== Number(readerState.currentPage) || !hit.blockIds?.length) return;
  const menu = document.createElement("div");
  menu.className = "hit-candidates";
  menu.style.left = `${Math.min(Math.max(hit.x, 0.02), 0.86) * 100}%`;
  menu.style.top = `${Math.min(Math.max(hit.y, 0.02), 0.86) * 100}%`;
  hit.blockIds.forEach((blockId) => {
    const block = (slide?.blocks || []).find((item) => item.id === blockId);
    if (!block) return;
    const index = (slide.blocks || []).findIndex((item) => item.id === blockId);
    const option = document.createElement("button");
    option.type = "button";
    option.dataset.candidateBlockId = blockId;
    setStyleProperty(option, "--block-color", blockColor(index));
    option.textContent = `${index + 1}. ${block.title || blockId}`;
    menu.appendChild(option);
  });
  if (menu.children.length) layer.appendChild(menu);
}

function setStyleProperty(node, name, value) {
  if (node?.style?.setProperty) {
    node.style.setProperty(name, value);
  } else if (node?.style) {
    node.style[name] = value;
  }
}

function blockColor(index) {
  const safeIndex = Number.isFinite(index) && index >= 0 ? index : 0;
  return BLOCK_COLORS[safeIndex % BLOCK_COLORS.length];
}

function eventPointInGuidePage(event) {
  const pageNode = event.target?.closest?.(".guide-page");
  if (!pageNode?.getBoundingClientRect || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)) {
    return null;
  }
  const rect = pageNode.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  return {
    x: (event.clientX - rect.left) / rect.width,
    y: (event.clientY - rect.top) / rect.height
  };
}

function typesetMath(parent) {
  const mathJax = globalThis.MathJax;
  if (!mathJax?.typesetPromise) return;
  mathJax.typesetPromise([parent]).catch((error) => {
    console.warn("MathJax typeset failed", error);
  });
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

function activePromptProfile() {
  return promptProfileSelect.value || "study";
}

function profileKey(blockId, profile) {
  return `${blockId}::${profile || activePromptProfile()}`;
}

function pageProfileKey(pageNumber, profile) {
  return `${Number(pageNumber)}::${profile || activePromptProfile()}`;
}

function hasBlockExplanation(blockId, profile) {
  return readerState.explanationsByProfileKey.has(profileKey(blockId, profile || activePromptProfile()));
}

function getBlockExplanation(blockId) {
  return (
    readerState.explanationsByProfileKey.get(profileKey(blockId, activePromptProfile())) ||
    readerState.explanationsByBlockId.get(blockId)
  );
}

function hasPageExplanation(pageNumber, profile) {
  return readerState.pageExplanationsByProfileKey.has(pageProfileKey(pageNumber, profile || activePromptProfile()));
}

function getPageExplanation(pageNumber) {
  return (
    readerState.pageExplanationsByProfileKey.get(pageProfileKey(pageNumber, activePromptProfile())) ||
    readerState.pageExplanationsByPage.get(Number(pageNumber))
  );
}

function getBlockError(blockId) {
  return readerState.errorsByBlockId.get(profileKey(blockId, activePromptProfile())) || readerState.errorsByBlockId.get(blockId);
}

function getBlockStatus(blockId, profile) {
  const selectedProfile = profile || activePromptProfile();
  if (hasBlockExplanation(blockId, selectedProfile)) return "done";
  return readerState.queueStatusByBlockId.get(profileKey(blockId, selectedProfile)) || "idle";
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
    !currentJobId || !hasApiKey() || !collectExportExplanations().length;
}

function hasApiKey() {
  return Boolean(apiKeyInput.value.trim());
}

function selectedApiConfig(profileOverride = "") {
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) {
    throw new Error("请先填写 API Key");
  }
  return {
    api_key: apiKey,
    base_url: baseUrlInput.value.trim(),
    model: modelInput.value.trim() || "gpt-4.1-mini",
    prompt_profile: profileOverride || activePromptProfile(),
    include_images: Boolean(includeImagesInput.checked)
  };
}

function enqueueBlockExplanation(blockId, profile = activePromptProfile()) {
  if (hasBlockExplanation(blockId, profile)) {
    promptProfileSelect.value = profile;
    renderReader();
    return;
  }
  const statusKey = profileKey(blockId, profile);
  const status = readerState.queueStatusByBlockId.get(statusKey);
  if (status === "pending" || status === "running") return;
  promptProfileSelect.value = profile;
  readerState.errorsByBlockId.delete(statusKey);
  readerState.errorsByBlockId.delete(blockId);
  readerState.queueStatusByBlockId.set(statusKey, "pending");
  readerState.queue.push({ blockId, wholePage: false, profile });
  renderReader();
  runExplanationQueue();
}

function enqueueWholePageExplanation(pageNumber) {
  const slide = readerState.slidesByPage.get(Number(pageNumber));
  const block = slide?.blocks?.[0];
  if (!block) return;
  const profile = activePromptProfile();
  if (hasBlockExplanation(block.id, profile)) return;
  if (readerState.queue.some((item) => item.blockId === block.id && item.profile === profile)) return;
  readerState.queueStatusByBlockId.set(profileKey(block.id, profile), "pending");
  readerState.queue.push({ blockId: block.id, wholePage: true, pageNumber: Number(pageNumber), profile });
  renderReader();
  runExplanationQueue();
}

async function runExplanationQueue() {
  if (readerState.running) return;
  readerState.running = true;
  try {
    const workerCount = Math.min(EXPLANATION_QUEUE_CONCURRENCY, readerState.queue.length);
    const workers = Array.from({ length: workerCount }, async () => {
      while (readerState.queue.length > 0) {
        const item = readerState.queue.shift();
        if (!item) continue;
        const statusKey = profileKey(item.blockId, item.profile);
        readerState.queueStatusByBlockId.set(statusKey, "running");
        renderReader();
        try {
          await explainSingleBlock(item.blockId, item);
          readerState.queueStatusByBlockId.delete(statusKey);
        } catch (error) {
          readerState.queueStatusByBlockId.set(statusKey, "error");
          readerState.errorsByBlockId.set(statusKey, error.message);
        }
        renderReader();
      }
    });
    await Promise.all(workers);
  } finally {
    readerState.running = false;
    renderReader();
  }
}

async function explainSingleBlock(blockId, options = {}) {
  if (!currentJobId) {
    throw new Error("请先完成转换");
  }
  const config = selectedApiConfig(options.profile || activePromptProfile());
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
  const explanation = { ...(result.explanation || {}), prompt_profile: config.prompt_profile };
  readerState.errorsByBlockId.delete(profileKey(blockId, config.prompt_profile));
  readerState.explanationsByProfileKey.set(profileKey(blockId, config.prompt_profile), explanation);
  readerState.explanationsByBlockId.set(blockId, explanation);
  renderAIResult(result, blockId);
}

async function explainWholePage(pageNumber, profile = activePromptProfile()) {
  if (!currentJobId) {
    throw new Error("请先完成转换");
  }
  if (hasPageExplanation(pageNumber, profile)) {
    const explanation = readerState.pageExplanationsByProfileKey.get(pageProfileKey(pageNumber, profile));
    renderAIResult({ status: "ok", explanation });
    renderReader();
    return;
  }
  const config = selectedApiConfig(profile);
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
  const explanation = { ...(result.explanation || {}), prompt_profile: config.prompt_profile };
  readerState.pageExplanationsByProfileKey.set(pageProfileKey(pageNumber, config.prompt_profile), explanation);
  readerState.pageExplanationsByPage.set(Number(pageNumber), explanation);
  renderAIResult({ ...result, explanation });
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
    await explainWholePage(slide.number, activePromptProfile());
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
  return [...readerState.selectedBlockIds]
    .map((blockId) => {
      const explanation = getBlockExplanation(blockId);
      return explanation ? { block_id: blockId, explanation } : null;
    })
    .filter(Boolean);
}

async function editExplanationsForPdf(explanations) {
  const config = selectedApiConfig();
  const requestKey = pdfEditRequestKey(explanations, config);
  if (readerState.latestPdfEdit?.request_key === requestKey) {
    return readerState.latestPdfEdit.export_explanations || [];
  }
  const response = await fetch("/api/ai/edit-pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: currentJobId,
      explanations,
      ...config
    })
  });
  const result = await response.json();
  if (!response.ok || result.status !== "ok") {
    throw new Error(result.error || "AI PDF 整理失败");
  }
  result.request_key = requestKey;
  readerState.latestPdfEdit = result;
  return result.export_explanations || [];
}

function pdfEditRequestKey(explanations, config) {
  return JSON.stringify({
    job_id: currentJobId,
    model: config.model || "",
    base_url: config.base_url || "",
    prompt_profile: config.prompt_profile || "",
    explanations: (explanations || []).map((item) => ({
      target: exportItemKey(item),
      prompt_profile: item?.explanation?.prompt_profile || item?.prompt_profile || "",
      text: asText(
        item?.explanation?.pdf_snippet ||
        item?.explanation?.short_explanation ||
        item?.explanation?.detail
      ),
      sections: asSections(item?.explanation?.sections),
      source_refs: item?.explanation?.source_refs || []
    }))
  });
}

function exportItemKey(item) {
  if (item?.page_number) return `page:${Number(item.page_number)}`;
  return `block:${item?.block_id || ""}`;
}

function hasPdfExplanationText(item) {
  const explanation = item?.explanation || {};
  return Boolean(
    asText(explanation.pdf_snippet || explanation.short_explanation || explanation.detail).trim() ||
    asList(explanation.key_points).length ||
    asSections(explanation.sections).length
  );
}

function mergeEditedExportExplanations(selectedExplanations, editedExplanations) {
  const editedByKey = new Map(
    (editedExplanations || [])
      .filter((item) => item && typeof item === "object")
      .map((item) => [exportItemKey(item), item])
  );
  return selectedExplanations.map((selected) => {
    const edited = editedByKey.get(exportItemKey(selected));
    const source = hasPdfExplanationText(edited) ? edited : selected;
    return {
      ...source,
      include_in_pdf: true
    };
  });
}

async function exportAIGuidePdf() {
  if (!currentJobId) {
    throw new Error("请先完成转换");
  }
  const explanations = collectExportExplanations();
  if (!explanations.length) {
    throw new Error("请先选择已生成 AI 解释的块");
  }
  if (!hasApiKey()) {
    throw new Error("请先填写 API Key，让 AI 整理进入 PDF 的短稿");
  }
  exportAIButton.disabled = true;
  const originalText = exportAIButton.textContent;
  exportAIButton.textContent = "整理中";
  try {
    const editedExplanations = await editExplanationsForPdf(explanations);
    const exportExplanations = mergeEditedExportExplanations(explanations, editedExplanations);
    exportAIButton.textContent = "生成中";
    const response = await fetch("/api/ai/export-guide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: currentJobId,
        explanations: exportExplanations
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
    setReaderMessage(`AI 已整理 ${exportExplanations.length} 条重点补充，PDF 已生成`);
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

function setBlockSelection(blockId, selected, scrollToPanel = true) {
  if (!blockId) return;
  if (selected) {
    readerState.selectedBlockIds.add(blockId);
  } else {
    readerState.selectedBlockIds.delete(blockId);
  }
  readerState.activeBlockId = blockId;
  readerState.hitCandidates = null;
  renderReader();
  if (scrollToPanel) scrollExplanationCard(blockId);
}

function toggleBlockSelection(blockId) {
  setBlockSelection(blockId, !readerState.selectedBlockIds.has(blockId));
}

function scrollExplanationCard(blockId) {
  const card = explanationPanel?.querySelector?.(`[data-focus-block="${blockId}"]`);
  if (card?.scrollIntoView) {
    card.scrollIntoView({ block: "nearest" });
  }
}

function focusBlock(blockId) {
  if (!blockId) return;
  readerState.activeBlockId = blockId;
  renderReader();
  scrollExplanationCard(blockId);
}

pageTabs?.addEventListener("click", (event) => {
  const page = event.target?.dataset?.page;
  if (!page) return;
  readerState.currentPage = Number(page);
  readerState.activeBlockId = "";
  readerState.hitCandidates = null;
  renderReader();
});

guidePageStage?.addEventListener("click", (event) => {
  const candidateBlockId = event.target?.dataset?.candidateBlockId;
  if (candidateBlockId) {
    toggleBlockSelection(candidateBlockId);
    return;
  }
  const point = eventPointInGuidePage(event);
  if (point) {
    const hits = hitBlocksAtPoint(getCurrentSlide(), point.x, point.y);
    if (hits.length > 1) {
      readerState.hitCandidates = {
        page: readerState.currentPage,
        x: point.x,
        y: point.y,
        blockIds: hits.map((block) => block.id)
      };
      readerState.activeBlockId = hits[0].id;
      renderReader();
      return;
    }
    if (hits.length === 1) {
      toggleBlockSelection(hits[0].id);
      return;
    }
  }
  const blockId = event.target?.dataset?.blockId || event.target?.parentElement?.dataset?.blockId;
  toggleBlockSelection(blockId);
});

blockList.addEventListener("change", (event) => {
  const checkbox = event.target;
  if (!(checkbox instanceof HTMLInputElement) || checkbox.type !== "checkbox") return;
  const blockId = checkbox.dataset.blockId;
  if (!blockId) return;
  setBlockSelection(blockId, checkbox.checked);
});

blockList.addEventListener("click", (event) => {
  const target = event.target;
  const explainBlock = target?.dataset?.explainBlock;
  const promptProfile = target?.dataset?.promptProfile || activePromptProfile();
  const focusTarget = target?.dataset?.focusBlock;
  if (explainBlock) {
    if (!hasApiKey()) {
      setReaderMessage("请先填写 API Key");
      return;
    }
    enqueueBlockExplanation(explainBlock, promptProfile);
    return;
  }
  if (focusTarget) {
    focusBlock(focusTarget);
  }
});

explanationPanel?.addEventListener("change", (event) => {
  const checkbox = event.target;
  if (!(checkbox instanceof HTMLInputElement) || checkbox.type !== "checkbox") return;
  const blockId = checkbox.dataset.panelSelectBlock;
  if (!blockId) return;
  setBlockSelection(blockId, checkbox.checked);
});

explanationPanel?.addEventListener("click", (event) => {
  const explainBlock = event.target?.dataset?.explainBlock;
  const explainPage = event.target?.dataset?.explainPage;
  const promptProfile = event.target?.dataset?.promptProfile || activePromptProfile();
  const focusTarget = event.target?.dataset?.focusBlock || event.target?.parentElement?.dataset?.focusBlock;
  if (explainBlock) {
    if (!hasApiKey()) {
      setReaderMessage("请先填写 API Key");
      return;
    }
    enqueueBlockExplanation(explainBlock, promptProfile);
    return;
  }
  if (explainPage) {
    const pageNumber = Number(explainPage);
    promptProfileSelect.value = promptProfile;
    if (hasPageExplanation(pageNumber, promptProfile)) {
      renderReader();
      return;
    }
    if (!hasApiKey()) {
      setReaderMessage("请先填写 API Key");
      return;
    }
    setReaderMessage("整页解释生成中");
    explainWholePage(pageNumber, promptProfile)
      .then(() => setReaderMessage("整页解释已生成"))
      .catch((error) => setReaderMessage(error.message));
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

async function loadConvertResult(result) {
  currentJobId = result.job_id;
  currentResult = result;
  setWarnings(result.warnings || []);
  setDownloads(result);
  await loadReaderAssets(result);
  if (frame && result.guide_pdf_url) frame.src = result.guide_pdf_url;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!input.files.length) return;

  button.disabled = true;
  button.textContent = "转换中";
  startConvertProgress();
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
    const response = await fetch("/api/convert", {
      method: "POST",
      body: data
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "转换失败");
    }
    if (result.status === "accepted") {
      currentJobId = result.job_id;
      await pollConvertStatus(result.job_id);
      return;
    }
    if (result.status !== "ok") {
      throw new Error(result.error || "转换失败");
    }
    finishConvertProgress();
    await loadConvertResult(result);
  } catch (error) {
    setStepError(error.message);
    resultTitle.textContent = "转换失败";
    readerHint.textContent = error.message;
    if (warningList) {
      warningList.innerHTML = "";
      const node = document.createElement("div");
      node.className = "warning-item";
      node.textContent = error.message;
      warningList.appendChild(node);
    }
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
setStep(0);

function dispatchReaderEvent(name, detail) {
  if (typeof CustomEvent === "function") {
    document.dispatchEvent(new CustomEvent(name, { detail }));
    return;
  }
  const event = document.createEvent("CustomEvent");
  event.initCustomEvent(name, false, false, detail);
  document.dispatchEvent(event);
}

const clearCacheBtn = document.querySelector("#clearCacheButton");
if (clearCacheBtn) {
  clearCacheBtn.addEventListener("click", async () => {
    try {
      const resp = await fetch("/api/cache/clear");
      const data = await resp.json();
      clearCacheBtn.textContent = data.cleared ? "缓存已清除" : "无缓存";
      setTimeout(() => { clearCacheBtn.textContent = "清除缓存"; }, 2000);
    } catch (_) {
      clearCacheBtn.textContent = "操作失败";
      setTimeout(() => { clearCacheBtn.textContent = "清除缓存"; }, 2000);
    }
  });
}
