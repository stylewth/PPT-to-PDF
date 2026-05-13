const form = document.querySelector("#uploadForm");
const input = document.querySelector("#deckInput");
const button = document.querySelector("#convertButton");
const statusItems = [...document.querySelectorAll("#statusList li")];
const warningList = document.querySelector("#warningList");
const frame = document.querySelector("#previewFrame");
const resultTitle = document.querySelector("#resultTitle");
const downloadLinks = document.querySelector("#downloadLinks");

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
    ["预览", result.preview_url],
    ["分析", result.analysis_url],
    ["导读计划", result.augment_plan_url],
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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!input.files.length) return;

  button.disabled = true;
  button.textContent = "转换中";
  setStep(1);
  setWarnings([]);
  frame.removeAttribute("src");
  downloadLinks.innerHTML = "";
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
    setStep(statusItems.length);
    setWarnings(result.warnings || []);
    setDownloads(result);
    frame.src = result.preview_url;
  } catch (error) {
    setStep(0);
    warningList.innerHTML = `<div class="warning-item">${error.message}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = "重新转换";
  }
});
