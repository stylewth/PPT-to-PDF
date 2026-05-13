const demoData = {
  course: {
    title: "机器学习导论 第 3 讲",
    fileMeta: "示例：动画遮挡 + 递进公式页",
    score: 86,
    issues: [
      { type: "danger", text: "最终层遮挡 2 处" },
      { type: "warning", text: "动画步骤 5 个" },
      { type: "info", text: "缺少页备注解释" },
    ],
    pages: [
      {
        section: "第 12 页",
        title: "梯度下降的更新逻辑",
        slide: ["当前位置", "损失函数", "下一步参数"],
        cover: "原始 PDF 只显示最终公式，遮住了中间推导",
        steps: [
          "先定位当前参数点，再观察损失函数曲线。",
          "动画第二步引入梯度方向，解释为什么要沿反方向移动。",
          "最终公式被拆成更新动作和学习率含义，便于课后复习。",
        ],
        explain:
          "这一页的核心不是记住公式，而是理解每次更新都在用局部斜率决定下一步方向。",
      },
      {
        section: "第 18 页",
        title: "过拟合与正则化",
        slide: ["训练集表现", "测试集表现", "泛化能力"],
        cover: "结论标签覆盖了对比图右侧曲线",
        steps: [
          "先比较训练集和测试集误差走势。",
          "再标出误差分叉的位置，说明模型开始记忆噪声。",
          "最后把正则化解释为限制模型复杂度的约束。",
        ],
        explain:
          "学习版 PDF 会把被盖住的曲线和结论分开呈现，避免只看到一句结论却看不到原因。",
      },
    ],
  },
  training: {
    title: "新员工辅助驾驶安全培训",
    fileMeta: "示例：流程弹出 + 风险提示页",
    score: 89,
    issues: [
      { type: "warning", text: "流程节点 6 个" },
      { type: "danger", text: "风险提示被覆盖" },
      { type: "info", text: "适合生成回看手册" },
    ],
    pages: [
      {
        section: "第 7 页",
        title: "接管提醒处理流程",
        slide: ["识别提醒", "确认路况", "平稳接管"],
        cover: "最终态只剩完整流程图，关键风险提示不明显",
        steps: [
          "先识别系统提醒类型，区分视觉、声音和方向盘震动。",
          "再确认周边交通状态，避免只关注仪表提示。",
          "最后执行平稳接管，并记录异常场景。",
        ],
        explain:
          "培训版 PDF 会把流程拆成可复述步骤，并保留每一步对应的风险提醒。",
      },
      {
        section: "第 11 页",
        title: "异常场景上报",
        slide: ["采集信息", "填写记录", "同步团队"],
        cover: "弹出层叠加后，上报字段示例被遮住",
        steps: [
          "先确认异常发生的时间、道路和天气。",
          "再填写可复现条件，不只写主观描述。",
          "最后同步给团队沉淀为培训案例。",
        ],
        explain:
          "系统把隐藏字段转成清单，帮助员工离开讲师后仍能照着完成上报。",
      },
    ],
  },
};

const state = {
  scenario: "course",
  fileName: "",
  layoutMode: "study",
  isAnalyzing: false,
};

const layoutModeLabels = {
  study: "学习版",
  notes: "批注版",
  brief: "回看版",
};

const fileInput = document.querySelector("#fileInput");
const uploadZone = document.querySelector("#uploadZone");
const fileTitle = document.querySelector("#fileTitle");
const fileMeta = document.querySelector("#fileMeta");
const segments = document.querySelectorAll(".segment");
const analyzeButton = document.querySelector("#analyzeButton");
const loadSampleButton = document.querySelector("#loadSampleButton");
const printButton = document.querySelector("#printButton");
const statusText = document.querySelector("#statusText");
const stepsList = document.querySelector("#stepsList");
const issueStrip = document.querySelector("#issueStrip");
const pdfPages = document.querySelector("#pdfPages");
const previewTitle = document.querySelector("#previewTitle");
const readabilityScore = document.querySelector("#readabilityScore");

function currentData() {
  return demoData[state.scenario];
}

function setScenario(nextScenario) {
  state.scenario = nextScenario;
  segments.forEach((button) => {
    button.classList.toggle("active", button.dataset.scenario === nextScenario);
  });
  resetAnalysis();
  renderPreview(false);
}

function resetAnalysis() {
  statusText.textContent = "等待转换";
  readabilityScore.textContent = "--";
  stepsList.querySelectorAll("li").forEach((item) => {
    item.classList.remove("active", "done");
  });
}

function setFile(file) {
  if (!file) return;
  state.fileName = file.name;
  fileTitle.textContent = file.name;
  fileMeta.textContent = `${formatBytes(file.size)} · Demo 展示转换结果形态`;
  resetAnalysis();
}

function loadSample() {
  const data = currentData();
  state.fileName = data.title;
  fileTitle.textContent = data.title;
  fileMeta.textContent = data.fileMeta;
  resetAnalysis();
  renderPreview(false);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function renderIssues() {
  issueStrip.innerHTML = "";
  currentData().issues.forEach((issue) => {
    const pill = document.createElement("span");
    pill.className = `issue-pill ${issue.type}`;
    pill.textContent = issue.text;
    issueStrip.appendChild(pill);
  });
}

function renderPreview(showResult = true) {
  const data = currentData();
  previewTitle.textContent = showResult
    ? `${state.fileName || data.title} · 演示版预览`
    : "学习型 PDF 预览";
  readabilityScore.textContent = showResult ? data.score : "--";
  renderIssues();
  pdfPages.classList.toggle("compact", state.layoutMode === "brief");
  pdfPages.innerHTML = "";

  const pages = showResult ? data.pages : data.pages.slice(0, 1);
  pages.forEach((page, index) => {
    const pageNode = document.createElement("article");
    pageNode.className = "pdf-page";
    pageNode.style.animationDelay = `${index * 80}ms`;
    pageNode.innerHTML = pageTemplate(page, index);
    pdfPages.appendChild(pageNode);
  });
}

function pageTemplate(page, index) {
  const noteLines = state.layoutMode === "notes" ? 9 : state.layoutMode === "brief" ? 3 : 6;
  return `
    <div class="original-slide">
      <div class="page-meta">
        <span>${page.section}</span>
        <span>原始演示页</span>
      </div>
      <div class="slide-canvas" aria-label="${page.title}">
        <div class="slide-title">${page.title}</div>
        <div class="concept-node node-a">${page.slide[0]}</div>
        <div class="arrow-line"></div>
        <div class="concept-node node-b">${page.slide[1]}</div>
        <div class="concept-node node-c">${page.slide[2]}</div>
        <div class="cover-layer">${page.cover}</div>
        <div class="small-note">检测到最终态遮挡，已拆分为学习路径</div>
      </div>
    </div>
    <div class="learning-layout">
      <div>
        <div class="page-meta">
          <span>学习版 ${index + 1}</span>
          <span>${layoutModeLabels[state.layoutMode]}</span>
        </div>
        <h3>${page.title}</h3>
      </div>
      <div class="timeline">
        ${page.steps
          .map(
            (step, stepIndex) => `
          <div class="timeline-step">
            <span>${stepIndex + 1}</span>
            <p>${step}</p>
          </div>
        `,
          )
          .join("")}
      </div>
      <div class="explain-box">
        <h3>复习解释</h3>
        <p>${page.explain}</p>
      </div>
      <div class="notes-area" aria-label="批注区">
        ${Array.from({ length: noteLines }, () => '<div class="note-line"></div>').join("")}
      </div>
    </div>
  `;
}

async function analyze() {
  if (state.isAnalyzing) return;
  state.isAnalyzing = true;
  analyzeButton.disabled = true;
  analyzeButton.textContent = "转换中";
  statusText.textContent = "正在分析课件结构";
  stepsList.querySelectorAll("li").forEach((item) => {
    item.classList.remove("active", "done");
  });

  const steps = [...stepsList.querySelectorAll("li")];
  for (const [index, item] of steps.entries()) {
    item.classList.add("active");
    statusText.textContent = item.textContent;
    await wait(430);
    item.classList.remove("active");
    item.classList.add("done");
  }

  statusText.textContent = "已生成演示版预览";
  state.isAnalyzing = false;
  analyzeButton.disabled = false;
  analyzeButton.textContent = "重新转换";
  renderPreview(true);
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

fileInput.addEventListener("change", (event) => {
  setFile(event.target.files[0]);
});

["dragenter", "dragover"].forEach((eventName) => {
  uploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    uploadZone.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  uploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    uploadZone.classList.remove("dragging");
  });
});

uploadZone.addEventListener("drop", (event) => {
  setFile(event.dataTransfer.files[0]);
});

segments.forEach((button) => {
  button.addEventListener("click", () => setScenario(button.dataset.scenario));
});

document.querySelectorAll("input[name='layoutMode']").forEach((input) => {
  input.addEventListener("change", () => {
    state.layoutMode = input.value;
    renderPreview(readabilityScore.textContent !== "--");
  });
});

analyzeButton.addEventListener("click", analyze);
loadSampleButton.addEventListener("click", loadSample);
printButton.addEventListener("click", () => window.print());

loadSample();
renderPreview(false);
