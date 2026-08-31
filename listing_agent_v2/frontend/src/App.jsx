import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowClockwise,
  CaretDown,
  Check,
  CheckCircle,
  ClipboardText,
  Copy,
  FileArrowDown,
  ImageSquare,
  MagicWand,
  PencilSimple,
  Sparkle,
  SpinnerGap,
  Translate,
  UploadSimple,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { backfillImageFacts } from "./imageFactBackfill.js";

const VARIANT_META = {
  balanced: { name: "均衡版", badge: "推荐" },
  style: { name: "风格版", badge: "场景" },
  search: { name: "搜索版", badge: "关键词" },
};

const EMPTY_FORM = {
  marketplace: "US",
  language: "English (US)",
  productType: "",
  brandName: "",
  styleAngle: "",
  lengths: "",
  curl: "",
  bandType: "",
  pieceCount: "",
  contents: "",
  imageFacts: "",
  t1Keywords: "",
  t2Keywords: "",
  t3Keywords: "",
  forbiddenTerms: "",
  referenceListing: "",
  tone: "Direct Conversion",
  titleStrategy: "coreFirst",
};

const DEMO_FORM = {
  ...EMPTY_FORM,
  productType: "DIY lash clusters kit",
  brandName: "Mamzy Luxe",
  styleAngle: "wispy natural look",
  lengths: "10/12/14mm",
  curl: "D Curl",
  bandType: "clear band",
  pieceCount: "120 clusters",
  contents: "lash cluster tray, applicator, bond and seal",
  imageFacts: "包装可见：D Curl，10/12/14mm 混合长度，clear band，120 clusters。",
  t1Keywords: "lash clusters, cluster lashes, diy lash extensions, lash clusters kit",
  t2Keywords: "wispy lash clusters, clear band lashes, d curl lash clusters",
  t3Keywords: "work, date, vacation, clean girl makeup, soft glam",
  forbiddenTerms: "waterproof, hypoallergenic, latex free, 24-hour, medical grade",
  referenceListing: "学习结构：标题先讲核心词和规格，五点按功能、规格、场景、使用人群和包装内容组织。",
};

const DEMO_VARIANTS = [
  {
    id: "balanced",
    title: "DIY Lash Clusters Kit D Curl 10-14mm Clear Band Wispy Lashes",
    itemHighlight: "Customizable wispy lash clusters with mixed lengths for work, dates and soft glam looks",
    highlights: ["Mixed-length styling", "Clear band", "D Curl"],
    bullets: [
      "CUSTOMIZABLE WISPY LOOK - Build a soft everyday lash map or add definition at the outer corners with small clusters.",
      "MIXED 10/12/14MM LENGTHS - Combine shorter and longer clusters to shape inner, middle and outer sections with more control.",
      "D CURL WITH CLEAR BAND - Confirmed tray details keep the lash line visually light while supporting a lifted style direction.",
      "FOR WORK, DATES AND SOFT GLAM - Adjust density to suit clean girl makeup, vacation photos or a more polished evening look.",
      "KIT CONTENTS KEPT CLEAR - Includes the confirmed lash tray, applicator, bond and seal shown in the supplied product information.",
    ],
    description:
      "Create a personalized lash map with DIY lash clusters designed around confirmed D Curl, clear-band and mixed-length details. Use shorter clusters toward the inner corner and add 12mm or 14mm pieces where you want more visible lift. The result can move from wearable daily definition to a fuller soft-glam finish without relying on unsupported performance claims.",
    searchTerms: "individual lashes underlash wispy eyelashes cluster extension refill natural makeup",
    reasons: ["关键词、可读性与场景信息均衡"],
  },
  {
    id: "style",
    title: "Wispy Lash Clusters D Curl Clear Band 10-14mm DIY Lash Kit",
    itemHighlight: "Soft wispy definition with customizable mixed lengths for clean girl makeup and date-night looks",
    highlights: ["Style-led", "Scene coverage", "Mixed lengths"],
    bullets: [
      "SOFT WISPY DEFINITION - Layer the clusters from light to full for a finish that works with clean makeup or soft glam.",
      "SHAPE YOUR OWN LASH MAP - Use 10mm, 12mm and 14mm clusters to customize lift and density across the lash line.",
      "VISIBLE D CURL DETAIL - The confirmed curl and clear-band design support a lifted look without adding unverified claims.",
      "READY FOR REAL ROUTINES - Style for workdays, date nights, vacation makeup or photos when you want controlled definition.",
      "CONFIRMED KIT SET - Product information covers the lash tray, applicator, bond and seal for a clear purchase decision.",
    ],
    description:
      "Build a wispy lash look around the way you actually wear makeup. The mixed 10/12/14mm lengths help shape a subtle inner corner and a more lifted outer edge, while the confirmed D Curl and clear band keep the Listing grounded in visible product facts.",
    searchTerms: "under lash extensions segmented eyelashes soft glam eye makeup refill clusters",
    reasons: ["风格词和场景词更突出"],
  },
  {
    id: "search",
    title: "Lash Clusters Kit DIY Lash Extensions D Curl 10-14mm Clear Band",
    itemHighlight: "Search-focused lash cluster kit with confirmed D Curl, clear band and mixed 10/12/14mm lengths",
    highlights: ["Core term first", "Specification rich", "Backend coverage"],
    bullets: [
      "LASH CLUSTERS KIT FOR DIY STYLING - Create a customizable lash extension look with small clusters placed under the lash line.",
      "10/12/14MM MIXED LENGTHS - Use the confirmed size range to compare inner, center and outer-corner placement options.",
      "D CURL CLEAR BAND LASHES - Verified tray details give shoppers the practical specifications they need before buying.",
      "WISPY OR NATURAL LASH MAPS - Change cluster placement to move from daily definition to fuller soft-glam eye makeup.",
      "TRAY, APPLICATOR, BOND AND SEAL - The Listing names only the kit contents confirmed in the supplied product information.",
    ],
    description:
      "This DIY lash extensions kit combines D Curl lash clusters, a clear band and 10/12/14mm mixed lengths. The copy prioritizes high-intent category terms while keeping the product description readable and based on confirmed facts.",
    searchTerms: "segmented lashes underlash false eyelashes individual extension kit eye clusters refill",
    reasons: ["标题核心词前置，搜索覆盖更集中"],
  },
];

const SECTION_DEFINITIONS = [
  { id: "market", index: "1", title: "市场与生成范围" },
  { id: "product", index: "2", title: "产品信息与图片" },
  { id: "keywords", index: "3", title: "关键词" },
  { id: "negative", index: "4", title: "否定词（可选）" },
  { id: "reference", index: "5", title: "竞品/参考 Listing 学习（可选）" },
];

export function App() {
  const [form, setForm] = useState(EMPTY_FORM);
  const [expanded, setExpanded] = useState("market");
  const [images, setImages] = useState([]);
  const [imageState, setImageState] = useState("idle");
  const [variants, setVariants] = useState([]);
  const [activeId, setActiveId] = useState("balanced");
  const [loading, setLoading] = useState(false);
  const [editingKey, setEditingKey] = useState("");
  const [translations, setTranslations] = useState({});
  const [toast, setToast] = useState("");
  const [refineTarget, setRefineTarget] = useState(null);
  const [refineInstruction, setRefineInstruction] = useState("");
  const [refining, setRefining] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("demo") === "1") {
      setForm(DEMO_FORM);
      setVariants(DEMO_VARIANTS);
      setActiveId("balanced");
    }
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(""), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const activeVariant = useMemo(
    () => variants.find((item) => item.id === activeId) || variants[0] || null,
    [activeId, variants],
  );
  const keywords = useMemo(() => buildKeywordList(form), [form]);
  const coverage = useMemo(
    () => calculateCoverage(activeVariant, keywords),
    [activeVariant, keywords],
  );

  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  async function handleImages(files) {
    const selected = [...files].filter((file) => file.type.startsWith("image/")).slice(0, 4);
    if (!selected.length) return;
    const next = await Promise.all(
      selected.map(async (file) => ({
        name: file.name,
        type: file.type,
        dataUrl: await readFileAsDataUrl(file),
      })),
    );
    setImages(next);
    setImageState("ready");
    setExpanded("product");
  }

  async function recognizeImages() {
    if (!images.length) {
      setToast("请先上传产品图片");
      return;
    }
    setImageState("loading");
    try {
      const response = await fetch("/listing-agent/api/extract-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          marketplace: form.marketplace,
          category: form.productType || "false eyelashes",
          images,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || result.message || "图片识别失败");
      const recognizedFacts = Array.isArray(result.facts) ? result.facts : [];
      const facts = recognizedFacts
        .map((item) => `${item.label || item.key || "事实"}：${item.value || ""}`)
        .filter((item) => !item.endsWith("："));
      const needs = (result.needsConfirmation || []).map((item) => `待确认：${item}`);
      const imageFacts = [...facts, ...needs].join("\n");
      setForm((current) => {
        const { nextForm } = backfillImageFacts(current, recognizedFacts);
        return { ...nextForm, imageFacts };
      });
      setImageState("done");
      setToast("已识别并自动回填商品信息，请核对后生成");
    } catch (error) {
      setImageState("error");
      setToast(error.message || "图片识别失败，可手动填写事实");
    }
  }

  async function generateListing() {
    if (!form.productType.trim()) {
      setExpanded("product");
      setToast("请先填写商品种类");
      return;
    }
    setLoading(true);
    try {
      const response = await fetch("/listing-agent/api/generate-listings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildGenerationPayload(form)),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || result.error || "Listing 生成失败");
      const normalized = (result.variants || []).map((variant) => ({
        ...variant,
        ...(VARIANT_META[variant.id] || {}),
      }));
      if (normalized.length !== 3) throw new Error("AI 未返回完整的三版 Listing");
      setVariants(normalized);
      setActiveId(normalized.find((item) => item.id === "balanced")?.id || normalized[0].id);
      setTranslations({});
      setEditingKey("");
      setToast(
        result.storage?.persistenceFailed
          ? "Listing 已生成，但自动存档失败，请先下载草稿"
          : "Listing 已生成并自动存档",
      );
    } catch (error) {
      setToast(error.message || "Listing 生成失败");
    } finally {
      setLoading(false);
    }
  }

  function updateActiveField(fieldKey, value) {
    setVariants((current) =>
      current.map((variant) => {
        if (variant.id !== activeId) return variant;
        if (fieldKey.startsWith("bullet-")) {
          const index = Number(fieldKey.split("-")[1]);
          const bullets = [...variant.bullets];
          bullets[index] = value;
          return { ...variant, bullets };
        }
        return { ...variant, [fieldKey]: value };
      }),
    );
  }

  async function copyContent(value) {
    try {
      await navigator.clipboard.writeText(value);
      setToast("已复制到剪贴板");
    } catch {
      setToast("复制失败，请手动选中内容");
    }
  }

  async function translateField(fieldKey, label, limit) {
    if (!activeVariant) return;
    const content = getVariantField(activeVariant, fieldKey);
    setTranslations((current) => ({ ...current, [fieldKey]: "loading" }));
    try {
      const result = await requestRefine({
        action: "translate",
        field: label,
        content,
        keywords: keywords.map((item) => item.term),
        limit,
      });
      setTranslations((current) => ({ ...current, [fieldKey]: result.content }));
    } catch (error) {
      setTranslations((current) => ({ ...current, [fieldKey]: "" }));
      setToast(error.message || "翻译失败");
    }
  }

  async function applyRefine() {
    if (!refineTarget || !activeVariant) return;
    setRefining(true);
    try {
      const content = getVariantField(activeVariant, refineTarget.fieldKey);
      const result = await requestRefine({
        action: "optimize",
        field: refineTarget.label,
        content,
        instruction: refineInstruction,
        keywords: keywords.map((item) => item.term),
        limit: refineTarget.limit,
      });
      updateActiveField(refineTarget.fieldKey, result.content);
      setRefineTarget(null);
      setRefineInstruction("");
      setToast("已应用 AI 优化结果");
    } catch (error) {
      setToast(error.message || "AI 优化失败");
    } finally {
      setRefining(false);
    }
  }

  function saveDraft() {
    if (!variants.length) {
      setToast("请先生成 Listing");
      return;
    }
    const blob = new Blob(
      [JSON.stringify({ savedAt: new Date().toISOString(), form, variants }, null, 2)],
      { type: "application/json;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `listing-studio-v2-${Date.now()}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setToast("草稿已下载");
  }

  return (
    <main className="studio-shell">
      <header className="studio-header">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true"><Sparkle weight="fill" /></div>
          <div>
            <strong>Focused Split Studio</strong>
            <span>Amazon Listing 智能生成工作台 · V2</span>
          </div>
        </div>
        <div className="header-actions">
          {variants.length > 0 && (
            <div className="variant-switch" aria-label="Listing 版本视图">
              <span>版本视图</span>
              {variants.map((variant) => (
                <button
                  className={variant.id === activeId ? "active" : ""}
                  key={variant.id}
                  onClick={() => {
                    setActiveId(variant.id);
                    setEditingKey("");
                    setTranslations({});
                  }}
                  type="button"
                >
                  {VARIANT_META[variant.id]?.name || variant.name || variant.id}
                </button>
              ))}
            </div>
          )}
          <button className="quiet-button" onClick={generateListing} disabled={loading} type="button">
            <ArrowClockwise />
            重新生成
          </button>
        </div>
      </header>

      <div className="studio-workspace">
        <aside className="input-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">新版工作流</span>
              <h1>输入配置</h1>
            </div>
            <button className="text-button" onClick={() => setExpanded("")} type="button">
              收起全部
            </button>
          </div>

          <div className="accordion-list">
            {SECTION_DEFINITIONS.map((section) => (
              <AccordionSection
                key={section.id}
                section={section}
                expanded={expanded === section.id}
                complete={isSectionComplete(section.id, form, images)}
                onToggle={() => setExpanded(expanded === section.id ? "" : section.id)}
              >
                {section.id === "market" && (
                  <MarketFields form={form} setField={setField} />
                )}
                {section.id === "product" && (
                  <ProductFields
                    form={form}
                    setField={setField}
                    images={images}
                    imageState={imageState}
                    fileInputRef={fileInputRef}
                    onFiles={handleImages}
                    onRecognize={recognizeImages}
                  />
                )}
                {section.id === "keywords" && (
                  <KeywordFields form={form} setField={setField} />
                )}
                {section.id === "negative" && (
                  <NegativeFields form={form} setField={setField} />
                )}
                {section.id === "reference" && (
                  <ReferenceFields form={form} setField={setField} />
                )}
              </AccordionSection>
            ))}
          </div>

          <div className="input-footer">
            <button className="primary-button" onClick={generateListing} disabled={loading} type="button">
              {loading ? <SpinnerGap className="spin" /> : <MagicWand weight="fill" />}
              {loading ? "AI 生成中…" : "生成 Listing"}
            </button>
            <button className="secondary-button" onClick={saveDraft} type="button">
              <FileArrowDown />
              保存草稿
            </button>
            <p>AI 生成内容仅供参考，请确保符合 Amazon 政策与最新要求。</p>
          </div>
        </aside>

        <section className="result-panel">
          <div className="result-heading">
            <div>
              <span className="eyebrow">方案交付</span>
              <h2>生成结果</h2>
            </div>
            {activeVariant && (
              <span className="saved-status"><CheckCircle weight="fill" /> 已通过基础长度检查</span>
            )}
          </div>

          {!activeVariant ? (
            <EmptyResult onDemo={() => {
              setForm(DEMO_FORM);
              setVariants(DEMO_VARIANTS);
              setActiveId("balanced");
            }} />
          ) : (
            <div className="result-scroll">
              <CoveragePanel coverage={coverage} />
              <div className="content-stack">
                <ListingField
                  label="Title"
                  fieldKey="title"
                  value={activeVariant.title}
                  limit={75}
                  keywords={keywords}
                  editingKey={editingKey}
                  translation={translations.title}
                  onEdit={setEditingKey}
                  onChange={updateActiveField}
                  onCopy={copyContent}
                  onTranslate={translateField}
                  onOptimize={(target) => setRefineTarget(target)}
                />
                <ListingField
                  label="Item Highlights"
                  fieldKey="itemHighlight"
                  value={activeVariant.itemHighlight}
                  limit={125}
                  keywords={keywords}
                  editingKey={editingKey}
                  translation={translations.itemHighlight}
                  onEdit={setEditingKey}
                  onChange={updateActiveField}
                  onCopy={copyContent}
                  onTranslate={translateField}
                  onOptimize={(target) => setRefineTarget(target)}
                />
                <section className="listing-group">
                  <div className="group-heading">
                    <div><strong>Bullet Points</strong><span>5 条 · 每条不超过 500 字符</span></div>
                  </div>
                  <div className="bullet-list">
                    {activeVariant.bullets.map((bullet, index) => (
                      <ListingField
                        compact
                        key={`bullet-${index}`}
                        label={`要点 ${index + 1}`}
                        fieldKey={`bullet-${index}`}
                        value={bullet}
                        limit={500}
                        keywords={keywords}
                        editingKey={editingKey}
                        translation={translations[`bullet-${index}`]}
                        onEdit={setEditingKey}
                        onChange={updateActiveField}
                        onCopy={copyContent}
                        onTranslate={translateField}
                        onOptimize={(target) => setRefineTarget(target)}
                      />
                    ))}
                  </div>
                </section>
                <ListingField
                  label="Product Description"
                  fieldKey="description"
                  value={activeVariant.description}
                  limit={2000}
                  keywords={keywords}
                  editingKey={editingKey}
                  translation={translations.description}
                  onEdit={setEditingKey}
                  onChange={updateActiveField}
                  onCopy={copyContent}
                  onTranslate={translateField}
                  onOptimize={(target) => setRefineTarget(target)}
                  multiline
                />
                <ListingField
                  label="Search Terms"
                  fieldKey="searchTerms"
                  value={activeVariant.searchTerms}
                  limit={249}
                  byteLimit
                  keywords={keywords}
                  editingKey={editingKey}
                  translation={translations.searchTerms}
                  onEdit={setEditingKey}
                  onChange={updateActiveField}
                  onCopy={copyContent}
                  onTranslate={translateField}
                  onOptimize={(target) => setRefineTarget(target)}
                />
              </div>
            </div>
          )}
        </section>
      </div>

      {refineTarget && (
        <RefineDialog
          target={refineTarget}
          instruction={refineInstruction}
          setInstruction={setRefineInstruction}
          loading={refining}
          onClose={() => setRefineTarget(null)}
          onApply={applyRefine}
        />
      )}
      {toast && <div className="toast" role="status">{toast}</div>}
    </main>
  );
}

function AccordionSection({ section, expanded, complete, onToggle, children }) {
  return (
    <section className={`accordion-section ${expanded ? "expanded" : ""}`}>
      <button className="accordion-trigger" onClick={onToggle} type="button" aria-expanded={expanded}>
        <span className="section-index">{section.index}</span>
        <strong>{section.title}</strong>
        {complete && !expanded && <CheckCircle className="complete-icon" weight="fill" />}
        <CaretDown className="caret" />
      </button>
      {expanded && <div className="accordion-content">{children}</div>}
    </section>
  );
}

function MarketFields({ form, setField }) {
  return (
    <div className="field-stack">
      <Field label="Marketplace" required>
        <select value={form.marketplace} onChange={(event) => setField("marketplace", event.target.value)}>
          <option value="US">美国站 · Amazon.com</option>
          <option value="CA">加拿大站 · Amazon.ca</option>
          <option value="UK">英国站 · Amazon.co.uk</option>
          <option value="DE">德国站 · Amazon.de</option>
        </select>
      </Field>
      <Field label="生成内容">
        <div className="check-row">
          {["Title", "Item Highlights", "五点", "描述", "Search Terms"].map((item) => (
            <label className="check-option" key={item}>
              <input type="checkbox" checked readOnly />
              <span><Check weight="bold" /></span>
              {item}
            </label>
          ))}
        </div>
      </Field>
      <Field label="语言">
        <select value={form.language} onChange={(event) => setField("language", event.target.value)}>
          <option>English (US)</option>
          <option>English (UK)</option>
          <option>Deutsch</option>
        </select>
      </Field>
    </div>
  );
}

function ProductFields({ form, setField, images, imageState, fileInputRef, onFiles, onRecognize }) {
  return (
    <div className="field-stack">
      <div className="two-column-fields">
        <Field label="商品种类" required>
          <input value={form.productType} onChange={(event) => setField("productType", event.target.value)} placeholder="例如：DIY lash clusters kit" />
        </Field>
        <Field label="品牌名称">
          <input value={form.brandName} onChange={(event) => setField("brandName", event.target.value)} placeholder="可选" />
        </Field>
      </div>
      <Field label="风格/主要场景">
        <input value={form.styleAngle} onChange={(event) => setField("styleAngle", event.target.value)} placeholder="例如：wispy natural look, work and date" />
      </Field>
      <div className="three-column-fields">
        <Field label="规格/长度"><input value={form.lengths} onChange={(event) => setField("lengths", event.target.value)} placeholder="10/12/14mm" /></Field>
        <Field label="卷度"><input value={form.curl} onChange={(event) => setField("curl", event.target.value)} placeholder="D Curl" /></Field>
        <Field label="带型"><input value={form.bandType} onChange={(event) => setField("bandType", event.target.value)} placeholder="clear band" /></Field>
      </div>
      <div className="two-column-fields">
        <Field label="数量"><input value={form.pieceCount} onChange={(event) => setField("pieceCount", event.target.value)} placeholder="120 clusters" /></Field>
        <Field label="包装内容"><input value={form.contents} onChange={(event) => setField("contents", event.target.value)} placeholder="tray, applicator…" /></Field>
      </div>
      <Field label="产品图片（可选）">
        <input
          ref={fileInputRef}
          className="sr-only"
          type="file"
          accept="image/*"
          multiple
          onChange={(event) => onFiles(event.target.files)}
        />
        <button className="upload-zone" onClick={() => fileInputRef.current?.click()} type="button">
          <UploadSimple />
          <span>{images.length ? `已选择 ${images.length} 张图片` : "上传包装或产品图"}</span>
          <small>最多 4 张，用于提取可见事实</small>
        </button>
        {images.length > 0 && (
          <div className="image-preview-row">
            {images.map((image) => <img src={image.dataUrl} alt={image.name} key={image.name} />)}
            <button className="secondary-button compact-button" onClick={onRecognize} disabled={imageState === "loading"} type="button">
              {imageState === "loading" ? <SpinnerGap className="spin" /> : <ImageSquare />}
              {imageState === "done" ? "重新识别" : "识别图片事实"}
            </button>
          </div>
        )}
      </Field>
      <Field label="图片事实确认">
        <textarea value={form.imageFacts} onChange={(event) => setField("imageFacts", event.target.value)} rows="4" placeholder="可手动填写包装文字、规格和可见内容；识别补充为可选。" />
      </Field>
    </div>
  );
}

function KeywordFields({ form, setField }) {
  return (
    <div className="field-stack">
      <Field label="T1 核心词"><TagTextarea value={form.t1Keywords} onChange={(value) => setField("t1Keywords", value)} placeholder="lash clusters, cluster lashes" /></Field>
      <Field label="T2 转化词/细分词"><TagTextarea value={form.t2Keywords} onChange={(value) => setField("t2Keywords", value)} placeholder="wispy lash clusters, clear band lashes" /></Field>
      <Field label="T3 场景词"><TagTextarea value={form.t3Keywords} onChange={(value) => setField("t3Keywords", value)} placeholder="work, date, vacation, soft glam" /></Field>
      <p className="field-help">生成后右侧会按词层高亮，并统计使用次数和覆盖率。</p>
    </div>
  );
}

function NegativeFields({ form, setField }) {
  return (
    <div className="field-stack">
      <Field label="禁用词/高风险词">
        <TagTextarea value={form.forbiddenTerms} onChange={(value) => setField("forbiddenTerms", value)} placeholder="waterproof, hypoallergenic, latex free" />
      </Field>
      <div className="notice-box"><WarningCircle /> 未有包装或检测证据的功效、材质和医疗性声明不应进入 Listing。</div>
    </div>
  );
}

function ReferenceFields({ form, setField }) {
  return (
    <div className="field-stack">
      <div className="two-column-fields">
        <Field label="语气">
          <select value={form.tone} onChange={(event) => setField("tone", event.target.value)}>
            <option>Direct Conversion</option>
            <option>Natural Premium</option>
            <option>Beauty Editorial</option>
          </select>
        </Field>
        <Field label="标题策略">
          <select value={form.titleStrategy} onChange={(event) => setField("titleStrategy", event.target.value)}>
            <option value="coreFirst">核心词前置</option>
            <option value="brandFirst">品牌前置</option>
            <option value="styleFirst">风格前置</option>
          </select>
        </Field>
      </div>
      <Field label="参考 Listing/写法要点">
        <textarea value={form.referenceListing} onChange={(event) => setField("referenceListing", event.target.value)} rows="6" placeholder="粘贴竞品 Listing 或只写需要学习的结构、语气和信息顺序。" />
      </Field>
    </div>
  );
}

function Field({ label, required = false, children }) {
  return (
    <label className="field-label">
      <span>{label}{required && <b>*</b>}</span>
      {children}
    </label>
  );
}

function TagTextarea({ value, onChange, placeholder }) {
  const tags = parseTerms(value);
  return (
    <div className="tag-input-wrap">
      {tags.length > 0 && <div className="tag-preview">{tags.slice(0, 8).map((tag) => <span key={tag}>{tag}</span>)}</div>}
      <textarea value={value} onChange={(event) => onChange(event.target.value)} rows="3" placeholder={placeholder} />
    </div>
  );
}

function EmptyResult({ onDemo }) {
  return (
    <div className="empty-result">
      <div className="empty-icon"><ClipboardText /></div>
      <h3>等待生成 Listing</h3>
      <p>在左侧填写商品种类和已确认事实，再点击“生成 Listing”。</p>
      <button className="secondary-button" onClick={onDemo} type="button">查看示例结果</button>
    </div>
  );
}

function CoveragePanel({ coverage }) {
  return (
    <section className="coverage-panel">
      <div className="coverage-heading">
        <div><strong>关键词覆盖分析</strong><span>基于左侧当前词层</span></div>
        <span className="coverage-status"><CheckCircle weight="fill" /> 已实时重算</span>
      </div>
      <div className="coverage-metrics">
        <Metric label="核心词覆盖率" value={`${coverage.rate}%`} accent />
        <Metric label="关键词使用" value={`${coverage.covered}/${coverage.total}`} />
        <Metric label="高优先词覆盖" value={`${coverage.highCovered}/${coverage.highTotal}`} />
        <Metric label="Search Terms 字节" value={`${coverage.searchBytes}/249 bytes`} />
      </div>
    </section>
  );
}

function Metric({ label, value, accent = false }) {
  return <div className={`metric ${accent ? "accent" : ""}`}><span>{label}</span><strong>{value}</strong></div>;
}

function ListingField({
  label,
  fieldKey,
  value,
  limit,
  byteLimit = false,
  keywords,
  editingKey,
  translation,
  onEdit,
  onChange,
  onCopy,
  onTranslate,
  onOptimize,
  multiline = false,
  compact = false,
}) {
  const editing = editingKey === fieldKey;
  const used = byteLimit ? byteLength(value) : value.length;
  const over = used > limit;
  return (
    <section className={`listing-field ${compact ? "compact" : ""}`}>
      <div className="listing-field-head">
        <div className="field-title"><strong>{label}</strong><span>{byteLimit ? `≤${limit} bytes` : `≤${limit} 字符`}</span></div>
        <div className="field-actions">
          <button onClick={() => onCopy(value)} type="button"><Copy />复制</button>
          <button onClick={() => onEdit(editing ? "" : fieldKey)} type="button"><PencilSimple />{editing ? "完成" : "编辑"}</button>
          <button onClick={() => onTranslate(fieldKey, label, limit)} type="button"><Translate />翻译</button>
          <button onClick={() => onOptimize({ fieldKey, label, limit })} type="button"><Sparkle weight="fill" />AI 优化</button>
        </div>
      </div>
      {editing ? (
        <textarea
          className="listing-editor"
          value={value}
          rows={multiline ? 6 : compact ? 3 : 4}
          onChange={(event) => onChange(fieldKey, event.target.value)}
          autoFocus
        />
      ) : (
        <div className={`listing-copy ${multiline ? "multiline" : ""}`}>
          <HighlightText text={value} keywords={keywords} />
        </div>
      )}
      <span className={`field-count ${over ? "over" : ""}`}>{used}/{limit}{byteLimit ? " bytes" : ""}</span>
      {translation === "loading" && <div className="translation-row"><SpinnerGap className="spin" /> 翻译中…</div>}
      {translation && translation !== "loading" && <div className="translation-row">{translation}</div>}
    </section>
  );
}

function HighlightText({ text, keywords }) {
  if (!text) return null;
  const available = keywords.filter((item) => item.term.length > 1).sort((a, b) => b.term.length - a.term.length);
  if (!available.length) return text;
  const lookup = new Map(available.map((item) => [item.term.toLowerCase(), item.tier]));
  const expression = new RegExp(`(${available.map((item) => escapeRegex(item.term)).join("|")})`, "gi");
  return text.split(expression).map((part, index) => {
    const tier = lookup.get(part.toLowerCase());
    return tier ? <mark className={`keyword-highlight ${tier}`} key={`${part}-${index}`}>{part}</mark> : part;
  });
}

function RefineDialog({ target, instruction, setInstruction, loading, onClose, onApply }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="refine-dialog" role="dialog" aria-modal="true" aria-label={`AI 优化 ${target.label}`}>
        <div className="dialog-head">
          <div><span className="eyebrow">定向优化</span><h3>AI 优化 · {target.label}</h3></div>
          <button className="icon-button" onClick={onClose} type="button"><X /></button>
        </div>
        <p>只改写当前模块，其他 Listing 内容保持不变。</p>
        <div className="suggestion-row">
          {["增加未覆盖的高优先词", "语气更自然，减少堆词", "强化场景和使用动机"].map((item) => (
            <button key={item} onClick={() => setInstruction(item)} type="button">{item}</button>
          ))}
        </div>
        <textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} rows="5" placeholder="输入具体修改要求…" autoFocus />
        <div className="dialog-actions">
          <button className="secondary-button" onClick={onClose} type="button">取消</button>
          <button className="primary-button" onClick={onApply} disabled={loading} type="button">
            {loading ? <SpinnerGap className="spin" /> : <Sparkle weight="fill" />}
            {loading ? "优化中…" : "应用 AI 优化"}
          </button>
        </div>
      </section>
    </div>
  );
}

function buildGenerationPayload(form) {
  const t1 = parseTerms(form.t1Keywords);
  const t2 = parseTerms(form.t2Keywords);
  const t3 = parseTerms(form.t3Keywords);
  return {
    marketplace: form.marketplace,
    product: {
      brand: form.brandName,
      type: form.productType,
      style: form.styleAngle,
      lengths: form.lengths,
      curl: form.curl,
      bandType: form.bandType,
      pieceCount: form.pieceCount,
      contents: parseTerms(form.contents),
      verifiedClaims: [],
      imageFacts: form.imageFacts,
      needsConfirmation: [],
    },
    keywords: {
      t1,
      t2,
      t3,
      rankingPriority: t1.map((term) => ({ term })),
      growthPriority: t2.map((term) => ({ term })),
      conversionPriority: t2.map((term) => ({ term })),
      backendPriority: [...t2, ...t3].map((term) => ({ term })),
    },
    compliance: {
      forbiddenTerms: parseTerms(form.forbiddenTerms),
      customRules: "Title <=75 characters; Item Highlights <=125 characters; avoid unsupported claims and keyword stuffing.",
    },
    skill: {
      name: "Focused Split Studio V2",
      titleStrategy: form.titleStrategy,
      tone: form.tone,
      bulletPattern: "painSolutionScene",
      learnedRules: [],
      historicalReference: form.referenceListing,
    },
    limits: {
      title: 75,
      itemHighlight: 125,
      bullet: 500,
      description: 2000,
      searchTermsBytes: 249,
    },
    variants: [
      { id: "balanced", name: "均衡版", direction: "关键词、可读性和转化均衡" },
      { id: "style", name: "风格版", direction: "强调场景与审美表达" },
      { id: "search", name: "搜索版", direction: "强调高意图关键词覆盖" },
    ],
  };
}

async function requestRefine(payload) {
  const response = await fetch("/listing-agent-v2/api/refine", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || "AI 处理失败");
  return result;
}

function buildKeywordList(form) {
  const seen = new Set();
  return [
    ...parseTerms(form.t1Keywords).map((term) => ({ term, tier: "t1" })),
    ...parseTerms(form.t2Keywords).map((term) => ({ term, tier: "t2" })),
    ...parseTerms(form.t3Keywords).map((term) => ({ term, tier: "t3" })),
  ].filter((item) => {
    const key = item.term.toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function calculateCoverage(variant, keywords) {
  if (!variant) return { rate: 0, covered: 0, total: keywords.length, highCovered: 0, highTotal: 0, searchBytes: 0 };
  const copy = [variant.title, variant.itemHighlight, ...(variant.bullets || []), variant.description, variant.searchTerms].join(" ").toLowerCase();
  const covered = keywords.filter((item) => copy.includes(item.term.toLowerCase()));
  const high = keywords.filter((item) => item.tier === "t1");
  const highCovered = high.filter((item) => copy.includes(item.term.toLowerCase()));
  return {
    rate: keywords.length ? Math.round((covered.length / keywords.length) * 100) : 0,
    covered: covered.length,
    total: keywords.length,
    highCovered: highCovered.length,
    highTotal: high.length,
    searchBytes: byteLength(variant.searchTerms || ""),
  };
}

function isSectionComplete(id, form, images) {
  if (id === "market") return Boolean(form.marketplace && form.language);
  if (id === "product") return Boolean(form.productType && (form.imageFacts || images.length));
  if (id === "keywords") return Boolean(parseTerms(form.t1Keywords).length);
  if (id === "negative") return Boolean(parseTerms(form.forbiddenTerms).length);
  if (id === "reference") return Boolean(form.referenceListing);
  return false;
}

function getVariantField(variant, fieldKey) {
  if (fieldKey.startsWith("bullet-")) return variant.bullets[Number(fieldKey.split("-")[1])] || "";
  return variant[fieldKey] || "";
}

function parseTerms(value) {
  return [...new Set(String(value || "").split(/[,\n;，；]+/).map((item) => item.trim()).filter(Boolean))];
}

function byteLength(value) {
  return new TextEncoder().encode(String(value || "")).length;
}

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
