const STORAGE_KEY = "listing-agent-skills-v1";
const PREFERENCE_KEY = "listing-agent-preferences-v1";
const SELLFOX_STORAGE_KEY = "listing-agent-sellfox-aba-v1";
const LISTING_API_BASE =
  typeof window !== "undefined" && window.LISTING_AGENT_API_BASE
    ? window.LISTING_AGENT_API_BASE.replace(/\/+$/, "")
    : typeof window !== "undefined" && window.location.pathname.startsWith("/listing-agent")
      ? "/listing-agent/api"
      : "/api";
const RISK_LIBRARY_STORAGE_KEY = "listing-agent-risk-library-v1";

const DEFAULT_RISK_LIBRARY = [
  ["waterproof", "high"], ["water-resistant", "high"], ["sweatproof", "high"], ["smudge-proof", "high"],
  ["24-hour", "high"], ["48-hour", "high"], ["72-hour", "high"], ["all-day", "high"], ["long-lasting", "high"], ["long-wear", "high"],
  ["hypoallergenic", "high"], ["latex-free", "high"], ["non-toxic", "high"], ["irritation-free", "high"], ["no irritation", "high"],
  ["residue-free", "high"], ["safe for sensitive eyes", "high"], ["sensitive eyes", "high"], ["allergy safe", "high"],
  ["medical grade", "high"], ["FDA approved", "high"], ["FDA registered", "high"], ["clinically proven", "high"],
  ["dermatologist tested", "high"], ["ophthalmologist tested", "high"],
  ["reusable", "medium"], ["vegan", "medium"], ["cruelty-free", "medium"], ["formaldehyde-free", "medium"],
  ["natural ingredients", "medium"], ["eco-friendly", "medium"], ["best seller", "medium"], ["best-selling", "medium"],
  ["top rated", "medium"], ["#1", "medium"], ["hot sale", "medium"], ["free delivery", "medium"], ["free gift", "medium"],
  ["guaranteed", "medium"], ["100% satisfaction", "medium"]
].map(([term, level]) => ({ term, level }));

const VARIANT_PROFILES = [
  {
    id: "balanced",
    name: "排名优先版",
    badge: "高排名词",
    titleStrategy: "keywordFirst",
    bulletPattern: "painSolutionScene",
    tone: "beauty factual",
    bestFor: "适合用最相关、当前 ABA 排名最靠前的词建立标题首要搜索入口。",
    angle: "先使用产品相关性通过的高排名词，再由规格、痛点和场景承接转化。"
  },
  {
    id: "style",
    name: "增长机会版",
    badge: "上升趋势词",
    titleStrategy: "styleFirst",
    bulletPattern: "benefitSpecScene",
    tone: "premium soft",
    bestFor: "适合测试排名上升更快、同时与产品风格相符的关键词切入机会。",
    angle: "用增长词与视觉风格做组合，优先争取正在上升的细分搜索入口。"
  },
  {
    id: "search",
    name: "转化承接版",
    badge: "点击转化信号",
    titleStrategy: "keywordFirst",
    bulletPattern: "routineFirst",
    tone: "direct conversion",
    bestFor: "适合优先承接前三商品点击和转化份额都较高的成熟需求。",
    angle: "用转化承接词建立标题和五点的购买意图，再将其他排名词分配到后台词。"
  }
];

const DEFAULT_SKILL = {
  id: "default-false-lash",
  name: "False Lash Listing Architect",
  titleStrategy: "keywordFirst",
  tone: "beauty factual",
  bulletPattern: "painSolutionScene",
  titleLimit: 75,
  itemHighlightLimit: 125,
  bulletLimit: 500,
  descriptionLimit: 2000,
  searchTermLimit: 249,
  referenceListing: "",
  learning: {
    selectionCounts: {},
    recentSelections: [],
    feedback: [],
    learnedRules: [],
    updatedAt: ""
  },
  forbiddenClaims: "",
  customRules:
    "标题不超过 75 字符，避免禁用符号且实义词不重复超过 2 次；Item Highlights 不超过 125 字符；Search Terms 不超过 249 bytes；未确认根数不进标题；五点避免模板化，必须结合场景和痛点。"
};

const BUILTIN_SKILLS = [
  DEFAULT_SKILL,
  {
    ...DEFAULT_SKILL,
    id: "builtin-ranking-first",
    name: "ABA 排名优先 Skill",
    titleStrategy: "keywordFirst",
    tone: "direct conversion",
    bulletPattern: "painSolutionScene"
  },
  {
    ...DEFAULT_SKILL,
    id: "builtin-natural-premium",
    name: "自然风格转化 Skill",
    titleStrategy: "styleFirst",
    tone: "premium soft",
    bulletPattern: "benefitSpecScene"
  }
];

function getBuiltinSkills() {
  return BUILTIN_SKILLS.map((skill) => ({
    ...skill,
    learning: createDefaultSkillLearning()
  }));
}

function isBuiltinSkill(skillOrId) {
  const id = typeof skillOrId === "string" ? skillOrId : skillOrId?.id;
  return BUILTIN_SKILLS.some((skill) => skill.id === id);
}

const SAMPLE_DATA = {
  marketplace: "US",
  brandName: "ALICE",
  productType: "lash clusters",
  styleAngle: "natural wispy",
  lengths: "10-14mm",
  curl: "D Curl",
  bandType: "clear band",
  pieceCount: "120pcs",
  contents: ["lash tray", "bond", "seal", "applicator"],
  verifiedClaims: [],
  imageFacts:
    "Packaging shows 10/12/14mm, D Curl, clear band. Tray appears to include 120pcs. Bond, seal and applicator are shown as included.",
  t1Keywords: "lash clusters, cluster lashes, eyelash clusters",
  t2Keywords: "beginner friendly, easy to apply, anti lift, natural look",
  t3Keywords: "office, date, vacation, clean girl makeup, soft glam",
  abaRankings:
    "#1 lash clusters; #3 cluster lashes; #8 eyelash clusters. ABA Top 3 click share favors natural look, beginner friendly and clear band modifiers.",
  forbiddenRankings:
    "High risk: best seller, waterproof, hypoallergenic, latex-free. Medium risk: 24-hour, reusable. Low risk: natural look, beginner friendly.",
  mcpSummary:
    "SellerSprite: lash clusters and cluster lashes have the strongest demand. Beginner-friendly and natural look terms show higher purchase intent. Clear band has lower title density. New releases show soft glam, bunny eye and clean girl as rising style modifiers.",
  competitorNotes:
    "Competitor reviews praise easy to apply, natural look and lightweight feel. Negative reviews mention lifting corners, poking, visible band, glue mess and hard removal."
};

let skills = [];
let currentOutputText = "";
let uploadedImages = [];
let imageExtraction = createEmptyExtraction();
let preferences = createDefaultPreferences();
let latestResult = null;
let sellfoxSnapshot = createEmptySellfoxSnapshot();
let riskLibrary = createDefaultRiskLibrary();
let remoteSkillSaveTimer = null;
let remoteSkillSaveInFlight = Promise.resolve();
let activeWorkflowStep = 1;
let listingGenerationInProgress = false;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

document.addEventListener("DOMContentLoaded", () => {
  organizeWorkflowLayout();
  loadSkills();
  loadPreferences();
  loadRiskLibrary();
  bindEvents();
  bindWorkflowEvents();
  const initialSkill = skills.find((item) => item.id === preferences.selectedSkillId) || skills[0];
  syncSkillForm(initialSkill);
  refreshSkillSelect(initialSkill.id);
  renderRiskLibrary();
  renderExtractionReview();
  setFlowState("idle");
  renderPreferences();
  loadSellfoxSnapshot();
  renderSellfoxSnapshot();
  loadSellfoxRankingFile({ silent: true });
  loadRemoteUserState();
  drawTrayPreview();
  renderIcons();
});

function organizeWorkflowLayout() {
  const stageBody = $("#workflowStageBody");
  const abaMount = $("#abaPanelMount");
  const root = $("#workflowRoot");
  [$(".input-panel"), $("#strategyPanel"), $("#outputPanel")]
    .filter(Boolean)
    .forEach((panel) => stageBody?.appendChild(panel));
  const abaPanel = $("#abaRankingContext");
  if (abaPanel && abaMount) abaMount.appendChild(abaPanel);
  root?.classList.add("is-ready");
}

function bindWorkflowEvents() {
  $$('[data-workflow-step]').forEach((button) => {
    button.addEventListener("click", () => {
      const step = Number(button.dataset.workflowStep);
      if (step === 4 && !imageExtraction.confirmed) {
        showToast("先确认图片事实，再生成 Listing");
        setActiveWorkflowStep(1, { scroll: true });
        return;
      }
      setActiveWorkflowStep(step, { scroll: true });
    });
  });

  $$('[data-proxy-action]').forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.proxyAction);
      target?.click();
      const menu = button.closest("details");
      if (menu) menu.open = false;
    });
  });

  $("#workflowPrimaryBtn")?.addEventListener("click", handleWorkflowPrimaryAction);
  $("[data-context-action='aba']")?.addEventListener("click", () => {
    const detail = $("#abaContextDetail");
    if (detail) detail.open = true;
  });

  $("#toggleRiskLibraryBtn")?.addEventListener("click", () => {
    const content = $("#riskLibraryContent");
    if (!content) return;
    content.hidden = !content.hidden;
    $("#toggleRiskLibraryBtn").textContent = content.hidden ? "管理" : "收起";
    renderIcons();
  });

  $("#toggleSkillDetailsBtn")?.addEventListener("click", () => {
    const content = $("#skillDetailContent");
    const box = $(".skill-box");
    if (!content) return;
    content.hidden = !content.hidden;
    box?.classList.toggle("is-expanded", !content.hidden);
    $("#toggleSkillDetailsBtn").textContent = content.hidden ? "编辑" : "收起";
    renderIcons();
  });

  ["t1Keywords", "t2Keywords", "t3Keywords", "skillSelect"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", updateWorkflowContext);
    document.getElementById(id)?.addEventListener("input", updateWorkflowContext);
  });
}

function setActiveWorkflowStep(step, { scroll = false } = {}) {
  const nextStep = Math.min(4, Math.max(1, Number(step) || 1));
  activeWorkflowStep = nextStep;
  const root = $("#workflowRoot");
  if (root) root.dataset.activeStep = String(nextStep);

  $$('.workflow-step').forEach((button) => {
    const buttonStep = Number(button.dataset.workflowStep);
    const active = buttonStep === nextStep;
    button.classList.toggle("is-active", active);
    button.classList.toggle("is-complete", buttonStep < nextStep || (buttonStep === 1 && imageExtraction.confirmed));
    if (active) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  });

  updateWorkflowChrome();
  if (scroll) {
    $("#workflowStageTitle")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function handleWorkflowPrimaryAction() {
  if (listingGenerationInProgress) return;

  if (activeWorkflowStep === 1) {
    if (imageExtraction.status === "uploaded") {
      $("#extractImageBtn")?.click();
      return;
    }
    if (["extracted", "review"].includes(imageExtraction.status)) {
      $("#confirmImageFactsBtn")?.click();
      return;
    }
    if (imageExtraction.confirmed) setActiveWorkflowStep(2, { scroll: true });
    else $("#productImages")?.click();
    return;
  }

  if (activeWorkflowStep === 2) {
    setActiveWorkflowStep(3, { scroll: true });
    return;
  }

  if (activeWorkflowStep === 3) {
    if (!imageExtraction.confirmed) {
      showToast("先完成图片事实确认");
      setActiveWorkflowStep(1, { scroll: true });
      return;
    }
    $("#generateBtn")?.click();
    return;
  }

  if (currentOutputText) $("#copyAllBtn")?.click();
  else if (imageExtraction.confirmed) $("#generateBtn")?.click();
}

function updateWorkflowChrome() {
  const title = $("#workflowStageTitle");
  const description = $("#workflowStageDescription");
  const footerTitle = $("#workflowFooterTitle");
  const footerHint = $("#workflowFooterHint");
  const primary = $("#workflowPrimaryBtn");
  const primaryLabel = $("#workflowPrimaryLabel");
  if (!title || !description || !footerTitle || !footerHint || !primary || !primaryLabel) return;

  let content;
  if (activeWorkflowStep === 1) {
    content = {
      title: "下一步：上传产品图并提取事实",
      description: "上传产品图，系统将识别可见信息并填充为可编辑的产品事实。"
    };
    if (imageExtraction.status === "extracting") {
      content.footer = "正在提取图片事实";
      content.hint = "请稍候，识别完成后可以人工修正。";
      content.action = "正在识别…";
      content.disabled = true;
    } else if (["extracted", "review"].includes(imageExtraction.status)) {
      content.footer = "确认识别出的产品事实";
      content.hint = "可先修正内容，确认后再进入关键词策略。";
      content.action = "确认产品事实";
    } else if (imageExtraction.confirmed) {
      content.footer = "图片事实已确认";
      content.hint = "下一步选择个人 Skill。";
      content.action = "进入关键词与 Skill";
    } else if (!uploadedImages.length) {
      content.footer = "选择并上传产品图片";
      content.hint = "支持 JPG、PNG 和 WEBP，可一次上传多张。";
      content.action = "选择产品图片";
    } else {
      content.footer = "提取图片事实";
      content.hint = "系统将识别包装文字、规格与产品类型。";
      content.action = "提取图片事实";
    }
  } else if (activeWorkflowStep === 2) {
    content = {
      title: "下一步：选择个人 Skill",
      description: "选择最符合当前产品的文案策略，低频编辑功能已收起到“编辑”中。",
      footer: "确认当前 Skill",
      hint: "选择结果会自动按飞书用户保存。",
      action: "进入 ABA 数据策略"
    };
  } else if (activeWorkflowStep === 3) {
    content = {
      title: "下一步：确认关键词与合规策略",
      description: "核对核心词、转化词和场景词，违禁词库详情可按需展开。",
      footer: imageExtraction.confirmed ? "策略已就绪" : "还需确认图片事实",
      hint: imageExtraction.confirmed ? "生成后将返回三版可选 Listing。" : "返回第一步确认产品信息。",
      action: imageExtraction.confirmed ? "生成 Listing 方案" : "返回确认图片事实"
    };
  } else {
    content = {
      title: latestResult ? "Listing 方案已生成" : "下一步：生成 Listing 方案",
      description: "比较三个方向，选择后可复制标题、五点、描述和 Search Terms。",
      footer: latestResult ? "选择并使用 Listing 方案" : "等待生成 Listing",
      hint: latestResult ? "选中方案后可直接复制全部内容。" : "请先完成前面的产品与策略确认。",
      action: latestResult ? "复制当前方案" : "生成 Listing 方案",
      disabled: !imageExtraction.confirmed
    };
  }

  title.textContent = content.title;
  description.textContent = content.description;
  footerTitle.textContent = content.footer;
  footerHint.textContent = content.hint;
  primaryLabel.textContent = content.action;
  primary.disabled = Boolean(content.disabled);
  primary.classList.toggle("is-loading", listingGenerationInProgress);
  if (listingGenerationInProgress) {
    footerTitle.textContent = "正在生成三版 Listing";
    footerHint.textContent = "通常需要十几秒，请保持页面打开。";
    primaryLabel.textContent = "AI 正在生成…";
    primary.disabled = true;
  }
  updateWorkflowContext();
  renderIcons();
}

function updateWorkflowContext() {
  const abaMeta = $("#contextAbaMeta");
  const keywordMeta = $("#contextKeywordMeta");
  const skillMeta = $("#contextSkillMeta");
  if (abaMeta) {
    const count = Number(sellfoxSnapshot.summary?.uniqueTerms || sellfoxSnapshot.rows?.length || 0);
    abaMeta.textContent = count ? `已读取 ${formatNumber(count)} 个词组` : "等待 ABA 排名数据";
  }
  if (keywordMeta) {
    const groups = ["t1Keywords", "t2Keywords", "t3Keywords"]
      .map((id) => parseTerms($("#" + id)?.value || "").length)
      .filter(Boolean).length;
    keywordMeta.textContent = groups ? `已配置 ${groups} 组关键词` : "核心词、扩展词、场景词";
  }
  if (skillMeta) {
    const selected = $("#skillSelect")?.selectedOptions?.[0]?.textContent || "未选择 Skill";
    skillMeta.textContent = `${selected} · ${riskLibrary.length} 个违禁词`;
  }
}

async function loadRemoteUserState() {
  try {
    const response = await fetch(`${LISTING_API_BASE}/user-state`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.message || `读取失败：${response.status}`);

    const savedSkills = Array.isArray(payload.skills)
      ? payload.skills.filter((item) => item && typeof item === "object" && !isBuiltinSkill(item))
      : [];
    skills = [...getBuiltinSkills(), ...savedSkills];
    preferences = {
      ...createDefaultPreferences(),
      ...(payload.preferences && typeof payload.preferences === "object" ? payload.preferences : {})
    };
    preferences.counts = preferences.counts || {};
    riskLibrary = normalizeRiskLibrary(payload.riskLibrary);
    if (!riskLibrary.length) riskLibrary = createDefaultRiskLibrary();

    const selectedSkill = skills.find((item) => item.id === preferences.selectedSkillId)
      || skills.find((item) => !isBuiltinSkill(item))
      || skills[0];
    refreshSkillSelect(selectedSkill.id);
    syncSkillForm(selectedSkill);
    renderRiskLibrary();
    renderPreferences();
    $("#skillState").textContent = payload.updatedAt ? "已从 Skills 文件读取" : "等待保存到 Skills 文件";
    $("#skillState").title = payload.skillPath || "";
    if (!payload.updatedAt) await persistRemoteUserState({ quiet: true });
    updateWorkflowContext();
  } catch (error) {
    $("#skillState").textContent = "服务器偏好读取失败，当前使用内置 Skill";
    $("#skillState").title = error.message || "";
  }
}

function scheduleRemoteUserStateSave() {
  window.clearTimeout(remoteSkillSaveTimer);
  remoteSkillSaveTimer = window.setTimeout(() => {
    persistRemoteUserState({ quiet: true }).catch(() => {});
  }, 250);
}

async function persistRemoteUserState({ quiet = false } = {}) {
  window.clearTimeout(remoteSkillSaveTimer);
  const userSkills = skills.filter((item) => !isBuiltinSkill(item));
  const task = async () => {
    const response = await fetch(`${LISTING_API_BASE}/user-state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skills: userSkills, preferences, riskLibrary })
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.message || `保存失败：${response.status}`);
    $("#skillState").textContent = "已保存到 Skills 文件";
    $("#skillState").title = payload.skillPath || "";
    if (!quiet) showToast("偏好 Skill 已保存到服务器文件");
    return payload;
  };
  remoteSkillSaveInFlight = remoteSkillSaveInFlight.then(task, task);
  try {
    return await remoteSkillSaveInFlight;
  } catch (error) {
    $("#skillState").textContent = "服务器保存失败";
    $("#skillState").title = error.message || "";
    throw error;
  }
}

function bindEvents() {
  $("#generateBtn").addEventListener("click", async () => {
    if (!imageExtraction.confirmed) {
      setFlowState("review");
      $("#recognitionStage")?.scrollIntoView({ behavior: "smooth", block: "start" });
      showToast("请先完成图片识别并确认结果，再进行判断和生成");
      renderExtractionReview();
      return;
    }

    const data = collectForm();
    const skill = collectSkill();
    setListingGenerationState(true);

    try {
      await persistRemoteUserState({ quiet: true });
      const baseResult = generateListing(data, skill);
      const aiPayload = buildAiListingPayload(data, skill);
      const aiResponse = await requestAiListings(aiPayload);
      const result = mergeAiListingResult(baseResult, aiResponse, data, skill);
      latestResult = result;
      renderResult(result);
      setFlowState("done");
      if (aiResponse.storage?.persistenceFailed) {
        showToast(`AI 已生成 3 个 Listing 方案，可先复制；自动存档失败：${aiResponse.storage.message || "未知原因"}`);
      } else {
        showToast(
          aiResponse.storage?.storedAs === "file"
            ? "AI 已生成 3 个 Listing 方案，长文案已存档并记录"
            : "AI 已生成 3 个 Listing 方案并写入数据库"
        );
      }
    } catch (error) {
      showToast(formatListingGenerationError(error.message));
    } finally {
      setListingGenerationState(false);
    }
  });

  $("#sampleBtn").addEventListener("click", () => {
    fillSampleData();
    drawTrayPreview();
    showToast("示例识别结果已填入，请确认后进入判断");
  });

  $("#clearBtn").addEventListener("click", () => {
    $("#listingForm").reset();
    ["t1Keywords", "t2Keywords", "t3Keywords", "forbiddenRankings", "mcpSummary", "competitorNotes"].forEach((id) => {
      $(`#${id}`).value = "";
    });
    $("#imagePreview").innerHTML = "";
    uploadedImages = [];
    imageExtraction = createEmptyExtraction();
    renderExtractionReview();
    drawTrayPreview();
    setFlowState("idle");
    showToast("表单已清空");
  });

  $("#saveSkillBtn").addEventListener("click", () => saveCurrentSkill());
  $("#newSkillBtn").addEventListener("click", startNewSkillDraft);
  $("#createSkillFromListingBtn").addEventListener("click", createSkillFromListing);

  $("#exportSkillBtn").addEventListener("click", () => {
    const skill = collectSkill();
    const content = buildSkillMarkdown(skill);
    downloadText(`${slugify(skill.name)}.md`, content);
    showToast("Skill Markdown 已导出");
  });

  $("#buildSkillBtn").addEventListener("click", () => {
    const skill = collectSkill();
    const skillSummary = {
      title: "当前 Skill 摘要",
      metric: `${skill.titleLimit} title / ${skill.searchTermLimit} ST bytes`,
      content: buildSkillMarkdown(skill)
    };
    renderBlocks([skillSummary]);
    currentOutputText = skillSummary.content;
    $("#skillState").textContent = "已刷新";
    showToast("Skill 摘要已刷新");
  });

  $("#skillSelect").addEventListener("change", (event) => {
    const skill = skills.find((item) => item.id === event.target.value);
    if (skill) {
      syncSkillForm(skill);
      $("#skillState").textContent = isBuiltinSkill(skill) ? "内置模板" : "已加载";
      preferences.selectedSkillId = skill.id;
      preferences.updatedAt = new Date().toISOString();
      savePreferences();
    }
  });

  $("#copyAllBtn").addEventListener("click", async () => {
    if (!currentOutputText) {
      showToast("还没有可复制的内容");
      return;
    }
    try {
      await navigator.clipboard.writeText(currentOutputText);
      showToast("已复制全部结果");
    } catch {
      fallbackCopy(currentOutputText);
      showToast("已复制全部结果");
    }
  });

  $("#resultArea").addEventListener("click", handleResultAreaClick);
  $("#productImages").addEventListener("change", previewImages);
  $("#extractImageBtn").addEventListener("click", extractImageFacts);
  $("#confirmImageFactsBtn").addEventListener("click", confirmImageFacts);
  $("#syncSellfoxBtn").addEventListener("click", syncSellfoxRankings);
  $("#addRiskTermBtn").addEventListener("click", addRiskTerm);
  $("#riskLibrary").addEventListener("click", handleRiskLibraryClick);
  $("#riskTermInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addRiskTerm();
    }
  });

  ["lengths", "pieceCount", "styleAngle", "curl", "bandType"].forEach((id) => {
    $(`#${id}`).addEventListener("input", drawTrayPreview);
    $(`#${id}`).addEventListener("change", drawTrayPreview);
  });

  ["skillName", "titleStrategy", "tone", "bulletPattern", "forbiddenClaims", "customRules", "listingReference"].forEach((id) => {
    $(`#${id}`).addEventListener("input", () => {
      $("#skillState").textContent = "未保存更改";
    });
  });
}

function loadSkills() {
  skills = getBuiltinSkills();
}

function saveSkills() {
  scheduleRemoteUserStateSave();
}

function saveCurrentSkill({ forceNew = false, silent = false } = {}) {
  const skill = collectSkill();
  const selectedId = forceNew ? DEFAULT_SKILL.id : $("#skillSelect").value;
  const existingIndex = skills.findIndex((item) => item.id === selectedId && !isBuiltinSkill(item));
  let savedSkill;

  if (existingIndex >= 0 && !forceNew) {
    savedSkill = { ...skills[existingIndex], ...skill, id: selectedId };
    skills[existingIndex] = savedSkill;
  } else {
    savedSkill = {
      ...skill,
      id: `skill-${Date.now()}`,
      name: isBuiltinSkill(selectedId) ? `${skill.name} （个人）` : skill.name
    };
    skills.push(savedSkill);
  }

  saveSkills();
  refreshSkillSelect(savedSkill.id);
  preferences.selectedSkillId = savedSkill.id;
  savePreferences();
  $("#skillState").textContent = "正在保存到 Skills 文件";
  if (!silent) showToast("Skill 正在保存到服务器文件");
  return savedSkill;
}

function startNewSkillDraft() {
  syncSkillForm({ ...DEFAULT_SKILL, name: "", referenceListing: "" });
  $("#skillSelect").value = DEFAULT_SKILL.id;
  $("#skillState").textContent = "新建草稿，命名后保存";
  $("#skillName").focus();
  showToast("已创建新的 Skill 草稿");
}

function createSkillFromListing() {
  const reference = cleanText($("#listingReference").value);
  if (!reference) {
    showToast("请先粘贴历史 Listing 文案");
    return;
  }

  const requestedName = cleanText($("#skillName").value);
  const inferred = inferSkillFromListing(reference);
  const generatedSkill = {
    ...DEFAULT_SKILL,
    ...inferred,
    name: requestedName || `历史 Listing 复盘 Skill ${new Date().toLocaleDateString("zh-CN")}`,
    referenceListing: reference
  };

  syncSkillForm(generatedSkill);
  $("#listingReference").value = reference;
  const savedSkill = saveCurrentSkill({ forceNew: true, silent: true });
  $("#skillState").textContent = "已由历史文案生成并保存";
  showToast(`已新建 Skill：${savedSkill.name}`);
}

function inferSkillFromListing(reference) {
  const lower = reference.toLowerCase();
  const title = extractListingTitle(reference);
  const titleLower = title.toLowerCase();
  const currentBrand = cleanText($("#brandName").value).toLowerCase();
  const keywordPosition = titleLower.search(/lash|lashes|eyelash|eyelashes|cluster|false lash/);
  const titleStrategy = currentBrand && titleLower.startsWith(currentBrand)
    ? "brandFirst"
    : keywordPosition >= 0 && keywordPosition <= 24
      ? "keywordFirst"
      : "styleFirst";
  const tone = /premium|luxury|elegant|soft glam|精致|高级|轻柔/.test(lower)
    ? "premium soft"
    : /buy|shop|must-have|easy to apply|beginner|立即|新手|快速/.test(lower)
      ? "direct conversion"
      : /minimal|clean|simple|clean girl|极简|干净/.test(lower)
        ? "clean minimal"
        : "beauty factual";
  const bulletPattern = /step\s*\d|how to|routine|apply|先.*再|使用步骤|使用方法/.test(lower)
    ? "routineFirst"
    : /lift|poking|glue mess|hard removal|翘边|扎眼|痛点|不易贴/.test(lower)
      ? "painSolutionScene"
      : "benefitSpecScene";
  const riskHits = riskLibrary
    .map((item) => item.term)
    .filter((term) => lower.includes(term.toLowerCase()));
  const titleLength = Array.from(title).length;
  const notes = [
    `历史 Listing 复盘：标题约 ${titleLength || 0} 个字符，标题顺序、语气和五点结构已按原文提炼。`,
    riskHits.length ? `原文出现高风险或受限表达：${riskHits.join(", ")}；后续生成默认不复用。` : "原文未命中已启用的违禁词库；仍须以包装、资质和平台规则复核。"
  ];

  return {
    titleStrategy,
    tone,
    bulletPattern,
    customRules: `${DEFAULT_SKILL.customRules}；${notes.join("；")}`,
    forbiddenClaims: unique([...parseTerms(DEFAULT_SKILL.forbiddenClaims), ...riskHits]).join(", ")
  };
}

function extractListingTitle(reference) {
  const labelled = reference.match(/(?:^|\n)\s*(?:title|标题)\s*[:：]\s*(.+)/i);
  if (labelled?.[1]) return cleanText(labelled[1]);
  return cleanText(reference.split(/\n+/).find((line) => cleanText(line)) || "");
}

function createDefaultPreferences() {
  return {
    counts: {},
    totalChoices: 0,
    selectedSkillId: "",
    lastVariantId: "",
    lastVariantName: "",
    lastTone: "",
    lastBulletPattern: "",
    lastStyleAngle: "",
    updatedAt: ""
  };
}

function createDefaultSkillLearning() {
  return {
    selectionCounts: {},
    recentSelections: [],
    feedback: [],
    learnedRules: [],
    updatedAt: ""
  };
}

function getSkillLearning(skill) {
  const source = skill?.learning && typeof skill.learning === "object" ? skill.learning : {};
  return {
    ...createDefaultSkillLearning(),
    ...source,
    selectionCounts: source.selectionCounts && typeof source.selectionCounts === "object" ? source.selectionCounts : {},
    recentSelections: Array.isArray(source.recentSelections) ? source.recentSelections.slice(0, 12) : [],
    feedback: Array.isArray(source.feedback) ? source.feedback.slice(0, 12) : [],
    learnedRules: Array.isArray(source.learnedRules) ? source.learnedRules.map(cleanText).filter(Boolean).slice(0, 12) : []
  };
}

function loadPreferences() {
  preferences = createDefaultPreferences();
}

function savePreferences() {
  scheduleRemoteUserStateSave();
}

function createDefaultRiskLibrary() {
  return DEFAULT_RISK_LIBRARY.map((item) => ({ ...item }));
}

function loadRiskLibrary() {
  riskLibrary = createDefaultRiskLibrary();
}

function normalizeRiskLibrary(items) {
  if (!Array.isArray(items)) return [];
  const seen = new Set();
  return items
    .map((item) => ({
      term: cleanText(item?.term).toLowerCase(),
      level: item?.level === "medium" ? "medium" : "high"
    }))
    .filter((item) => item.term && !seen.has(item.term) && seen.add(item.term));
}

function saveRiskLibrary() {
  scheduleRemoteUserStateSave();
}

function buildRiskLibraryText() {
  const high = riskLibrary.filter((item) => item.level === "high").map((item) => item.term);
  const medium = riskLibrary.filter((item) => item.level === "medium").map((item) => item.term);
  return [
    high.length && `High risk: ${high.join(", ")}.`,
    medium.length && `Medium risk: ${medium.join(", ")}.`
  ].filter(Boolean).join("\n");
}

function syncRiskLibraryToSkillField() {
  const field = $("#forbiddenClaims");
  if (!field) return;
  field.value = unique(parseTerms(field.value)).join(", ");
}

function renderRiskLibrary() {
  const container = $("#riskLibrary");
  const count = $("#riskLibraryCount");
  if (!container || !count) return;
  const groups = [
    ["high", "高风险", "未有包装、检测或资质证据时直接拦截"],
    ["medium", "中风险", "可用前需补充品牌或商品证明"]
  ];
  container.innerHTML = groups.map(([level, label, note]) => {
    const entries = riskLibrary.filter((item) => item.level === level);
    return `
      <div class="risk-group">
        <div class="risk-group-head"><strong>${label} ${entries.length} 个</strong><span>${note}</span></div>
        <div class="risk-chip-list">
          ${entries.map((item) => `<span class="risk-chip ${level === "medium" ? "medium" : ""}"><span>${escapeHtml(item.term)}</span><button type="button" data-remove-risk-term="${escapeHtml(item.term)}" title="删除 ${escapeHtml(item.term)}" aria-label="删除 ${escapeHtml(item.term)}"><i data-lucide="minus"></i></button></span>`).join("")}
        </div>
      </div>`;
  }).join("");
  count.textContent = `${riskLibrary.length} 个已启用`;
  syncRiskLibraryToSkillField();
  updateWorkflowContext();
  renderIcons();
}

function addRiskTerm() {
  const input = $("#riskTermInput");
  const level = $("#riskLevel").value;
  const term = cleanText(input.value).toLowerCase();
  if (!term) {
    input.focus();
    return;
  }
  if (riskLibrary.some((item) => item.term.toLowerCase() === term)) {
    showToast("该词已在违禁词库中");
    input.focus();
    return;
  }
  riskLibrary.push({ term, level: level === "medium" ? "medium" : "high" });
  input.value = "";
  saveRiskLibrary();
  renderRiskLibrary();
  $("#skillState").textContent = "未保存更改";
  showToast("已加入违禁词库");
}

function handleRiskLibraryClick(event) {
  const button = event.target.closest("[data-remove-risk-term]");
  if (!button) return;
  const term = button.dataset.removeRiskTerm;
  riskLibrary = riskLibrary.filter((item) => item.term !== term);
  saveRiskLibrary();
  renderRiskLibrary();
  $("#skillState").textContent = "未保存更改";
  showToast(`已移除 ${term}`);
}

function handleResultAreaClick(event) {
  const feedbackButton = event.target.closest("[data-submit-listing-feedback]");
  if (feedbackButton && latestResult) {
    const feedback = cleanText($("#listingFeedbackInput")?.value);
    if (!feedback) {
      showToast("请先填写希望改进的问题");
      return;
    }
    const selected = latestResult.variants.find((variant) => variant.id === latestResult.selectedVariantId)
      || latestResult.variants[0];
    recordSkillLearning(selected, collectForm(), feedback, false);
    $("#listingFeedbackInput").value = "";
    showToast("问题反馈已提炼并写入当前 Skill");
    return;
  }

  const button = event.target.closest("[data-variant-id]");
  if (!button || !latestResult) return;

  const variant = latestResult.variants.find((item) => item.id === button.dataset.variantId);
  if (!variant) return;

  latestResult.selectedVariantId = variant.id;
  rememberVariantPreference(variant, collectForm());
  recordSkillLearning(variant, collectForm());
  renderResult(latestResult);
  renderPreferences();
  showToast(`已采用${variant.name}，偏好已记住`);
}

function ensureSkillLearningTarget() {
  const selectedId = $("#skillSelect").value;
  let skill = skills.find((item) => item.id === selectedId && !isBuiltinSkill(item));
  if (skill) return skill;

  const draft = collectSkill();
  skill = {
    ...draft,
    id: `skill-${Date.now()}`,
    name: cleanText(draft.name) && draft.name !== DEFAULT_SKILL.name ? draft.name : "我的 Listing Skill",
    learning: createDefaultSkillLearning()
  };
  skills.push(skill);
  refreshSkillSelect(skill.id);
  syncSkillForm(skill);
  return skill;
}

function recordSkillLearning(variant, data, feedback = "", countSelection = true) {
  const skill = ensureSkillLearningTarget();
  const learning = getSkillLearning(skill);
  const now = new Date().toISOString();
  const profile = VARIANT_PROFILES.find((item) => item.id === variant.id) || variant;

  if (countSelection) {
    learning.selectionCounts[variant.id] = (learning.selectionCounts[variant.id] || 0) + 1;
    learning.recentSelections = [
      {
        variantId: variant.id,
        variantName: variant.name,
        tone: variant.tone,
        bulletPattern: variant.bulletPattern,
        style: data.styleAngle,
        at: now
      },
      ...learning.recentSelections
    ].slice(0, 12);

    const selectionRule = `偏好 ${variant.name}：${labelTone(variant.tone)}语气、${labelBulletPattern(variant.bulletPattern)}。`;
    learning.learnedRules = unique([...learning.learnedRules, selectionRule]).slice(-12);
  }

  if (feedback) {
    const feedbackRule = summarizeFeedbackRule(feedback, profile);
    learning.feedback = [{ text: feedback, rule: feedbackRule, at: now }, ...learning.feedback].slice(0, 12);
    learning.learnedRules = unique([...learning.learnedRules, feedbackRule]).slice(-12);
  }

  learning.updatedAt = now;
  skill.learning = learning;
  saveSkills();
  refreshSkillSelect(skill.id);
  renderSkillLearningSummary(skill);
}

function summarizeFeedbackRule(feedback, variant) {
  const lower = feedback.toLowerCase();
  const refinements = [];
  if (/标题|title/.test(lower)) refinements.push("标题表达需要优先按该反馈调整");
  if (/太长|简短|精简|short/.test(lower)) refinements.push("文案应更精简，先保留核心词和已确认规格");
  if (/太硬|生硬|自然|柔和|soft/.test(lower)) refinements.push("语气应更自然、克制，避免生硬促销");
  if (/卖点|五点|bullet/.test(lower)) refinements.push("五点需要更贴近真实使用场景和购买顾虑");
  if (/关键词|aba|排名|search/.test(lower)) refinements.push("关键词需优先遵循 ABA 相关性与排名信号");
  const rule = refinements.length ? refinements.join("；") : `下次生成请遵循反馈：${feedback}`;
  return `针对 ${variant.name} 的反馈：${rule}。`;
}

function renderSkillLearningSummary(skill) {
  const panel = $("#skillLearningSummary");
  if (!panel) return;
  const learning = getSkillLearning(skill || skills.find((item) => item.id === $("#skillSelect").value));
  const totalChoices = Object.values(learning.selectionCounts).reduce((total, count) => total + Number(count || 0), 0);

  if (!totalChoices && !learning.feedback.length) {
    panel.innerHTML = `<span>这个 Skill 还没有学习记录。采用方案或提交问题反馈后，会逐步形成你的文案偏好。</span>`;
    return;
  }

  const favoriteId = Object.entries(learning.selectionCounts).sort((a, b) => b[1] - a[1])[0]?.[0];
  const favorite = VARIANT_PROFILES.find((item) => item.id === favoriteId);
  panel.innerHTML = `
    <strong>个人化学习</strong>
    <div>
      <span>已采用 ${totalChoices} 次</span>
      <span>常选：${escapeHtml(favorite?.name || "待形成")}</span>
      <span>反馈 ${learning.feedback.length} 条</span>
    </div>
    ${learning.learnedRules.length ? `<p>${escapeHtml(learning.learnedRules.slice(-2).join(" "))}</p>` : ""}`;
}

function rememberVariantPreference(variant, data) {
  preferences.counts[variant.id] = (preferences.counts[variant.id] || 0) + 1;
  preferences.totalChoices += 1;
  preferences.lastVariantId = variant.id;
  preferences.lastVariantName = variant.name;
  preferences.lastTone = variant.tone;
  preferences.lastBulletPattern = variant.bulletPattern;
  preferences.lastStyleAngle = data.styleAngle;
  preferences.updatedAt = new Date().toISOString();
  savePreferences();
}

function renderPreferences() {
  const panel = $("#preferencePanel");
  if (!panel) return;

  const favorite = getFavoriteVariant();
  if (!preferences.totalChoices) {
    panel.innerHTML = `
      <div>
        <strong>偏好记忆</strong>
        <p>选择某个生成方案后，这里会记录你更偏好的 Listing 方向。</p>
      </div>
      <div class="preference-chips">
        <span>等待选择</span>
        <span>按飞书用户保存</span>
      </div>`;
    return;
  }

  panel.innerHTML = `
    <div>
      <strong>偏好记忆</strong>
      <p>已记录 ${preferences.totalChoices} 次选择，推荐排序会参考这些偏好。</p>
    </div>
    <div class="preference-chips">
      <span>常选：${escapeHtml(favorite?.name || "未形成")}</span>
      <span>最近：${escapeHtml(preferences.lastVariantName || "无")}</span>
      <span>语气：${escapeHtml(labelTone(preferences.lastTone))}</span>
      <span>结构：${escapeHtml(labelBulletPattern(preferences.lastBulletPattern))}</span>
      <span>风格：${escapeHtml(titleCase(preferences.lastStyleAngle || "待观察"))}</span>
    </div>`;
}

function getFavoriteVariant() {
  const favoriteId = Object.entries(preferences.counts || {}).sort((a, b) => b[1] - a[1])[0]?.[0];
  return VARIANT_PROFILES.find((profile) => profile.id === favoriteId);
}

function createEmptySellfoxSnapshot() {
  return {
    rows: [],
    request: {},
    summary: {},
    fetchedAt: "",
    source: ""
  };
}

function loadSellfoxSnapshot() {
  try {
    const saved = JSON.parse(localStorage.getItem(SELLFOX_STORAGE_KEY) || "null");
    if (saved && Array.isArray(saved.rows)) sellfoxSnapshot = { ...createEmptySellfoxSnapshot(), ...saved };
  } catch {
    sellfoxSnapshot = createEmptySellfoxSnapshot();
  }
}

function saveSellfoxSnapshot() {
  try {
    localStorage.setItem(
      SELLFOX_STORAGE_KEY,
      JSON.stringify({ ...sellfoxSnapshot, rows: [] })
    );
  } catch {
    localStorage.removeItem(SELLFOX_STORAGE_KEY);
  }
}

function setSellfoxConnection(state, text) {
  const status = $("#sellfoxConnection");
  if (!status) return;
  status.dataset.state = state;
  status.textContent = text;
}

async function syncSellfoxRankings() {
  await loadSellfoxRankingFile();
}

async function loadSellfoxRankingFile(options = {}) {
  setSellfoxConnection("loading", "读取看板中");
  $("#syncSellfoxBtn").disabled = true;
  $("#sellfoxSnapshot").classList.add("empty");
  $("#sellfoxSnapshot").textContent = "正在读取已绑定 ABA 综合排名看板中的完整数据。";

  try {
    const response = await fetch(`${LISTING_API_BASE}/sellfox/ranking-file`, { cache: "no-store" });
    const payload = await response.json();
    sellfoxSnapshot = {
      rows: Array.isArray(payload.rows) ? payload.rows : [],
      request: { dateRange: payload.meta?.dateRange || "" },
      summary: payload.summary || {},
      fetchedAt: payload.updatedAt || new Date().toISOString(),
      source: payload.source || "ABA 四核心词综合排名看板"
    };
    if (!response.ok || !payload.ok || !sellfoxSnapshot.rows.length) throw new Error(payload.message || "看板中没有可用排名数据");
    saveSellfoxSnapshot();
    fillEmptyKeywordInputsFromSellfox();
    renderSellfoxSnapshot();
    renderAbaImportSource();
    $("#syncSellfoxBtn").disabled = false;
    setSellfoxConnection("ok", `已读取 ${sellfoxSnapshot.rows.length} 个词组`);
    if (!options.silent) showToast("已读取 ABA 看板，生成会使用真实排名、增长与点击/转化信号");
  } catch (error) {
    $("#syncSellfoxBtn").disabled = false;
    setSellfoxConnection("error", "读取失败");
  if (!sellfoxSnapshot.rows.length) renderSellfoxSnapshot();
    if (!options.silent) showToast(error.message || "ABA 看板读取失败");
  }
}

function renderAbaImportSource() {
  const source = $("#abaImportSource");
  if (!source) return;
  const count = Number(sellfoxSnapshot.summary?.uniqueTerms || sellfoxSnapshot.rows.length || 0);
  source.innerHTML = `<i data-lucide="database"></i> 当前数据：${escapeHtml(sellfoxSnapshot.source || "内置 ABA 排名数据")} · ${count.toLocaleString("zh-CN")} 个搜索词`;
  renderIcons();
}

function fillEmptyKeywordInputsFromSellfox() {
  const data = collectForm();
  const plan = buildSellfoxKeywordPlan(data);
  if (!$("#t1Keywords").value.trim() && plan.titleTerms.length) {
    $("#t1Keywords").value = plan.titleTerms.slice(0, 3).map((item) => item.term).join(", ");
  }
  if (!$("#t2Keywords").value.trim() && plan.conversionTerms.length) {
    $("#t2Keywords").value = plan.conversionTerms.slice(0, 3).map((item) => item.term).join(", ");
  }
}

function renderSellfoxSnapshot() {
  const container = $("#sellfoxSnapshot");
  if (!container) return;
  const rows = normalizeSellfoxRows(sellfoxSnapshot.rows);
  if (!rows.length) {
    container.className = "sellfox-snapshot empty";
    container.textContent = "尚未同步赛虎排名。你仍可手动填写 ABA 数据；同步后会自动过滤与当前产品无关的词。";
    updateWorkflowContext();
    return;
  }
  const plan = buildSellfoxKeywordPlan(collectForm());
  const rankingTerm = plan.titleTerms[0];
  const growthTerm = firstDistinctSellfoxTerm(plan.growthTerms, [rankingTerm]);
  const conversionTerm = firstDistinctSellfoxTerm(plan.conversionTerms, [rankingTerm, growthTerm]);
  const visible = [
    ["排名优先", rankingTerm],
    ["增长机会", growthTerm],
    ["转化承接", conversionTerm]
  ].filter(([, item]) => item);
  container.className = "sellfox-snapshot";
  container.innerHTML = `
    <div class="sellfox-snapshot-head">
      <strong>已同步 ${rows.length} 个词组，${plan.relevantRows.length} 个与当前产品相关</strong>
      <span>${escapeHtml(formatSellfoxSnapshotDate(sellfoxSnapshot))}</span>
    </div>
    <div class="sellfox-keyword-grid">
      ${visible.map(([label, item]) => `<div class="sellfox-keyword"><strong>${escapeHtml(label)}：${escapeHtml(item.term)}</strong><span>当前 #${formatNumber(item.rank)} · 上期 #${formatNumber(item.previousRank)} · ${formatGrowth(item.growth)} · 点击 ${formatShare(item.clickShare)} / 转化 ${formatShare(item.conversionShare)}</span></div>`).join("")}
    </div>`;
  updateWorkflowContext();
}

function formatSellfoxSnapshotDate(snapshot) {
  const request = snapshot.request || {};
  if (request.dateRange) return request.dateRange;
  if (request.startDate && request.endDate) return `${request.startDate} 至 ${request.endDate}`;
  return snapshot.fetchedAt ? `同步于 ${new Date(snapshot.fetchedAt).toLocaleString("zh-CN", { hour12: false })}` : "";
}

function refreshSkillSelect(selectedValue) {
  const select = $("#skillSelect");
  const hasSelectedId = selectedValue && skills.some((skill) => skill.id === selectedValue);
  select.innerHTML = "";
  skills.forEach((skill) => {
    const option = document.createElement("option");
    option.value = skill.id;
    option.textContent = skill.name;
    if ((hasSelectedId && skill.id === selectedValue) || (!hasSelectedId && selectedValue && skill.name === selectedValue)) {
      option.selected = true;
    }
    select.appendChild(option);
  });
  updateWorkflowContext();
}

function syncSkillForm(skill) {
  $("#skillName").value = skill.name;
  $("#titleStrategy").value = skill.titleStrategy;
  $("#tone").value = skill.tone;
  $("#bulletPattern").value = skill.bulletPattern;
  $("#forbiddenClaims").value = skill.forbiddenClaims;
  $("#customRules").value = skill.customRules;
  $("#listingReference").value = skill.referenceListing || "";
  syncRiskLibraryToSkillField();
  renderSkillLearningSummary(skill);
  updateWorkflowContext();
}

function collectSkill() {
  const selectedSkill = skills.find((item) => item.id === $("#skillSelect").value);
  return {
    id: $("#skillSelect").value || `skill-${Date.now()}`,
    name: cleanText($("#skillName").value) || "Untitled Listing Skill",
    titleStrategy: $("#titleStrategy").value,
    tone: $("#tone").value,
    bulletPattern: $("#bulletPattern").value,
    titleLimit: 75,
    itemHighlightLimit: 125,
    bulletLimit: 500,
    descriptionLimit: 2000,
    searchTermLimit: 249,
    referenceListing: cleanText($("#listingReference").value),
    learning: getSkillLearning(selectedSkill),
    forbiddenClaims: unique([...parseTerms($("#forbiddenClaims").value), ...riskLibrary.map((item) => item.term)]).join(", "),
    customRules: cleanText($("#customRules").value)
  };
}

function buildLinkedAbaRankingText() {
  const rows = normalizeSellfoxRows(sellfoxSnapshot.rows)
    .filter((row) => row.rank <= 30000)
    .sort((a, b) => a.rank - b.rank)
    .slice(0, 12);
  return rows.map((row) => `#${row.rank} ${row.term}`).join("; ");
}

function collectForm() {
  return {
    marketplace: $("#marketplace").value,
    brandName: cleanText($("#brandName").value),
    productType: $("#productType").value,
    styleAngle: $("#styleAngle").value,
    lengths: getSelectedLengthsText(),
    curl: cleanText($("#curl").value),
    bandType: $("#bandType").value,
    pieceCount: cleanText($("#pieceCount").value),
    contents: checkedValues("contents"),
    verifiedClaims: checkedValues("verifiedClaims"),
    imageFacts: cleanText($("#imageFacts").value),
    imageExtractionConfirmed: imageExtraction.confirmed,
    imageExtractionNeeds: imageExtraction.needs || [],
    t1Keywords: parseTerms($("#t1Keywords").value),
    t2Keywords: parseTerms($("#t2Keywords").value),
    t3Keywords: parseTerms($("#t3Keywords").value),
    abaRankings: buildLinkedAbaRankingText(),
    forbiddenRankings: [cleanText($("#forbiddenRankings").value), buildRiskLibraryText()].filter(Boolean).join("\n"),
    mcpSummary: cleanText($("#mcpSummary").value),
    competitorNotes: cleanText($("#competitorNotes").value),
    sellfoxSnapshot
  };
}

function checkedValues(name) {
  return $$(`input[name="${name}"]:checked`).map((input) => input.value);
}

function getSelectedLengthsText() {
  return checkedValues("lengths").join("/");
}

function setSelectedLengthOptions(value) {
  const selected = new Set(extractLengthOptions(value));
  $$('input[name="lengths"]').forEach((input) => {
    input.checked = selected.has(input.value);
  });
}

function extractLengthOptions(value) {
  const text = cleanText(value).toLowerCase();
  const lengths = new Set();
  const addLength = (numberLike) => {
    const number = Number(numberLike);
    if (number >= 4 && number <= 25) lengths.add(`${number}mm`);
  };

  const rangePattern = /(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*mm/g;
  let rangeMatch = rangePattern.exec(text);
  while (rangeMatch) {
    const start = Number(rangeMatch[1]);
    const end = Number(rangeMatch[2]);
    const low = Math.min(start, end);
    const high = Math.max(start, end);
    for (let number = low; number <= high; number += 1) addLength(number);
    rangeMatch = rangePattern.exec(text);
  }

  const groupedPattern = /((?:\d{1,2}\s*(?:\/|,|，|;|；|\s+)\s*)+\d{1,2})\s*mm/g;
  let groupedMatch = groupedPattern.exec(text);
  while (groupedMatch) {
    (groupedMatch[1].match(/\d{1,2}/g) || []).forEach(addLength);
    groupedMatch = groupedPattern.exec(text);
  }

  const explicitPattern = /(\d{1,2})\s*mm/g;
  let explicitMatch = explicitPattern.exec(text);
  while (explicitMatch) {
    addLength(explicitMatch[1]);
    explicitMatch = explicitPattern.exec(text);
  }

  return Array.from(lengths).sort((a, b) => Number(a) - Number(b));
}

function fillSampleData() {
  Object.entries(SAMPLE_DATA).forEach(([key, value]) => {
    const field = $(`#${key}`);
    if (field && typeof value === "string" && key !== "lengths") {
      field.value = value;
    }
  });

  setSelectedLengthOptions(SAMPLE_DATA.lengths);
  $$('input[name="contents"]').forEach((input) => {
    input.checked = SAMPLE_DATA.contents.includes(input.value);
  });
  $$('input[name="verifiedClaims"]').forEach((input) => {
    input.checked = SAMPLE_DATA.verifiedClaims.includes(input.value);
  });

  imageExtraction = {
    status: "extracted",
    confirmed: false,
    facts: [
      { key: "brandName", label: "品牌", value: SAMPLE_DATA.brandName, source: "示例包装文字", confidence: "高" },
      { key: "productType", label: "产品类型", value: SAMPLE_DATA.productType, source: "示例产品图", confidence: "高" },
      { key: "lengths", label: "长度", value: SAMPLE_DATA.lengths, source: "示例托盘标签", confidence: "高" },
      { key: "curl", label: "卷度", value: SAMPLE_DATA.curl, source: "示例托盘标签", confidence: "高" },
      { key: "bandType", label: "带型", value: SAMPLE_DATA.bandType, source: "示例产品图", confidence: "中" },
      { key: "pieceCount", label: "根数", value: SAMPLE_DATA.pieceCount, source: "示例包装文字", confidence: "高" }
    ],
    needs: ["示例中的套装包含物仍需要根据包装或 SKU 信息确认。"],
    blocked: ["不要仅凭产品图写入防水、低敏、无乳胶或可复用次数等声明。"],
    source: "示例识别结果"
  };
  renderExtractionReview();
  setFlowState("extracted");
}

function normalizeSellfoxRows(rows) {
  return (Array.isArray(rows) ? rows : [])
    .map((row) => {
      const term = cleanText(row.searchTerm || row.keyword || row.term);
      const rank = numericValue(row.searchFrequencyRank || row.rank);
      const previousRank = numericValue(row.lastSearchFrequencyRank || row.previousSearchFrequencyRank || row.lastRank);
      if (!term || !Number.isFinite(rank)) return null;
      return {
        term,
        rank,
        previousRank: Number.isFinite(previousRank) ? previousRank : null,
        growth: Number.isFinite(previousRank) ? previousRank - rank : null,
        clickShare: shareValue(row.top3AsinClickShare || row.top3ASINClickShare || row.clickShare),
        conversionShare: shareValue(row.top3AsinConversionShare || row.top3ASINConversionShare || row.conversionShare),
        matchedKeyword: cleanText(row.matchedKeyword),
        topAsins: row.top3AsinList || row.topAsins || row.asins || [],
        topBrands: Array.isArray(row.topBrands) ? row.topBrands.map(cleanText).filter(Boolean) : [],
        raw: row
      };
    })
    .filter(Boolean);
}

function numericValue(value) {
  if (typeof value === "number") return value;
  const normalized = String(value ?? "").replace(/[,#\s]/g, "");
  const number = Number(normalized);
  return Number.isFinite(number) ? number : NaN;
}

function shareValue(value) {
  if (typeof value === "number") return value > 1 ? value / 100 : value;
  const text = String(value ?? "").trim();
  if (!text) return 0;
  const number = Number(text.replace(/[%\s]/g, ""));
  if (!Number.isFinite(number)) return 0;
  return text.includes("%") || number > 1 ? number / 100 : number;
}

function productTermRelevance(term, productType) {
  const source = ` ${String(term || "").toLowerCase()} `;
  const type = String(productType || "").toLowerCase();
  const contains = (value) => source.includes(value);
  let score = 0;
  const reasons = [];

  if (type.includes("clusters")) {
    if (contains("cluster")) { score += 7; reasons.push("包含 cluster"); }
    if (contains("individual")) { score += 3; reasons.push("包含 individual"); }
    if (contains("extension")) { score += 2; reasons.push("包含 extension"); }
    if (contains("strip")) score -= 5;
  } else if (type.includes("strip")) {
    if (contains("strip") || contains("false lash") || contains("false eyelash")) { score += 7; reasons.push("匹配 strip/false lashes"); }
    if (contains("cluster")) score -= 3;
  } else if (type.includes("pre-glued")) {
    if (contains("pre glued") || contains("pre-glued")) { score += 8; reasons.push("匹配 pre-glued"); }
    if (contains("cluster")) score += 2;
  } else if (type.includes("magnetic")) {
    if (contains("magnetic")) { score += 8; reasons.push("匹配 magnetic"); }
  } else if (type.includes("bond")) {
    if (contains("bond") || contains("seal") || contains("glue")) { score += 8; reasons.push("匹配 bond/seal/glue"); }
  }

  if (contains("lash") || contains("lashes") || contains("eyelash") || contains("eyelashes")) score += 1;
  ["mascara", "primer", "tweezer", "tweezers"].forEach((excluded) => {
    if (contains(excluded)) score -= 9;
  });
  if (!type.includes("bond") && (contains("glue") || contains("bond") || contains("seal"))) score -= 9;
  return { score, reason: reasons.join("、") || "仅匹配睫毛词根" };
}

function buildSellfoxKeywordPlan(data) {
  const rows = normalizeSellfoxRows(data.sellfoxSnapshot?.rows);
  const maxRank = Math.max(...rows.map((row) => row.rank), 1);
  const enriched = rows.map((row) => {
    const relevance = productTermRelevance(row.term, data.productType);
    const rankSignal = Math.max(0, 1 - row.rank / maxRank);
    const growthSignal = row.growth === null ? 0 : Math.max(-1, Math.min(1, row.growth / Math.max(row.rank, 500)));
    const conversionSignal = Math.min(1, row.conversionShare / 0.5);
    const clickSignal = Math.min(1, row.clickShare / 0.5);
    const priority = relevance.score * 18 + rankSignal * 38 + Math.max(0, growthSignal) * 24 + conversionSignal * 14 + clickSignal * 6;
    return { ...row, relevance, priority, attentionGap: row.clickShare - row.conversionShare };
  });
  const rankedRows = enriched.filter((row) => row.rank <= 30000 && !isCompetitorBrandedTerm(row, data.brandName));
  const relevantRows = rankedRows.filter((row) => row.relevance.score >= 3);
  const pool = relevantRows.length ? relevantRows : rankedRows.filter((row) => row.relevance.score >= 0);
  const byPriority = [...pool].sort((a, b) => b.priority - a.priority || a.rank - b.rank);
  const titleTerms = [...pool].sort((a, b) => a.rank - b.rank || b.priority - a.priority).slice(0, 8);
  const growthTerms = [...pool]
    .filter((row) => row.growth !== null)
    .sort((a, b) => b.growth - a.growth || a.rank - b.rank)
    .slice(0, 8);
  const conversionTerms = [...pool]
    .sort((a, b) => (b.conversionShare * 2 + b.clickShare) - (a.conversionShare * 2 + a.clickShare) || a.rank - b.rank)
    .slice(0, 8);
  const followTerms = [...pool]
    .filter((row) => row.rank <= 10000 && row.growth !== null && row.growth >= 200 && row.attentionGap >= 0.08)
    .sort((a, b) => b.attentionGap - a.attentionGap || b.growth - a.growth)
    .slice(0, 6);

  return { rows: enriched, relevantRows, titleTerms, growthTerms, conversionTerms, followTerms, backendTerms: byPriority.slice(0, 15) };
}

function isCompetitorBrandedTerm(row, ownBrand) {
  const normalizedTerm = cleanText(row.term).toLowerCase();
  const normalizedOwnBrand = cleanText(ownBrand).toLowerCase();
  const brands = (row.topBrands || []).map((brand) => cleanText(brand).toLowerCase()).filter(Boolean);
  return brands.some((brand) => {
    if (normalizedOwnBrand && (brand === normalizedOwnBrand || normalizedTerm.startsWith(normalizedOwnBrand))) return false;
    return normalizedTerm.startsWith(`${brand} `) || normalizedTerm === brand;
  });
}

function formatNumber(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString("en-US") : "--";
}

function formatGrowth(value) {
  if (!Number.isFinite(value)) return "排名变化待确认";
  return value > 0 ? `上升 ${formatNumber(value)}` : value < 0 ? `下降 ${formatNumber(Math.abs(value))}` : "排名不变";
}

function formatGrowthForCopy(value) {
  if (!Number.isFinite(value)) return "ranking trend";
  return value > 0 ? `rank-up ${formatNumber(value)} positions` : value < 0 ? `rank-change ${formatNumber(Math.abs(value))} positions` : "steady ranking";
}

function formatShare(value) {
  return Number.isFinite(value) ? `${(value * 100).toFixed(value * 100 >= 10 ? 0 : 1)}%` : "--";
}

function setListingGenerationState(isGenerating) {
  listingGenerationInProgress = isGenerating;
  const button = $("#generateBtn");
  if (button) {
    button.disabled = isGenerating || !imageExtraction.confirmed;
    button.classList.toggle("is-loading", isGenerating);
    button.innerHTML = isGenerating
      ? '<i data-lucide="loader-circle"></i> AI 撰写中'
      : '<i data-lucide="sparkles"></i> 生成';
  }
  updateWorkflowChrome();
  renderIcons();
}

function buildAiListingPayload(data, skill) {
  const plan = buildSellfoxKeywordPlan(data);
  const toAiTerms = (rows) => rows.slice(0, 8).map((row) => ({
    term: row.term,
    rank: row.rank,
    growth: row.growth,
    clickShare: row.clickShare,
    conversionShare: row.conversionShare
  }));
  const learning = getSkillLearning(skill);
  const rankedRisks = extractRiskTerms(data.forbiddenRankings);

  return {
    marketplace: data.marketplace,
    product: {
      brand: data.brandName,
      type: data.productType,
      style: data.styleAngle,
      lengths: data.lengths,
      curl: data.curl,
      bandType: data.bandType,
      pieceCount: data.pieceCount,
      contents: data.contents,
      verifiedClaims: data.verifiedClaims,
      imageFacts: data.imageFacts,
      needsConfirmation: data.imageExtractionNeeds
    },
    keywords: {
      t1: data.t1Keywords,
      t2: data.t2Keywords,
      t3: data.t3Keywords,
      rankingPriority: toAiTerms(plan.titleTerms),
      growthPriority: toAiTerms(plan.growthTerms),
      conversionPriority: toAiTerms(plan.conversionTerms),
      backendPriority: toAiTerms(plan.backendTerms)
    },
    compliance: {
      forbiddenTerms: unique([...parseTerms(skill.forbiddenClaims), ...rankedRisks.all]),
      customRules: skill.customRules
    },
    skill: {
      name: skill.name,
      titleStrategy: skill.titleStrategy,
      tone: skill.tone,
      bulletPattern: skill.bulletPattern,
      learnedRules: learning.learnedRules,
      historicalReference: (skill.referenceListing || "").slice(0, 5000)
    },
    limits: {
      title: skill.titleLimit,
      itemHighlight: skill.itemHighlightLimit,
      bullet: skill.bulletLimit,
      description: skill.descriptionLimit,
      searchTermsBytes: skill.searchTermLimit
    },
    variants: VARIANT_PROFILES.map((profile) => ({
      id: profile.id,
      name: profile.name,
      direction: profile.angle
    }))
  };
}

async function requestAiListings(payload) {
  const response = await fetch(`${LISTING_API_BASE}/generate-listings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(await readErrorPayload(response));
  const result = await response.json();
  if (!Array.isArray(result.variants) || result.variants.length !== 3) {
    throw new Error("AI 未返回完整的三版 Listing");
  }
  return result;
}

function mergeAiListingResult(baseResult, aiResponse, data, skill) {
  const responseById = new Map(aiResponse.variants.map((variant) => [variant.id, variant]));
  baseResult.variants = baseResult.variants.map((templateVariant) => {
    const aiVariant = responseById.get(templateVariant.id);
    if (!aiVariant) return templateVariant;
    const title = fitSentence(
      cleanText(aiVariant.title) || templateVariant.title,
      skill.titleLimit
    );
    const itemHighlight = fitSentence(
      cleanText(aiVariant.itemHighlight) || templateVariant.itemHighlight,
      skill.itemHighlightLimit
    );
    const highlights = normalizeAiCopyItems(aiVariant.highlights, 3, templateVariant.highlights);
    const bullets = normalizeAiCopyItems(aiVariant.bullets, 5, templateVariant.bullets);
    const description = cleanText(aiVariant.description) || templateVariant.description;
    const searchTerms = cleanText(aiVariant.searchTerms) || templateVariant.searchTerms;
    const variantSkill = {
      ...skill,
      titleStrategy: templateVariant.titleStrategy,
      tone: templateVariant.tone,
      bulletPattern: templateVariant.bulletPattern
    };
    return {
      ...templateVariant,
      title,
      itemHighlight,
      highlights,
      first50: title.slice(0, 50),
      bullets,
      description,
      searchTerms,
      selfCheck: buildSelfCheck(data, variantSkill, title, itemHighlight, highlights, bullets, description, searchTerms),
      reasons: unique([...(aiVariant.reasons || []), ...templateVariant.reasons]),
      generatedBy: "AI"
    };
  });
  baseResult.recommendedVariantId = chooseRecommendedVariant(
    baseResult.variants,
    data,
    buildContext(data),
    baseResult.needsConfirmation
  );
  baseResult.selectedVariantId = baseResult.recommendedVariantId;
  return baseResult;
}

function normalizeAiCopyItems(items, count, fallback) {
  const valid = Array.isArray(items) ? items.map(cleanText).filter(Boolean).slice(0, count) : [];
  return valid.length === count ? valid : fallback;
}

function formatListingGenerationError(message) {
  const text = String(message || "");
  const lower = text.toLowerCase();
  if (text.includes("偏好 Skill") || text.includes("保存失败") || lower.includes("persistence failed")) {
    return text;
  }
  if (lower.includes("siliconflow_api_key") || lower.includes("api key")) {
    return "服务端 AI 配置不可用，请联系管理员。";
  }
  if (text.includes("401") || text.includes("403") || lower.includes("unauthorized")) {
    return "服务端 AI 鉴权失败，请联系管理员。";
  }
  if (text.includes("30003") || lower.includes("model disabled")) {
    return "服务端 AI 暂不可用，请联系管理员。";
  }
  if (lower.includes("incomplete listing")) {
    return "AI 返回的三版内容不完整，请重试生成。";
  }
  if (lower.includes("timed out") || lower.includes("timeout")) {
    return "AI 生成超时，系统已尝试备用模型，请重试一次。";
  }
  return "AI Listing 生成失败，请稍后重试或联系管理员。";
}

function generateListing(data, skill) {
  const context = buildContext(data);
  const confirmedFacts = buildConfirmedFacts(data);
  const needsConfirmation = buildNeedsConfirmation(data);
  const variants = buildListingVariants(data, skill, context, needsConfirmation);
  const recommendedVariantId = chooseRecommendedVariant(variants, data, context, needsConfirmation);
  const selectedVariantId = recommendedVariantId;
  const qas = buildQas(data, context);
  const imagePlan = buildImagePlan(data, context);
  const strategy = buildStrategy(data, context);
  const rationale = buildRationale(data, context);
  const decisionInfo = buildDecisionInfo(data, context, needsConfirmation, variants, recommendedVariantId);
  const rankingSummary = buildRankingSummary(data);

  return {
    confirmedFacts,
    needsConfirmation,
    strategy,
    rationale,
    decisionInfo,
    rankingSummary,
    variants,
    recommendedVariantId,
    selectedVariantId,
    imagePlan,
    qas,
    reviewGuidance: buildReviewGuidance(data, context),
    abPlan: buildAbPlan(data, context)
  };
}

function buildListingVariants(data, skill, context, needsConfirmation) {
  return VARIANT_PROFILES.map((profile) => {
    const variantContext = buildVariantContext(context, profile);
    const variantSkill = {
      ...skill,
      titleStrategy: profile.titleStrategy,
      bulletPattern: profile.bulletPattern,
      tone: profile.tone
    };
    const title = buildTitle(data, variantSkill, variantContext);
    const itemHighlight = buildItemHighlight(data, variantContext, profile);
    const highlights = buildVariantHighlights(data, variantContext, profile);
    const bullets = buildBullets(data, variantContext, variantSkill);
    const description = buildVariantDescription(data, variantContext, profile);
    const searchTerms = buildSearchTerms(data, variantSkill, title, itemHighlight, highlights, bullets, description);
    const selfCheck = buildSelfCheck(data, variantSkill, title, itemHighlight, highlights, bullets, description, searchTerms);
    const score = scoreVariant(profile, data, variantContext, needsConfirmation, skill);

    return {
      ...profile,
      score,
      title,
      itemHighlight,
      highlights,
      first50: title.slice(0, 50),
      tagMatrix: buildTagMatrix(data, variantContext),
      bullets,
      description,
      searchTerms,
      selfCheck,
      reasons: buildVariantReasons(profile, data, variantContext, needsConfirmation, score)
    };
  });
}

function buildVariantContext(context, profile) {
  const plan = context.sellfoxPlan;
  const rankingCandidate = plan.titleTerms[0];
  const growthCandidate = firstDistinctSellfoxTerm(plan.growthTerms, [rankingCandidate]);
  const conversionCandidate = firstDistinctSellfoxTerm(plan.conversionTerms, [rankingCandidate, growthCandidate]);
  const candidate = profile.id === "balanced"
    ? rankingCandidate
    : profile.id === "style"
      ? growthCandidate
      : conversionCandidate;
  return {
    ...context,
    coreKeyword: candidate?.term || context.coreKeyword,
    sellfoxFocus: candidate || null
  };
}

function firstDistinctSellfoxTerm(candidates, excluded) {
  const blocked = new Set(excluded.filter(Boolean).map((item) => item.term.toLowerCase()));
  return candidates.find((item) => !blocked.has(item.term.toLowerCase())) || candidates[0] || null;
}

function buildVariantHighlights(data, context, profile) {
  const base = buildHighlights(data, context);
  if (profile.id === "style") {
    return [
      fitSentence(`${titleCase(context.coreKeyword)} paired with a ${context.look.toLowerCase()} look`, 125),
      fitSentence(`${formatGrowthForCopy(context.sellfoxFocus?.growth)} trend signal with ${context.specLine || "confirmed specs"}`, 125),
      fitSentence(`Growth-led coverage for ${context.scenarioTerms.slice(0, 2).join(" and ")} beauty routines`, 125)
    ];
  }
  if (profile.id === "search") {
    return [
      fitSentence(`${titleCase(context.coreKeyword)} for ${context.primaryScenario}`, 125),
      fitSentence(`Click ${formatShare(context.sellfoxFocus?.clickShare)} and conversion ${formatShare(context.sellfoxFocus?.conversionShare)} signal`, 125),
      fitSentence(`Routine-led copy for comparison shoppers with clear purchase intent`, 125)
    ];
  }
  return base;
}

function buildItemHighlight(data, context, profile) {
  const product = titleCase(data.productType);
  const spec = context.specLine || "confirmed product details";
  const useCases = context.scenarioTerms.slice(0, 2).join(" and ") || "daily makeup";
  if (profile.id === "style") {
    return fitSentence(`${context.look} ${product} with ${spec} for ${useCases}`, 125);
  }
  if (profile.id === "search") {
    return fitSentence(`${titleCase(context.coreKeyword)} with ${spec}, recommended for ${useCases}`, 125);
  }
  return fitSentence(`${product} with ${spec} for ${useCases}`, 125);
}

function buildVariantDescription(data, context, profile) {
  const baseDescription = buildDescription(data, context);
  if (profile.id === "style") {
    return [
      `${titleCase(data.productType)} from ${data.brandName || "your brand"} use ${context.coreKeyword} as a growth-led keyword entrance, while the visible product facts keep the page grounded in a ${context.look.toLowerCase()} finish.`,
      `This version pairs the rising search term with product images, length labels and confirmed package details instead of relying on keyword repetition alone.`,
      `Use only product claims supported by packaging or seller documentation.`
    ].join("\n\n");
  }
  if (profile.id === "search") {
    return [
      `${titleCase(data.productType)} from ${data.brandName || "your brand"} are written around ${context.coreKeyword}, a term showing top-three click share of ${formatShare(context.sellfoxFocus?.clickShare)} and conversion share of ${formatShare(context.sellfoxFocus?.conversionShare)}.`,
      `This version places mature purchase intent in the title and bullets, then moves other relevant ranking terms that are not already visible into backend Search Terms instead of repeating keywords for coverage.`,
      `Keep uncertain package details and high-risk claims out of the listing until they are confirmed.`
    ].join("\n\n");
  }
  return baseDescription;
}

function scoreVariant(profile, data, context, needsConfirmation, skill) {
  let score = 68;
  const focus = context.sellfoxFocus;
  if (profile.id === "balanced") {
    score += needsConfirmation.length ? 7 : 4;
    if (focus) score += Math.max(0, Math.round(12 - Math.log10(Math.max(focus.rank, 1)) * 2));
  }
  if (profile.id === "style") {
    if (data.styleAngle) score += 8;
    if (data.imageFacts || data.imageExtractionConfirmed) score += 7;
    if (context.scenarioTerms.length >= 3) score += 4;
    if (focus?.growth > 0) score += Math.min(12, Math.round(focus.growth / 250));
  }
  if (profile.id === "search") {
    if (data.t1Keywords.length >= 2) score += 8;
    if (data.abaRankings) score += 8;
    if (data.mcpSummary) score += 7;
    if (context.painSignals.length) score += 4;
    if (focus?.conversionShare) score += Math.min(12, Math.round(focus.conversionShare * 20));
  }
  if (preferences.lastVariantId === profile.id) score += 3;
  score += Math.min((preferences.counts?.[profile.id] || 0) * 2, 8);
  score += Math.min((getSkillLearning(skill).selectionCounts?.[profile.id] || 0) * 3, 10);
  if (!data.pieceCount && profile.id !== "balanced") score -= 4;
  if (!data.mcpSummary && !data.abaRankings && !context.sellfoxPlan.rows.length && profile.id === "search") score -= 6;
  return Math.max(45, Math.min(96, score));
}

function chooseRecommendedVariant(variants, data, context, needsConfirmation) {
  const sorted = [...variants].sort((a, b) => b.score - a.score);
  if (needsConfirmation.length >= 4) return "balanced";
  if (context.sellfoxPlan.titleTerms.length) return sorted[0]?.id || "balanced";
  if (!data.mcpSummary && !data.abaRankings && context.scenarioTerms.length >= 3 && data.imageFacts) return "style";
  return sorted[0]?.id || "balanced";
}

function buildVariantReasons(profile, data, context, needsConfirmation, score) {
  const reasons = [
    `推荐分 ${score}/100：${profile.angle}`,
    profile.bestFor
  ];
  if (context.sellfoxFocus) {
    reasons.push(`赛虎依据：${context.sellfoxFocus.term}，ABA #${formatNumber(context.sellfoxFocus.rank)}，${formatGrowth(context.sellfoxFocus.growth)}，前三商品点击 ${formatShare(context.sellfoxFocus.clickShare)} / 转化 ${formatShare(context.sellfoxFocus.conversionShare)}。`);
  } else if (profile.id === "balanced" && needsConfirmation.length) {
    reasons.push(`当前还有 ${needsConfirmation.length} 个待确认项，排名优先版会减少未确认信息进入标题和卖点。`);
  } else {
    reasons.push("尚未同步赛虎排名，本版暂用手动 T1/T2/T3、ABA 和 MCP 信息生成。");
  }
  if (preferences.counts?.[profile.id]) {
    reasons.push(`你此前选择过 ${preferences.counts[profile.id]} 次这个方向，推荐排序已参考该偏好。`);
  }
  return reasons;
}

function buildDecisionInfo(data, context, needsConfirmation, variants, recommendedVariantId) {
  const recommended = variants.find((variant) => variant.id === recommendedVariantId) || variants[0];
  const factScore = [
    data.lengths,
    data.curl,
    data.bandType,
    data.pieceCount,
    data.imageFacts || data.imageExtractionConfirmed
  ].filter(Boolean).length;
  const keywordScore = [data.t1Keywords.length, data.t2Keywords.length, data.t3Keywords.length, data.abaRankings, data.mcpSummary, context.sellfoxPlan.rows.length].filter(Boolean).length;
  const abaTerms = extractRankedTerms(data.abaRankings);
  const riskTerms = extractRiskTerms(data.forbiddenRankings);
  const confidence = factScore >= 4 && needsConfirmation.length <= 2 ? "高" : factScore >= 3 ? "中" : "低";
  const riskText = needsConfirmation.length
    ? `还有 ${needsConfirmation.length} 个信息需要确认，未确认内容不会被当作强卖点。`
    : "核心规格已较完整，可以进入更积极的标题和五点测试。";

  return [
    {
      label: "事实可信度",
      value: confidence,
      detail: `已确认规格 ${factScore}/5；图片确认${data.imageExtractionConfirmed ? "已完成" : "未完成或手动填写"}。`
    },
    {
      label: "推荐方案",
      value: recommended.name,
      detail: `推荐原因：${recommended.reasons[0]}`
    },
    {
      label: "合规判断",
      value: riskTerms.high.length ? "高风险词优先拦截" : needsConfirmation.length ? "保守写法" : "可正常展开",
      detail: riskTerms.high.length ? `高风险词：${riskTerms.high.slice(0, 5).join(", ")}；生成时不主动写入。` : riskText
    },
    {
      label: "关键词判断",
      value: context.sellfoxPlan.relevantRows.length ? "赛虎数据驱动" : keywordScore >= 4 ? "信号较足" : "建议补充",
      detail: context.sellfoxPlan.relevantRows.length
        ? `赛虎同步 ${context.sellfoxPlan.rows.length} 个词组，筛出 ${context.sellfoxPlan.relevantRows.length} 个产品相关词；标题优先 ${context.sellfoxPlan.titleTerms.slice(0, 3).map((item) => item.term).join(", ")}。`
        : `T1/T2/T3、ABA 与 MCP 数据覆盖 ${keywordScore}/6；ABA 高排名词 ${abaTerms.length ? abaTerms.slice(0, 4).join(", ") : "待填写"}。`
    },
    {
      label: "偏好影响",
      value: preferences.totalChoices ? "已参与推荐" : "暂无历史偏好",
      detail: preferences.totalChoices
        ? `常选方向：${getFavoriteVariant()?.name || "未形成"}；最近选择：${preferences.lastVariantName || "无"}。`
        : "你选择方案后，系统会把该方向作为下次推荐排序的参考。"
    }
  ];
}

function buildRankingSummary(data) {
  const abaTerms = extractRankedTerms(data.abaRankings);
  const riskTerms = extractRiskTerms(data.forbiddenRankings);
  const plan = buildSellfoxKeywordPlan(data);
  const source = [];

  if (plan.relevantRows.length) {
    source.push(`赛虎 ABA 已同步：${plan.rows.length} 个词组中筛出 ${plan.relevantRows.length} 个与 ${data.productType} 相关的词。排名优先：${plan.titleTerms.slice(0, 3).map((item) => `${item.term} (#${formatNumber(item.rank)})`).join("；")}。`);
    if (plan.growthTerms.length) {
      source.push(`增长机会：${plan.growthTerms.slice(0, 3).map((item) => `${item.term} (${formatGrowth(item.growth)})`).join("；")}。增长版标题会从这组词中选择。`);
    }
    if (plan.conversionTerms.length) {
      source.push(`转化承接：${plan.conversionTerms.slice(0, 3).map((item) => `${item.term} (点击 ${formatShare(item.clickShare)} / 转化 ${formatShare(item.conversionShare)})`).join("；")}。`);
    }
    if (plan.followTerms.length) {
      source.push(`跟随切入观察：${plan.followTerms.slice(0, 3).map((item) => `${item.term} (点击-转化差 ${(item.attentionGap * 100).toFixed(1)}pt)`).join("；")}。只作为测试假设，不等同于可直接宣称的卖点。`);
    }
  }

  if (plan.relevantRows.length) {
    source.push("Search Terms 会优先使用未出现在前台文案中的相关 ABA 词，避免重复堆词。");
  } else {
    source.push(
      data.abaRankings
        ? `ABA 排名已录入：优先参考 ${abaTerms.slice(0, 6).join(", ") || "原始 ABA 文本"}。`
        : "ABA 排名尚未读取，目前只能用 T1/T2/T3 和 MCP 摘要做关键词判断。"
    );
    source.push("没有可提取的 ABA 排名词，后台词会回退到 T1/T2/T3、MCP 和竞品评论信号。");
  }
  source.push(
    riskTerms.high.length
      ? `高风险违规词：${riskTerms.high.join(", ")}。这些词默认不进入标题、五点和 Search Terms。`
      : "未填写高风险违规词排名；系统仍会使用 Skill 里的禁用词清单。"
  );
  source.push(
    riskTerms.medium.length
      ? `中风险词：${riskTerms.medium.join(", ")}。只有在包装、资质或卖家文档确认后才建议使用。`
      : "中风险词未单独排序。"
  );
  source.push(
    riskTerms.low.length
      ? `低风险词：${riskTerms.low.join(", ")}。可作为风格或场景表达，但仍避免医疗/功效化。`
      : "低风险词未单独排序。"
  );

  return source;
}

function buildContext(data) {
  const sellfoxPlan = buildSellfoxKeywordPlan(data);
  const coreKeyword = sellfoxPlan.titleTerms[0]?.term || data.t1Keywords[0] || data.productType;
  const scenarioTerms = data.t3Keywords.length ? data.t3Keywords : ["office", "date", "daily makeup"];
  const primaryScenario = scenarioTerms.slice(0, 3).join(", ");
  const t2 = data.t2Keywords.join(" ") + " " + data.competitorNotes + " " + data.mcpSummary + " " + data.abaRankings;
  const painSignals = extractPainSignals(t2);
  const praiseSignals = extractPraiseSignals(t2);
  const contentsLabel = formatContents(data.contents);
  const specLine = [data.lengths, data.curl, data.bandType].filter(Boolean).join(" ");
  const look = data.styleAngle.replace(/\b\w/g, (char) => char.toUpperCase());
  const kitLabel = data.contents.some((item) => ["bond", "seal", "applicator", "remover"].includes(item))
    ? "Kit"
    : "";

  return {
    coreKeyword,
    scenarioTerms,
    primaryScenario,
    painSignals,
    praiseSignals,
    contentsLabel,
    specLine,
    look,
    kitLabel,
    sellfoxPlan,
    sellfoxFocus: sellfoxPlan.titleTerms[0] || null
  };
}

function buildTitle(data, skill, context) {
  const brand = data.brandName ? data.brandName.toUpperCase() : "";
  const core = titleCase(context.coreKeyword || data.productType);
  const productType = titleCase(data.productType);
  const style = titleCase(data.styleAngle);
  const spec = [data.lengths, data.curl].filter(Boolean).join(" ");
  const kit = context.kitLabel;
  const piece = data.pieceCount && /\d/.test(data.pieceCount) ? data.pieceCount : "";

  let parts;
  if (skill.titleStrategy === "brandFirst") {
    parts = [brand, core, kit, style, spec, piece];
  } else if (skill.titleStrategy === "styleFirst") {
    parts = [style, core, spec, kit, brand, piece];
  } else {
    parts = [core, style, productType !== core ? productType : "", spec, kit, brand, piece];
  }

  return fitTitle(parts, skill.titleLimit);
}

function buildHighlights(data, context) {
  const spec = context.specLine || "verified lash details";
  const contents = context.contentsLabel || "lash tray";
  return [
    fitSentence(`${context.look} look for ${context.primaryScenario}`, 125),
    fitSentence(`${spec} with ${contents}`, 125),
    fitSentence(`Built for ${context.scenarioTerms.slice(0, 2).join(" and ")} routines`, 125)
  ];
}

function buildBullets(data, context, skill) {
  const brand = data.brandName || "These lashes";
  const product = titleCase(data.productType);
  const pain = context.painSignals[0] || "heavy strip-lash feel";
  const praise = context.praiseSignals[0] || "natural-looking definition";
  const spec = context.specLine || "visible length and curl details";
  const band = data.bandType ? `${data.bandType} helps the lash line blend more softly` : "flexible placement helps shape the look";
  const contents = context.contentsLabel || "lash tray";
  const count = data.pieceCount ? `${data.pieceCount} ` : "";

  const bulletSet = {
    painSolutionScene: [
      `Skip the ${pain}. ${brand} ${product} create a ${context.look.toLowerCase()} effect for ${context.primaryScenario}, giving everyday makeup a cleaner, more intentional finish.`,
      `Beginner-friendly styling starts with small clusters you can place where your eyes need lift or softness. Use them to build a natural lash map without committing to a heavy full strip.`,
      `${count}${spec} gives you a clear routine for inner, middle and outer-corner placement. ${band} when applied with the right amount of bond and seal.`,
      `Scene-ready without sounding overdone: pair these cluster lashes with clean girl makeup, soft glam, workdays, dates or vacation photos when you want definition that still looks wearable.`,
      `Includes ${contents}. Best for shoppers who want customizable false eyelashes; choose a fuller or longer style if you prefer dramatic mega-volume makeup.`
    ],
    benefitSpecScene: [
      `${context.look} result first: these ${product.toLowerCase()} add visible definition while keeping the lash map customizable for ${context.primaryScenario}.`,
      `${spec} supports soft placement from inner corner to outer corner, so beginners can test cat-eye, doll-eye or daily lash looks with more control.`,
      `${count}${contents} keeps the routine in one place. Use the included pieces only as confirmed by your package and product images.`,
      `Review-style language points to ${praise}; the copy stays factual by connecting that benefit to the product's visible style, length and band details.`,
      `Made for daily makeup users who want a polished result, with product details grounded in confirmed packaging and seller documentation.`
    ],
    routineFirst: [
      `Map the look, apply bond, place clusters and seal as needed. This ${product.toLowerCase()} routine is built for shoppers who want control without a salon appointment.`,
      `${context.look} clusters help create a soft lash line for ${context.primaryScenario}, with a result that feels more customized than one-piece strip lashes.`,
      `${spec} and ${contents} give shoppers the practical details they need before buying, especially when comparing length range and included tools.`,
      `Pain points from reviews such as ${pain} are addressed through placement, band detail and clear application messaging instead of unsupported claims.`,
      `Best for beginners and daily makeup users; choose another style if the buyer wants bold stage, Russian volume or mega dramatic lashes.`
    ]
  };

  return bulletSet[skill.bulletPattern].map((bullet) => fitSentence(bullet, skill.bulletLimit));
}

function buildDescription(data, context) {
  const product = titleCase(data.productType);
  const spec = context.specLine || "the visible product details";
  const contents = context.contentsLabel || "the lash tray";

  return [
    `${product} from ${data.brandName || "your brand"} are positioned for a ${context.look.toLowerCase()} lash look that works with ${context.primaryScenario}. The copy focuses on verified product facts, buyer intent and clear style language.`,
    `Use the clusters to customize lift, softness and density instead of relying on a one-piece strip lash effect. The listing should connect the look to real shopper needs such as easy placement, wearable definition and a more polished daily routine.`,
    `${spec} and ${contents} should stay visible across the title, bullets, images and A+ content. Keep customer-facing copy grounded in confirmed packaging and seller documentation.`
  ].join("\n\n");
}

function buildSearchTerms(data, skill, title, itemHighlight, highlights, bullets, description) {
  const frontCopy = [title, itemHighlight, ...highlights, ...bullets, description, data.brandName].join(" ").toLowerCase();
  const forbidden = unique([...parseTerms(skill.forbiddenClaims), ...extractRiskTerms(data.forbiddenRankings).all]);
  const sellfoxTerms = buildSellfoxKeywordPlan(data).backendTerms.map((item) => item.term);
  const sourceTerms = [
    ...sellfoxTerms,
    ...extractRankedTerms(data.abaRankings),
    ...data.t1Keywords,
    ...data.t2Keywords,
    ...data.t3Keywords,
    ...extractTermsFromText(data.abaRankings),
    ...extractTermsFromText(data.mcpSummary),
    ...extractTermsFromText(data.competitorNotes),
    "manga lashes",
    "bunny lashes",
    "pestanas postizas",
    "wispy extensions",
    "under lash"
  ];

  const candidates = unique(sourceTerms)
    .map(sanitizeSearchTerm)
    .filter(Boolean)
    .filter((term) => !containsForbidden(term, forbidden))
    .filter((term) => !frontCopy.includes(term.toLowerCase()));

  let output = "";
  for (const term of candidates) {
    const next = output ? `${output} ${term}` : term;
    if (byteLength(next) <= skill.searchTermLimit) {
      output = next;
    }
  }
  return output || "manga bunny underlash pestanas postizas wispy refill";
}

function buildQas(data, context) {
  const specs = context.specLine || "Check the package and tray labels for exact lengths and curl.";
  const contents = context.contentsLabel || "lash tray";
  return [
    {
      q: "What look does it create?",
      a: `It is positioned for a ${context.look.toLowerCase()} lash look, suitable for ${context.primaryScenario}.`
    },
    {
      q: "What lengths and curl are included?",
      a: specs
    },
    {
      q: "What is included in the package?",
      a: contents
    },
    {
      q: "Is it beginner-friendly?",
      a: "The listing can describe beginner-friendly placement only when the lash map, tools or review language support that positioning."
    },
    {
      q: "Does it include verified safety or wear-time claims?",
      a: "Only use those claims if packaging, lab documents or the seller confirms them."
    }
  ];
}

function buildImagePlan(data, context) {
  const spec = context.specLine || "length and curl details";
  return [
    `Main image: tray, packaging and confirmed tools clearly visible.`,
    `Image 2: kit contents callout with ${context.contentsLabel || "included items"}.`,
    `Image 3: lash map using ${spec}.`,
    `Image 4: ${context.look} on-eye result with a clean background.`,
    `Image 5: pain-point module for ${context.painSignals.slice(0, 2).join(" and ") || "placement and band visibility"}.`,
    `Image 6: scenarios such as ${context.primaryScenario}.`,
    `A+ modules: brand story, routine steps, detail close-up and generic style comparison.`
  ];
}

function buildStrategy(data, context) {
  const abaTerms = extractRankedTerms(data.abaRankings);
  const riskTerms = extractRiskTerms(data.forbiddenRankings);
  return [
    `T1 title zone: ${context.coreKeyword} plus ${data.styleAngle}.`,
    context.sellfoxFocus
      ? `赛虎标题依据：${context.sellfoxFocus.term} 的 ABA #${formatNumber(context.sellfoxFocus.rank)}；${formatGrowth(context.sellfoxFocus.growth)}。`
      : "赛虎排名尚未同步，标题核心词暂用手动 T1 输入。",
    `T2 conversion angle: ${data.t2Keywords.slice(0, 4).join(", ") || "beginner use, natural look, easy placement"}.`,
    `T3 COSMO scenes: ${context.primaryScenario}.`,
    `ABA ranking signal: ${abaTerms.length ? abaTerms.slice(0, 6).join(", ") : "No ABA ranking pasted; keyword priority is estimated from T1/T2/T3 and MCP."}`,
    `Risk word priority: ${riskTerms.high.length ? `High risk - ${riskTerms.high.join(", ")}` : "No ranked risk words pasted; using Skill forbidden claims only."}`,
    `MCP signal to use: ${data.mcpSummary || "No MCP summary pasted; using the built-in false-lash logic."}`,
    `Competitor/review signal: ${data.competitorNotes || "No competitor notes pasted; keep claims conservative."}`
  ];
}

function buildRationale(data, context) {
  const abaTerms = extractRankedTerms(data.abaRankings);
  const riskTerms = extractRiskTerms(data.forbiddenRankings);
  return [
    `${context.coreKeyword} -> ${context.sellfoxFocus ? "赛虎排名和产品相关性筛选后的核心词" : "T1 / MCP 输入的核心词"}。`,
    context.sellfoxFocus
      ? `${context.sellfoxFocus.term} -> 赛虎产品相关性筛选后，ABA #${formatNumber(context.sellfoxFocus.rank)}；${formatGrowth(context.sellfoxFocus.growth)}。`
      : "赛虎排名 -> 尚未同步，未作为自动排名依据。",
    `${abaTerms.slice(0, 3).join(", ") || "ABA ranking pending"} -> ABA ranking / keyword-share priority.`,
    `${data.styleAngle} -> visual or product-positioning style angle.`,
    `${context.specLine || "spec details"} -> user/image-confirmed product fact.`,
    `${context.primaryScenario} -> COSMO scenario coverage.`,
    `${context.painSignals.join(", ") || "pain-point language"} -> review/competitor/MCP pain signal.`,
    `${riskTerms.high.join(", ") || "Skill forbidden claims"} -> compliance/risk-word exclusion priority.`
  ];
}

function buildConfirmedFacts(data) {
  const facts = [
    `Marketplace: ${data.marketplace}`,
    data.brandName && `Brand: ${data.brandName}`,
    `Product type: ${titleCase(data.productType)}`,
    `Style: ${titleCase(data.styleAngle)}`,
    data.lengths && `Lengths: ${data.lengths}`,
    data.curl && `Curl: ${data.curl}`,
    data.bandType && `Band: ${data.bandType}`,
    data.pieceCount && `Piece count: ${data.pieceCount}`,
    data.contents.length && `Contents: ${formatContents(data.contents)}`
  ].filter(Boolean);
  return facts;
}

function buildNeedsConfirmation(data) {
  const needs = [];
  if (!data.lengths) needs.push("Length range is not confirmed.");
  if (!data.curl) needs.push("Curl is not confirmed.");
  if (!data.bandType) needs.push("Band type is not confirmed.");
  if (!data.pieceCount) needs.push("Piece count is not confirmed; keep it out of the title.");
  if (!data.verifiedClaims.length) needs.push("No safety, waterproof, wear-time or reusable claims are verified.");
  if (data.imageExtractionConfirmed && data.imageExtractionNeeds.length) {
    data.imageExtractionNeeds.forEach((item) => needs.push(`Image review: ${item}`));
  }
  return needs;
}

function buildTagMatrix(data, context) {
  return {
    Function: ["add length", "add definition", context.look.toLowerCase()],
    Scene: context.scenarioTerms,
    Audience: ["beginners", "daily makeup users", "soft glam users"],
    Product: [data.productType, "false eyelashes", "individual lashes"],
    Attribute: [data.bandType, data.curl, data.lengths].filter(Boolean),
    Intent: ["natural look", "custom lash map", "wearable beauty routine"]
  };
}

function buildReviewGuidance(data, context) {
  return [
    "Encourage compliant photo themes through better product experience and packaging, not through review incentives.",
    `Useful review-photo themes: on-eye ${context.look.toLowerCase()} result, close-up band detail, package contents and ${context.primaryScenario}.`,
    "Never ask buyers to mention keywords or leave positive reviews."
  ];
}

function buildAbPlan(data, context) {
  return [
    `A: ${titleCase(context.coreKeyword)} front-loaded with ${data.styleAngle}.`,
    `B: ${titleCase(data.styleAngle)} angle first for trend/style testing.`,
    `Image test: length map first versus on-eye result first.`,
    `Bullet test: pain-point opening versus beauty-result opening.`
  ];
}

function escapeRegExp(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function findRepeatedTitleWords(title) {
  const exempt = new Set([
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "nor",
    "of", "on", "or", "so", "the", "to", "with", "yet"
  ]);
  const counts = new Map();
  (String(title || "").toLowerCase().match(/[a-z0-9]+(?:-[a-z0-9]+)?/g) || []).forEach((word) => {
    if (!exempt.has(word)) counts.set(word, (counts.get(word) || 0) + 1);
  });
  return [...counts.entries()].filter(([, count]) => count > 2).map(([word]) => word);
}

function buildSelfCheck(data, skill, title, itemHighlight, highlights, bullets, description, searchTerms) {
  const fullCopy = [title, itemHighlight, ...highlights, ...bullets, description, searchTerms].join(" ");
  const titleWithoutBrand = data.brandName
    ? title.replace(new RegExp(escapeRegExp(data.brandName), "ig"), "")
    : title;
  const disallowedTitleCharacters = unique(titleWithoutBrand.match(/[!$?_{}^¬¦]/g) || []);
  const repeatedTitleWords = findRepeatedTitleWords(title);
  const rankedRisks = extractRiskTerms(data.forbiddenRankings);
  const forbidden = unique([...parseTerms(skill.forbiddenClaims), ...rankedRisks.all]);
  const forbiddenHits = forbidden.filter((term) => fullCopy.toLowerCase().includes(term.toLowerCase()));
  const highRiskHits = rankedRisks.high.filter((term) => fullCopy.toLowerCase().includes(term.toLowerCase()));
  const unverifiedClaimHits = forbiddenHits.filter((term) => isClaimTerm(term) && !isClaimVerified(term, data.verifiedClaims));

  const checks = [
    {
      status: title.length <= skill.titleLimit ? "ok" : "bad",
      text: `标题 ${title.length}/${skill.titleLimit} 字符`
    },
    {
      status: itemHighlight.length <= skill.itemHighlightLimit ? "ok" : "bad",
      text: `Item Highlights ${itemHighlight.length}/${skill.itemHighlightLimit} 字符`
    },
    {
      status: disallowedTitleCharacters.length ? "bad" : "ok",
      text: disallowedTitleCharacters.length
        ? `标题含禁用符号：${disallowedTitleCharacters.join(" ")}`
        : "标题未发现 Amazon 禁用符号"
    },
    {
      status: repeatedTitleWords.length ? "bad" : "ok",
      text: repeatedTitleWords.length
        ? `标题实义词重复超过 2 次：${repeatedTitleWords.join(", ")}`
        : "标题实义词均未重复超过 2 次"
    },
    {
      status: Math.max(...bullets.map((item) => item.length)) <= skill.bulletLimit ? "ok" : "bad",
      text: `最长五点 ${Math.max(...bullets.map((item) => item.length))}/${skill.bulletLimit} 字符`
    },
    {
      status: description.length <= skill.descriptionLimit ? "ok" : "bad",
      text: `产品描述 ${description.length}/${skill.descriptionLimit} 字符`
    },
    {
      status: byteLength(searchTerms) <= skill.searchTermLimit ? "ok" : "bad",
      text: `Search Terms ${byteLength(searchTerms)}/${skill.searchTermLimit} bytes`
    },
    {
      status: unverifiedClaimHits.length ? "bad" : "ok",
      text: unverifiedClaimHits.length
        ? `未确认声明风险：${unverifiedClaimHits.join(", ")}`
        : "未检测到未确认的防水、24-hour、低敏或无乳胶声明"
    },
    {
      status: /B0[A-Z0-9]{8}/i.test(searchTerms) ? "bad" : "ok",
      text: /B0[A-Z0-9]{8}/i.test(searchTerms)
        ? "后台 Search Terms 含有疑似 ASIN 格式"
        : "后台 Search Terms 未发现 ASIN 格式"
    },
    {
      status: forbiddenHits.length ? "warn" : "ok",
      text: forbiddenHits.length ? `发现禁用词或高风险词，需复核：${forbiddenHits.join(", ")}` : "未发现禁用促销词"
    },
    {
      status: highRiskHits.length ? "bad" : "ok",
      text: highRiskHits.length
        ? `命中高风险词排名：${highRiskHits.join(", ")}`
        : rankedRisks.high.length
          ? `高风险词排名已检查：${rankedRisks.high.slice(0, 5).join(", ")}`
          : "未录入单独的高风险词排名"
    }
  ];

  return checks;
}

function renderResult(result) {
  const selected = result.variants.find((variant) => variant.id === result.selectedVariantId)
    || result.variants.find((variant) => variant.id === result.recommendedVariantId)
    || result.variants[0];
  result.selectedVariantId = selected.id;

  const blocks = [
    {
      title: "方案选择",
      metric: `${result.variants.length} 版`,
      content: renderVariantChoicesText(result),
      html: renderVariantChoicesHtml(result, selected)
    },
    {
      title: "判断信息与推荐理由",
      metric: selected.name,
      content: renderDecisionText(result.decisionInfo, selected),
      html: renderDecisionHtml(result.decisionInfo, selected)
    },
    {
      title: "ABA 排名与违规词优先级",
      metric: "排序依据",
      content: toList(result.rankingSummary),
      html: renderRankingSummaryHtml(result.rankingSummary)
    },
    {
      title: "已确认产品事实",
      metric: `${result.confirmedFacts.length} 项`,
      content: toList(result.confirmedFacts)
    },
    {
      title: "需要确认",
      metric: `${result.needsConfirmation.length} 项`,
      content: result.needsConfirmation.length ? toList(result.needsConfirmation) : "没有待确认项。"
    },
    {
      title: "数据策略摘要",
      metric: "策略",
      content: toList(result.strategy)
    },
    {
      title: "数据到文案依据",
      metric: "可追溯",
      content: toList([...result.rationale, ...selected.reasons])
    },
    {
      title: "标题",
      metric: `${selected.title.length}/75`,
      content: selected.title
    },
    {
      title: "Item Highlights（商品亮点，常称副标题）",
      metric: `${selected.itemHighlight.length}/125`,
      content: selected.itemHighlight
    },
    {
      title: "卖点提炼（内部参考）",
      metric: `${selected.highlights.length} 条`,
      content: toNumbered(selected.highlights.map((item) => `${item} [${item.length}/125]`))
    },
    {
      title: "前 50 个字符",
      metric: `${selected.first50.length}/50`,
      content: selected.first50
    },
    {
      title: "COSMO/Alexa 标签矩阵",
      metric: "标签",
      content: renderTagMatrixText(selected.tagMatrix),
      html: renderTagMatrixHtml(selected.tagMatrix)
    },
    {
      title: "五点描述",
      metric: `最长 ${Math.max(...selected.bullets.map((item) => item.length))}/500`,
      content: toNumbered(selected.bullets.map((item) => `${item} [${item.length}/500]`))
    },
    {
      title: "产品描述",
      metric: `${selected.description.length}/2000`,
      content: selected.description
    },
    {
      title: "图片与 A+ 规划",
      metric: "模块",
      content: toNumbered(result.imagePlan)
    },
    {
      title: "后台 Search Terms",
      metric: `${byteLength(selected.searchTerms)}/249 bytes`,
      content: selected.searchTerms
    },
    {
      title: "Alexa/Rufus 问答",
      metric: `${result.qas.length} Q&A`,
      content: result.qas.map((item) => `Q: ${item.q}\nA: ${item.a}`).join("\n\n")
    },
    {
      title: "评论内容引导",
      metric: "合规",
      content: toList(result.reviewGuidance)
    },
    {
      title: "A/B 测试计划",
      metric: "版本",
      content: toList(result.abPlan)
    },
    {
      title: "自检",
      metric: "质量",
      content: selected.selfCheck.map((item) => `${item.status.toUpperCase()}: ${item.text}`).join("\n"),
      html: renderCheckHtml(selected.selfCheck)
    }
  ];

  renderBlocks(blocks);
  $("#titleScore").textContent = `${selected.title.length}/75`;
  $("#itemHighlightScore").textContent = `${selected.itemHighlight.length}/125`;
  $("#bulletScore").textContent = `${Math.max(...selected.bullets.map((item) => item.length))}/500`;
  $("#stScore").textContent = `${byteLength(selected.searchTerms)}/249 bytes`;
  currentOutputText = blocks.map((block) => `## ${block.title}\n${block.content}`).join("\n\n");
}

function renderVariantChoicesHtml(result, selected) {
  return `<div class="variant-grid">${result.variants
    .map((variant) => {
      const isSelected = variant.id === selected.id;
      const isRecommended = variant.id === result.recommendedVariantId;
      return `
        <article class="variant-card ${isSelected ? "selected" : ""}">
          <div class="variant-card-head">
            <div>
              <strong>${escapeHtml(variant.name)}</strong>
              <span>${escapeHtml(variant.badge)}</span>
            </div>
            <b>${variant.score}</b>
          </div>
          <p>${escapeHtml(variant.bestFor)}</p>
          <div class="variant-title">${escapeHtml(variant.title)}</div>
          <div class="variant-item-highlight">
            <span>Item Highlights</span>
            ${escapeHtml(variant.itemHighlight)}
          </div>
          <ul>
            ${variant.reasons.slice(0, 3).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}
          </ul>
          <button class="ghost-button variant-button" type="button" data-variant-id="${escapeHtml(variant.id)}">
            <i data-lucide="${isSelected ? "check-circle-2" : "mouse-pointer-click"}"></i>
            ${isSelected ? "当前采用" : "采用此版"}${isRecommended ? " · 推荐" : ""}
          </button>
        </article>`;
    })
    .join("")}</div>
    <section class="listing-feedback">
      <div>
        <strong>让当前 Skill 继续学习</strong>
        <p>采用喜欢的方案后，可以记录问题、修改方向或不想再出现的表达。下一次 AI 生成会读取这些规则。</p>
      </div>
      <label for="listingFeedbackInput">当前采用方案的问题反馈</label>
      <textarea id="listingFeedbackInput" rows="3" placeholder="例如：标题过于堆词；语气希望更自然；五点先讲使用场景；不要再写 beginner-friendly"></textarea>
      <button class="ghost-button" type="button" data-submit-listing-feedback>
        <i data-lucide="message-square-plus"></i>
        提炼并写入当前 Skill
      </button>
    </section>`;
}

function renderVariantChoicesText(result) {
  return result.variants
    .map(
      (variant) => `${variant.name} (${variant.score}/100)\n标题：${variant.title}\nItem Highlights：${variant.itemHighlight}\n${variant.reasons.join("\n")}`
    )
    .join("\n\n");
}

function renderDecisionHtml(decisions, selected) {
  return `
    <div class="decision-grid">
      ${decisions
        .map(
          (item) => `
          <div class="decision-card">
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(item.value)}</strong>
            <p>${escapeHtml(item.detail)}</p>
          </div>`
        )
        .join("")}
    </div>
    <div class="recommend-note">
      <strong>当前采用：${escapeHtml(selected.name)}</strong>
      <p>${escapeHtml(selected.angle)}</p>
    </div>`;
}

function renderDecisionText(decisions, selected) {
  return [
    ...decisions.map((item) => `${item.label}: ${item.value} - ${item.detail}`),
    `当前采用: ${selected.name} - ${selected.angle}`
  ].join("\n");
}

function renderRankingSummaryHtml(items) {
  return `<div class="ranking-summary">${items
    .map((item) => {
      const type = item.includes("高风险") ? "risk-high" : item.includes("ABA") ? "aba" : item.includes("中风险") ? "risk-medium" : "plain";
      return `<p class="${type}">${escapeHtml(item)}</p>`;
    })
    .join("")}</div>`;
}

function renderBlocks(blocks) {
  const area = $("#resultArea");
  area.innerHTML = "";
  blocks.forEach((block) => {
    const article = document.createElement("article");
    article.className = "result-block";
    const header = document.createElement("header");
    header.innerHTML = `<h3>${escapeHtml(block.title)}</h3><span class="metric">${escapeHtml(block.metric || "")}</span>`;
    const content = document.createElement("div");
    content.className = "result-content";
    if (block.html) {
      content.innerHTML = block.html;
    } else {
      content.textContent = block.content;
    }
    article.append(header, content);
    area.appendChild(article);
  });
  renderIcons();
}

function renderTagMatrixHtml(matrix) {
  return Object.entries(matrix)
    .map(
      ([key, values]) =>
        `<p><strong>${escapeHtml(key)}</strong></p><div class="tag-row">${values
          .map((value) => `<span class="tag">${escapeHtml(value)}</span>`)
          .join("")}</div>`
    )
    .join("");
}

function renderCheckHtml(checks) {
  return `<ul class="risk-list">${checks
    .map((item) => `<li><strong class="${item.status}">${item.status.toUpperCase()}</strong><span>${escapeHtml(item.text)}</span></li>`)
    .join("")}</ul>`;
}

function drawTrayPreview() {
  const canvas = $("#trayCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const data = {
    lengths: getSelectedLengthsText(),
    pieceCount: $("#pieceCount").value,
    styleAngle: $("#styleAngle").value,
    curl: $("#curl").value,
    bandType: $("#bandType").value
  };

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fff7fa";
  ctx.fillRect(0, 0, width, height);

  ctx.fillStyle = "#f5dce7";
  roundedRect(ctx, 34, 22, 492, 190, 18);
  ctx.fill();
  ctx.strokeStyle = "#d9b7c6";
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.fillStyle = "#fffefe";
  roundedRect(ctx, 56, 42, 448, 150, 12);
  ctx.fill();

  const rows = inferRows(data.pieceCount);
  const cols = 12;
  const startX = 84;
  const startY = 58;
  const gapX = 31;
  const gapY = Math.min(18, 122 / Math.max(rows - 1, 1));
  const color = data.bandType === "black band" ? "#241a21" : "#3f3038";

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const x = startX + col * gapX;
      const y = startY + row * gapY;
      drawLash(ctx, x, y, 10 + (col % 4), color, data.styleAngle);
    }
  }

  const labels = parseLengths(data.lengths);
  ctx.fillStyle = "#8f3454";
  ctx.font = "700 16px Inter, sans-serif";
  ctx.fillText(titleCase(data.styleAngle || "lash map"), 34, 236);
  ctx.fillStyle = "#746971";
  ctx.font = "600 13px Inter, sans-serif";
  ctx.fillText([labels.join(" / "), data.curl, data.bandType].filter(Boolean).join("  ·  ") || "Length map preview", 34, 254);

  $("#previewTitle").textContent = `${titleCase(data.styleAngle || "Lash")} Preview`;
  $("#previewMeta").textContent = `${rows} rows · ${data.pieceCount || "count pending"}`;
}

function drawLash(ctx, x, y, length, color, style) {
  const curve = style.includes("cat") ? 8 : style.includes("manga") ? 11 : 6;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.quadraticCurveTo(x - curve, y - length, x - curve / 2, y - length - 8);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x + 3, y);
  ctx.quadraticCurveTo(x + curve, y - length - 2, x + curve / 2, y - length - 9);
  ctx.stroke();
}

function roundedRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function createEmptyExtraction() {
  return {
    status: "idle",
    confirmed: false,
    facts: [],
    needs: [],
    blocked: [],
    source: ""
  };
}

function previewImages(event) {
  const preview = $("#imagePreview");
  preview.innerHTML = "";
  uploadedImages = Array.from(event.target.files).slice(0, 6);
  uploadedImages
    .slice(0, 6)
    .forEach((file) => {
      const img = document.createElement("img");
      img.alt = file.name;
      img.src = URL.createObjectURL(file);
      preview.appendChild(img);
    });
  imageExtraction = uploadedImages.length
    ? {
        ...createEmptyExtraction(),
        status: "uploaded",
        needs: ["图片已上传，等待识别。请点击“提取”获取可确认事实。"]
      }
    : createEmptyExtraction();
  renderExtractionReview();
  setFlowState(uploadedImages.length ? "uploaded" : "idle");
}

function setFlowState(state) {
  document.body.dataset.flowState = state;
  const chips = $$(".status-chip");
  const activeMap = {
    idle: 0,
    uploaded: 0,
    extracting: 0,
    extracted: 1,
    review: 1,
    confirmed: 2,
    done: 3
  };
  const activeIndex = activeMap[state] ?? 0;
  chips.forEach((chip, index) => {
    chip.classList.toggle("active", index <= activeIndex);
  });
  syncRecognitionGate();
  const stepMap = {
    idle: 1,
    uploaded: 1,
    extracting: 1,
    extracted: 1,
    review: 1,
    confirmed: 2,
    done: 4
  };
  setActiveWorkflowStep(stepMap[state] || activeWorkflowStep);
}

function syncRecognitionGate() {
  const isUnlocked = imageExtraction.confirmed;
  const strategyPanel = $("#strategyPanel");
  const outputPanel = $("#outputPanel");

  if (strategyPanel) {
    strategyPanel.classList.remove("flow-locked");
    strategyPanel.inert = false;
    strategyPanel.setAttribute("aria-disabled", "false");
  }
  if (outputPanel) {
    outputPanel.classList.toggle("flow-locked", !isUnlocked);
    outputPanel.inert = !isUnlocked;
    outputPanel.setAttribute("aria-disabled", String(!isUnlocked));
  }

  ["#strategyLock", "#outputLock"].forEach((selector) => {
    const notice = $(selector);
    if (notice) notice.hidden = isUnlocked;
  });

  $$('[data-recognition-dependent] input, [data-recognition-dependent] select, [data-recognition-dependent] textarea').forEach((field) => {
    field.disabled = !isUnlocked;
  });

  ["#generateBtn", "#copyAllBtn"].forEach((selector) => {
    const button = $(selector);
    if (button) button.disabled = !isUnlocked;
  });
}

async function extractImageFacts() {
  if (!uploadedImages.length) {
    showToast("请先上传产品图片");
    return;
  }
  imageExtraction = {
    ...imageExtraction,
    status: "extracting",
    confirmed: false,
    needs: ["正在提取图片可见事实..."]
  };
  renderExtractionReview();
  setFlowState("extracting");

  try {
    const extraction = await runImageExtraction(uploadedImages, collectForm());
    imageExtraction = {
      ...extraction,
      status: "extracted",
      confirmed: false
    };
    renderExtractionReview();
    setFlowState("extracted");
    showToast("图片事实已提取，请确认后继续");
  } catch (error) {
    const errorReason = formatExtractorError(error.message);
    const manualEvidence = cleanText($("#imageFacts").value);
    imageExtraction = {
      ...createEmptyExtraction(),
      status: "extracted",
      facts: manualEvidence
        ? [{ key: "packageText", label: "人工补充的图片证据", value: manualEvidence, source: "人工输入", confidence: "待确认" }]
        : [],
      needs: [
        errorReason,
        manualEvidence
          ? "图片识别接口暂不可用，可确认人工补充的图片证据后继续。"
          : "图片识别接口暂不可用；识别补充为可选项，可留空并确认继续，或稍后重新提取。"
      ],
      blocked: ["不要从图片臆测材质、安全、持久、防水、低敏或复用次数。"],
      source: error.message
    };
    renderExtractionReview();
    setFlowState("review");
    showToast(manualEvidence ? "图片识别失败，请确认人工补充的图片证据后继续" : "图片识别失败；识别补充可留空，确认后可继续");
  }
}

async function runImageExtraction(files, currentData) {
  const endpoint =
    typeof window !== "undefined" && window.LISTING_IMAGE_EXTRACTOR_ENDPOINT
      ? window.LISTING_IMAGE_EXTRACTOR_ENDPOINT
      : typeof window !== "undefined" && window.location.protocol.startsWith("http")
        ? `${LISTING_API_BASE}/extract-image`
        : "";

  if (endpoint) {
    const images = await Promise.all(files.slice(0, 4).map(fileToPayload));
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task: "extract_listing_image_facts",
        category: currentData.productType,
        marketplace: currentData.marketplace,
        images
      })
    });
    if (!response.ok) {
      const detail = await readErrorPayload(response);
      throw new Error(detail);
    }
    const payload = await response.json();
    return normalizeExtractionPayload(payload);
  }

  return localImageExtraction(files, currentData);
}

async function readErrorPayload(response) {
  const text = await response.text();
  try {
    const payload = JSON.parse(text);
    const siliconFlowPart = [
      payload.siliconFlowStatus && `status ${payload.siliconFlowStatus}`,
      payload.siliconFlowCode && `code ${payload.siliconFlowCode}`,
      payload.siliconFlowMessage
    ].filter(Boolean).join(" · ");
    const source = response.url.includes("/generate-listings") ? "AI Listing" : "Image extractor";
    return [
      `${source} returned ${response.status}`,
      siliconFlowPart || payload.message || payload.error || text
    ].filter(Boolean).join(": ");
  } catch {
    const source = response.url.includes("/generate-listings") ? "AI Listing" : "Image extractor";
    return `${source} returned ${response.status}: ${text.slice(0, 240)}`;
  }
}

function formatExtractorError(message) {
  const text = String(message || "");
  const lower = text.toLowerCase();

  if (lower.includes("siliconflow_api_key") || lower.includes("api key")) {
    return "服务端 AI 配置不可用，请联系管理员。";
  }
  if (lower.includes("model disabled")) {
    return "服务端图片识别暂不可用，请联系管理员。";
  }
  if (lower.includes("code 30003")) {
    return "服务端图片识别暂不可用，请联系管理员。";
  }
  if (text.includes("401") || text.includes("403") || lower.includes("unauthorized") || lower.includes("forbidden")) {
    return "服务端 AI 鉴权失败，请联系管理员。";
  }
  if (text.includes("400") && (lower.includes("image") || lower.includes("vision") || lower.includes("multimodal"))) {
    return "服务端暂时无法识别该图片，请更换图片后重试。";
  }
  if (lower.includes("model")) {
    return "服务端图片识别暂不可用，请联系管理员。";
  }

  return "图片识别接口返回错误，请稍后重试或联系管理员。";
}

function localImageExtraction(files, currentData) {
  const fileText = files.map((file) => file.name).join(" ");
  const source = [fileText, currentData.imageFacts].filter(Boolean).join(" ");
  const lower = source.toLowerCase();
  const facts = [];
  const needs = [];
  const blocked = [
    "不要仅凭图片推断材质、成分、安全认证、低敏、敏感眼可用、持久小时数、防水、可复用次数。",
    "侧边道具不能默认视为包含物；必须由包装、SKU 数据或用户确认。",
    "只把包装文字、托盘标签、明显配件和视觉风格作为可确认事实。"
  ];

  addFact(facts, "brandName", "品牌 / 产品线", currentData.brandName, "用户输入");
  addFact(facts, "productType", "产品类型", currentData.productType, "已选择类目");

  const lengthHit = extractLengthOptions(source).join("/");
  addFact(facts, "lengths", "长度", lengthHit || currentData.lengths, lengthHit ? "图片文字或文件名" : "当前表单");

  const curlHit = source.match(/\b(?:CC|DD|CD|J|B|C|D|L|M)\s*curl\b/i);
  addFact(facts, "curl", "卷度", curlHit?.[0] || currentData.curl, curlHit ? "图片文字或文件名" : "当前表单");

  const pieceHit = source.match(/\b\d{2,3}\s*(?:pcs|pieces|clusters)\b/i);
  addFact(facts, "pieceCount", "根数", pieceHit?.[0] || currentData.pieceCount, pieceHit ? "图片文字或文件名" : "当前表单");

  const band = ["clear band", "thin band", "invisible band", "black band"].find((item) => lower.includes(item));
  addFact(facts, "bandType", "带型", band || currentData.bandType, band ? "图片文字或文件名" : "当前表单");

  const style = detectStyle(lower, currentData.styleAngle);
  addFact(facts, "styleAngle", "视觉风格", style, style === currentData.styleAngle ? "当前表单" : "视觉/风格文字");

  ["lash tray", "bond", "seal", "applicator", "remover"].forEach((item) => {
    if (lower.includes(item.replace("lash ", "")) || currentData.contents.includes(item)) {
      addFact(facts, "contents", "可见 / 已确认内容物", item, lower.includes(item.replace("lash ", "")) ? "图片文字或文件名" : "当前表单");
    }
  });

  if (!facts.some((fact) => fact.key === "lengths")) needs.push("长度标签需要确认。");
  if (!facts.some((fact) => fact.key === "curl")) needs.push("卷度需要确认。");
  if (!facts.some((fact) => fact.key === "pieceCount")) needs.push("根数需要确认；确认前不要写进标题。");
  if (!facts.some((fact) => fact.key === "bandType")) needs.push("带型需要确认。");
  if (!lower.includes("bond") && !lower.includes("seal") && !lower.includes("applicator")) {
    needs.push("如果胶水、封层或夹子只是图片道具，套装内容物需要人工确认。");
  }

  return {
    facts,
    needs,
    blocked,
    source: "本地图片识别结果。"
  };
}

function addFact(facts, key, label, value, source) {
  const clean = cleanText(value);
  if (!clean) return;
  if (facts.some((fact) => fact.key === key && fact.value.toLowerCase() === clean.toLowerCase())) return;
  facts.push({
    key,
    label,
    value: clean,
    source,
    confidence: source.includes("image") || source.includes("图片") ? "中" : "低"
  });
}

function detectStyle(lower, fallback) {
  const styleMap = [
    ["manga spiky", ["manga", "spiky", "spider"]],
    ["bunny eye", ["bunny"]],
    ["cat eye", ["cat eye", "cateye"]],
    ["doll eye", ["doll", "baby doll"]],
    ["soft glam", ["soft glam"]],
    ["short natural", ["short natural"]],
    ["natural wispy", ["natural", "wispy"]]
  ];
  const match = styleMap.find(([, keys]) => keys.some((key) => lower.includes(key)));
  return match ? match[0] : fallback;
}

function normalizeExtractionPayload(payload) {
  const facts = Array.isArray(payload.facts) ? payload.facts : [];
  const needs = Array.isArray(payload.needsConfirmation) ? payload.needsConfirmation : payload.needs || [];
  const blocked = Array.isArray(payload.doNotInfer) ? payload.doNotInfer : payload.blocked || [];
  return {
    facts: facts.map((fact) => ({
      key: cleanText(fact.key),
      label: translateExtractionText(cleanText(fact.label || fact.key)),
      value: cleanText(fact.value),
      source: translateExtractionText(cleanText(fact.source || "服务端图片识别")),
      confidence: translateConfidence(cleanText(fact.confidence || "medium"))
    })).filter((fact) => fact.key && fact.value),
    needs: needs.map((item) => translateExtractionText(cleanText(item))).filter(Boolean),
    blocked: blocked.map((item) => translateExtractionText(cleanText(item))).filter(Boolean),
    source: translateExtractionText(cleanText(payload.source || "vision endpoint"))
  };
}

function translateConfidence(confidence) {
  const map = {
    high: "高",
    medium: "中",
    low: "低"
  };
  return map[confidence.toLowerCase()] || confidence;
}

function translateExtractionText(text) {
  const normalized = cleanText(text);
  const lower = normalized.toLowerCase();
  const exactMap = {
    "needs confirmation": "需要确认",
    "do not infer": "禁止推断",
    "confirmed from image": "图片确认事实",
    "exact piece count": "准确根数",
    "full package text": "包装完整文字",
    "brand name spelling": "品牌名称拼写",
    "style name": "风格名称",
    "package text": "包装文字",
    "tray label": "托盘标签",
    "visible item": "可见内容物",
    "visual inference": "视觉推断",
    "vision model": "图片识别",
    "vision endpoint": "视觉接口",
    "image text or filename": "图片文字或文件名",
    "current form": "当前表单",
    "user input": "用户输入",
    "selected category": "已选择类目",
    "image-visible estimate": "图片可见估算",
    "lengths": "长度",
    "curl": "卷度",
    "piece count": "根数",
    "band type": "带型",
    "visual style": "视觉风格",
    "brand / product line": "品牌 / 产品线",
    "product type": "产品类型",
    "visible / confirmed content": "可见 / 已确认内容物"
  };
  if (exactMap[lower]) return exactMap[lower];

  return normalized
    .replace(/Do not infer material, ingredients, hypoallergenic, latex-free, waterproof, wear time, reusable count, irritation-free, residue-free, or sensitive-eye-safe claims from images only\./gi, "不要仅凭图片推断材质、成分、低敏、无乳胶、防水、佩戴时长、可复用次数、无刺激、无残留或敏感眼可用等声明。")
    .replace(/Do not treat side props such as bond, seal, remover, or applicator as included unless packaging, SKU data, or the user confirms them\./gi, "胶水、封层、卸除液、镊子/夹子等侧边道具，不能默认视为包含物；必须由包装、SKU 数据或用户确认。")
    .replace(/Use printed packaging text and tray labels as stronger evidence than visual style guesses\./gi, "包装印刷文字和托盘标签的证据等级高于视觉风格猜测。")
    .replace(/Piece count needs confirmation; do not place it in title yet\./gi, "根数需要确认；确认前不要写进标题。")
    .replace(/Length labels need confirmation\./gi, "长度标签需要确认。")
    .replace(/Curl needs confirmation\./gi, "卷度需要确认。")
    .replace(/Band type needs confirmation\./gi, "带型需要确认。")
    .replace(/Kit contents need confirmation if bond, seal or applicator appear only as props\./gi, "如果胶水、封层或夹子只是图片道具，套装内容物需要人工确认。");
}

function fileToPayload(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve({
        name: file.name,
        type: file.type,
        dataUrl: reader.result
      });
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function confirmImageFacts() {
  if (!imageExtraction.facts.length) {
    imageExtraction.confirmed = true;
    imageExtraction.status = "confirmed";
    renderExtractionReview();
    drawTrayPreview();
    setFlowState("confirmed");
    showToast("已确认暂无可用图片事实，识别补充可留空，可以继续生成");
    return;
  }

  const selectedIndexes = $$('input[name="extractedFact"]:checked').map((input) => Number(input.value));
  const selectedFacts = selectedIndexes.map((index) => imageExtraction.facts[index]).filter(Boolean);
  if (!selectedFacts.length) {
    showToast("请至少勾选一个图片事实");
    return;
  }

  selectedFacts.forEach(applyExtractedFact);
  writeConfirmedImageFacts(selectedFacts);
  imageExtraction.confirmed = true;
  imageExtraction.status = "confirmed";
  renderExtractionReview();
  drawTrayPreview();
  setFlowState("confirmed");
  showToast("图片事实已确认，可以继续生成");
}

function applyExtractedFact(fact) {
  if (fact.key === "brandName") $("#brandName").value = fact.value;
  if (fact.key === "lengths") setSelectedLengthOptions(fact.value);
  if (fact.key === "curl") setSelectIfOptionExists("#curl", fact.value);
  if (fact.key === "pieceCount") $("#pieceCount").value = fact.value;
  if (fact.key === "productType") setSelectIfOptionExists("#productType", fact.value);
  if (fact.key === "styleAngle") setSelectIfOptionExists("#styleAngle", fact.value);
  if (fact.key === "bandType") setSelectIfOptionExists("#bandType", fact.value.toLowerCase());
  if (fact.key === "contents") {
    $$('input[name="contents"]').forEach((input) => {
      if (input.value === fact.value.toLowerCase()) input.checked = true;
    });
  }
}

function setSelectIfOptionExists(selector, value) {
  const select = $(selector);
  const lower = cleanText(value).toLowerCase();
  const option = Array.from(select.options).find((item) => item.value.toLowerCase() === lower || item.textContent.toLowerCase() === lower);
  if (option) select.value = option.value;
}

function writeConfirmedImageFacts(facts) {
  const lines = facts.map((fact) => `${fact.label}: ${fact.value}`);
  $("#imageFacts").value = `图片确认事实：${lines.join("；")}。`;
}

function renderExtractionReview() {
  const review = $("#imageExtractionReview");
  const status = $("#extractionStatus");
  if (!review || !status) return;
  const confirmButton = $("#confirmImageFactsBtn");

  const statusText = {
    idle: "上传图片后，先提取图片事实，再确认进入下一步。",
    uploaded: "图片已上传，点击“提取”读取可见事实。",
    extracting: "正在提取图片可见事实...",
    extracted: "请勾选确认可以写入 Listing 的事实。",
    confirmed: "图片事实已确认，可以进入关键词策略和 Listing 生成。"
  };
  status.textContent = statusText[imageExtraction.status] || statusText.idle;
  if (confirmButton) {
    const canConfirmEmptyResult = imageExtraction.status === "extracted";
    confirmButton.disabled = imageExtraction.confirmed || (!imageExtraction.facts.length && !canConfirmEmptyResult);
  }

  if (imageExtraction.status === "idle") {
    review.innerHTML = `<div class="review-empty">还没有上传图片。</div>`;
    renderIcons();
    return;
  }

  const factHtml = imageExtraction.facts.length
    ? imageExtraction.facts
        .map(
          (fact, index) => `
            <label class="review-card">
              <input type="checkbox" name="extractedFact" value="${index}" ${imageExtraction.confirmed ? "disabled" : "checked"} />
              <span>
                <strong>${escapeHtml(fact.label)}: ${escapeHtml(fact.value)}</strong>
                <span>${escapeHtml(fact.source)} · 置信度：${escapeHtml(fact.confidence)}</span>
              </span>
            </label>`
        )
        .join("")
    : `<div class="review-empty">暂无可直接确认的图片事实。</div>`;

  const needsHtml = imageExtraction.needs.length
    ? imageExtraction.needs.map((item) => `<div class="review-card need"><span></span><span><strong>需要确认</strong><span>${escapeHtml(item)}</span></span></div>`).join("")
    : `<div class="review-empty">暂无待确认项。</div>`;

  const blockedHtml = imageExtraction.blocked.length
    ? imageExtraction.blocked.map((item) => `<div class="review-card blocked"><span></span><span><strong>禁止推断</strong><span>${escapeHtml(item)}</span></span></div>`).join("")
    : "";

  review.innerHTML = `
    <section class="review-group">
      <h4><i data-lucide="check-circle-2"></i> 图片确认事实</h4>
      ${factHtml}
    </section>
    <section class="review-group">
      <h4><i data-lucide="help-circle"></i> 需要确认</h4>
      ${needsHtml}
    </section>
    <section class="review-group">
      <h4><i data-lucide="shield-alert"></i> 禁止推断</h4>
      ${blockedHtml}
    </section>`;
  renderIcons();
}

function extractPainSignals(text) {
  const source = text.toLowerCase();
  const signals = [
    ["lifting corners", ["lift", "lifting", "翘", "翘边"]],
    ["poking feel", ["poke", "poking", "扎眼"]],
    ["visible band", ["visible band", "band obvious", "带子明显"]],
    ["glue mess", ["glue mess", "mess", "胶水"]],
    ["hard removal", ["hard removal", "remove", "卸除"]],
    ["heavy strip-lash feel", ["heavy", "strip", "厚重"]]
  ];
  return signals.filter(([, keys]) => keys.some((key) => source.includes(key))).map(([label]) => label);
}

function extractPraiseSignals(text) {
  const source = text.toLowerCase();
  const signals = [
    ["easy to apply", ["easy to apply", "beginner", "新手"]],
    ["natural look", ["natural", "自然"]],
    ["lightweight feel", ["lightweight", "轻盈"]],
    ["wispy finish", ["wispy", "仙子"]],
    ["blends well", ["blend", "融合"]]
  ];
  return signals.filter(([, keys]) => keys.some((key) => source.includes(key))).map(([label]) => label);
}

function extractTermsFromText(text) {
  const phrases = [
    "lash clusters",
    "cluster lashes",
    "clear band",
    "beginner friendly",
    "natural look",
    "soft glam",
    "clean girl",
    "bunny eye",
    "manga",
    "spider",
    "fairy",
    "cat eye",
    "doll eye",
    "anti lift",
    "no prick",
    "easy to apply"
  ];
  const lower = text.toLowerCase();
  return phrases.filter((phrase) => lower.includes(phrase));
}

function extractRankedTerms(text) {
  const source = cleanText(text);
  if (!source) return [];
  const matches = [];
  const rankPattern = /#?\b(?:rank\s*)?(\d{1,3})\b[\s:：.-]*([a-z][a-z0-9\s-]{2,40})/gi;
  let match = rankPattern.exec(source);
  while (match) {
    matches.push({
      rank: Number(match[1]),
      term: sanitizeSearchTerm(match[2]).replace(/\b(top|share|click|rate|rank|aba)\b/g, "").trim()
    });
    match = rankPattern.exec(source);
  }

  const ranked = matches
    .filter((item) => item.term && item.term.length > 2)
    .sort((a, b) => a.rank - b.rank)
    .map((item) => item.term);

  return unique([...ranked, ...extractTermsFromText(source)]);
}

function extractRiskTerms(text) {
  const source = cleanText(text);
  const buckets = {
    high: [],
    medium: [],
    low: []
  };
  if (!source) {
    return { ...buckets, all: [] };
  }

  const knownTerms = unique([
    "best seller",
    "hot sale",
    "free delivery",
    "waterproof",
    "24-hour",
    "hypoallergenic",
    "latex-free",
    "irritation-free",
    "residue-free",
    "safe for sensitive eyes",
    "reusable",
    "medical grade",
    "allergy safe",
    "no irritation",
    "sensitive eyes",
    ...DEFAULT_RISK_LIBRARY.map((item) => item.term)
  ]);

  source
    .split(/[.;；。\n]/)
    .map(cleanText)
    .filter(Boolean)
    .forEach((line) => {
      const lower = line.toLowerCase();
      const level = lower.includes("高") || lower.includes("high")
        ? "high"
        : lower.includes("中") || lower.includes("medium")
          ? "medium"
          : lower.includes("低") || lower.includes("low")
            ? "low"
            : "medium";
      const found = knownTerms.filter((term) => lower.includes(term));
      const looseTerms = line
        .replace(/高风险|中风险|低风险|high risk|medium risk|low risk|high|medium|low|risk|风险|禁用|违规/gi, "")
        .split(/[,，、/]/)
        .map(sanitizeRiskTerm)
        .filter(Boolean);
      buckets[level].push(...found, ...looseTerms);
    });

  buckets.high = unique(buckets.high);
  buckets.medium = unique(buckets.medium).filter((term) => !buckets.high.includes(term));
  buckets.low = unique(buckets.low).filter((term) => !buckets.high.includes(term) && !buckets.medium.includes(term));

  return {
    ...buckets,
    all: unique([...buckets.high, ...buckets.medium, ...buckets.low])
  };
}

function sanitizeRiskTerm(term) {
  return cleanText(term)
    .toLowerCase()
    .replace(/^[：:\-\s]+|[：:\-\s]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function parseTerms(value) {
  return unique(
    String(value || "")
      .split(/[,，;；\n]/)
      .map(cleanText)
      .filter(Boolean)
  );
}

function parseLengths(value) {
  return extractLengthOptions(value);
}

function inferRows(pieceCount) {
  const count = Number(String(pieceCount || "").match(/\d+/)?.[0] || 108);
  if (count >= 144) return 12;
  if (count >= 120) return 10;
  if (count >= 96) return 9;
  return 8;
}

function fitTitle(parts, limit) {
  const cleaned = parts.map(cleanText).filter(Boolean);
  let title = "";
  cleaned.forEach((part) => {
    const separator = title && /\d+pcs/i.test(part) ? " " : title ? " " : "";
    const next = `${title}${separator}${part}`;
    if (next.length <= limit) {
      title = next;
    }
  });
  if (title.length > limit) {
    title = title.slice(0, limit).trim();
  }
  return title.replace(/\s+/g, " ");
}

function fitSentence(sentence, limit) {
  const clean = cleanText(sentence);
  if (clean.length <= limit) return clean;
  const words = clean.split(" ");
  let output = "";
  for (const word of words) {
    const next = output ? `${output} ${word}` : word;
    if (next.length > limit - 1) break;
    output = next;
  }
  return output.replace(/[,.，。;；:-]$/, "");
}

function formatContents(contents) {
  if (!contents.length) return "";
  return contents.map((item) => titleCase(item)).join(", ");
}

function sanitizeSearchTerm(term) {
  return cleanText(term)
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .replace(/\b(a|an|and|the|for|with|of|to)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function containsForbidden(term, forbidden) {
  return forbidden.some((item) => item && term.toLowerCase().includes(item.toLowerCase()));
}

function isClaimTerm(term) {
  return /waterproof|24-hour|hypoallergenic|latex-free|irritation-free|residue-free|sensitive eyes|reusable/i.test(term);
}

function isClaimVerified(term, verifiedClaims) {
  const lower = term.toLowerCase();
  return verifiedClaims.some((claim) => lower.includes(claim));
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function titleCase(value) {
  return cleanText(value)
    .split(" ")
    .map((word) => {
      if (/^[A-Z0-9-]+$/.test(word)) return word;
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(" ");
}

function labelTone(value) {
  const map = {
    "beauty factual": "美妆事实",
    "premium soft": "柔和高级",
    "direct conversion": "直接转化",
    "clean minimal": "清爽克制"
  };
  return map[value] || value || "待观察";
}

function labelBulletPattern(value) {
  const map = {
    painSolutionScene: "痛点方案",
    benefitSpecScene: "效果规格",
    routineFirst: "流程优先"
  };
  return map[value] || value || "待观察";
}

function unique(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = cleanText(item).toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function byteLength(text) {
  return new TextEncoder().encode(text || "").length;
}

function toList(items) {
  return items.map((item) => `- ${item}`).join("\n");
}

function toNumbered(items) {
  return items.map((item, index) => `${index + 1}. ${item}`).join("\n");
}

function renderTagMatrixText(matrix) {
  return Object.entries(matrix)
    .map(([key, values]) => `${key}: ${values.join(", ")}`)
    .join("\n");
}

function buildSkillMarkdown(skill) {
  const referenceSection = cleanText(skill.referenceListing)
    ? `\n## Historical Listing Reference\n\n${skill.referenceListing}\n`
    : "";
  const learning = getSkillLearning(skill);
  const learningSection = learning.learnedRules.length
    ? `\n## Personal Learning\n\n${learning.learnedRules.map((rule) => `- ${rule}`).join("\n")}\n`
    : "";
  return `---
name: ${skill.name}
description: Personal Amazon listing generation skill for category-specific product facts, MCP keyword data, competitor review signals, A9/COSMO/Rufus coverage, and compliance self-checks.
---

# ${skill.name}

## Core Rules

- Title limit: ${skill.titleLimit} characters.
- Item Highlights limit: ${skill.itemHighlightLimit} characters.
- Bullet limit: ${skill.bulletLimit} characters each.
- Product description limit: ${skill.descriptionLimit} characters.
- Backend Search Terms limit: ${skill.searchTermLimit} bytes.
- Title strategy: ${skill.titleStrategy}.
- Tone: ${skill.tone}.
- Bullet pattern: ${skill.bulletPattern}.

## Forbidden Or High-Risk Claims

${parseTerms(skill.forbiddenClaims).map((item) => `- ${item}`).join("\n")}

## Custom Rules

${skill.customRules}

## Generation Workflow

1. Confirm product facts from user input, packaging and images.
2. Map MCP data into T1/T2/T3/T4 keywords.
3. Generate strategy before final copy.
4. Generate title, Item Highlights, internal selling-point summaries, five bullets, description, image/A+ plan, backend Search Terms and Rufus Q&A.
5. Run character, byte, unsupported-claim and duplication checks.
${learningSection}${referenceSection}`;
}

function downloadText(filename, content) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function slugify(value) {
  return cleanText(value)
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
    .replace(/^-|-$/g, "") || "listing-skill";
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fallbackCopy(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2200);
}

function renderIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}
