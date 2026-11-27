import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowClockwise,
  CheckCircle,
  LockKey,
  SlidersHorizontal,
  Warning,
  X,
} from "@phosphor-icons/react";
import {
  executeSpControl,
  fetchSpControlCapabilities,
  previewSpControl,
} from "./adDiagnosticApi.js";
import { campaignIdOf, campaignNameOf, focusProducts, rowsOf, valueOf } from "./adDiagnosticModel.js";

const STATE_OPTIONS = [
  ["enabled", "开启"],
  ["paused", "暂停"],
  ["archived", "归档"],
];
const STRATEGY_OPTIONS = [
  ["legacyForSales", "动态竞价－只降低"],
  ["autoForSales", "动态竞价－提高和降低"],
  ["manual", "固定竞价"],
];
const MATCH_OPTIONS = [
  ["exact", "精准"],
  ["phrase", "词组"],
  ["broad", "广泛"],
];
const NEGATIVE_MATCH_OPTIONS = MATCH_OPTIONS.slice(0, 2);

const FIELDS = {
  campaign_state: [{ key: "state", label: "活动状态", options: STATE_OPTIONS }],
  campaign_budget: [{ key: "budget", label: "新日预算", type: "number", min: 1, step: 1, suffix: "USD" }],
  campaign_strategy: [{ key: "strategy", label: "竞价策略", options: STRATEGY_OPTIONS }],
  placement_adjustment: [
    { key: "placement_top", label: "搜索首页顶部", type: "number", min: 0, max: 900, step: 1, suffix: "%" },
    { key: "placement_product", label: "商品页面", type: "number", min: 0, max: 900, step: 1, suffix: "%" },
    { key: "placement_rest", label: "其余搜索位置", type: "number", min: 0, max: 900, step: 1, suffix: "%" },
  ],
  ad_group_state: [{ key: "group_id", label: "广告组", source: "groups" }, { key: "state", label: "广告组状态", options: STATE_OPTIONS }],
  ad_group_default_bid: [{ key: "group_id", label: "广告组", source: "groups" }, { key: "default_bid", label: "默认竞价", type: "number", min: 0.02, max: 10, step: 0.01, suffix: "USD" }],
  ad_group_create: [{ key: "name", label: "广告组名称" }, { key: "default_bid", label: "默认竞价", type: "number", min: 0.02, max: 10, step: 0.01, suffix: "USD" }],
  ad_product_state: [{ key: "ad_id", label: "广告商品", source: "products" }, { key: "state", label: "商品状态", options: STATE_OPTIONS }],
  ad_product_create: [{ key: "group_id", label: "广告组", source: "groups" }, { key: "sku", label: "SKU" }, { key: "asin", label: "ASIN" }],
  keyword_bid: [{ key: "target_id", label: "关键词", source: "keywords" }, { key: "bid", label: "新竞价", type: "number", min: 0.02, max: 10, step: 0.01, suffix: "USD" }],
  keyword_state: [{ key: "target_id", label: "关键词", source: "keywords" }, { key: "state", label: "关键词状态", options: STATE_OPTIONS }],
  keyword_create: [{ key: "group_id", label: "广告组", source: "groups" }, { key: "keyword_text", label: "关键词" }, { key: "match_type", label: "匹配类型", options: MATCH_OPTIONS }, { key: "bid", label: "竞价", type: "number", min: 0.02, max: 10, step: 0.01, suffix: "USD" }],
  product_target_bid: [{ key: "target_id", label: "商品投放", source: "targets" }, { key: "bid", label: "新竞价", type: "number", min: 0.02, max: 10, step: 0.01, suffix: "USD" }],
  product_target_state: [{ key: "target_id", label: "商品投放", source: "targets" }, { key: "state", label: "商品投放状态", options: STATE_OPTIONS }],
  product_target_create: [{ key: "group_id", label: "广告组", source: "groups" }, { key: "asin", label: "目标 ASIN" }, { key: "bid", label: "竞价", type: "number", min: 0.02, max: 10, step: 0.01, suffix: "USD" }],
  negative_keyword_create: [{ key: "group_id", label: "广告组", source: "groups" }, { key: "keyword_text", label: "否定关键词" }, { key: "match_type", label: "否定匹配", options: NEGATIVE_MATCH_OPTIONS }],
  negative_keyword_remove: [{ key: "target_id", label: "否定关键词", source: "negativeKeywords" }],
  negative_target_create: [{ key: "group_id", label: "广告组", source: "groups" }, { key: "asin", label: "否定 ASIN" }],
  negative_target_remove: [{ key: "target_id", label: "否定商品", source: "negativeTargets" }],
  campaign_create: [{ key: "name", label: "活动名称" }, { key: "budget", label: "日预算", type: "number", min: 1, step: 1, suffix: "USD" }, { key: "strategy", label: "竞价策略", options: STRATEGY_OPTIONS }],
};

const idOf = (row, ...keys) => String(valueOf(row, ...keys) || "");
const textOf = (row, fallback, ...keys) => String(valueOf(row, ...keys) || fallback);

function controlSources(model) {
  const structure = model?.structure || {};
  const products = focusProducts(model);
  return {
    groups: rowsOf(structure.ad_groups || structure.groups).map((row) => ({ value: idOf(row, "groupId", "group_id"), label: textOf(row, "未命名广告组", "name", "groupName", "group_name"), row })),
    products: products.map((row) => ({ value: idOf(row, "adId", "ad_id"), label: `${textOf(row, "SKU未知", "sku", "msku")} · ${textOf(row, "ASIN未知", "asin")}`, row })),
    keywords: rowsOf(structure.keywords).map((row) => ({ value: idOf(row, "keywordId", "targetId", "target_id"), label: textOf(row, "关键词未返回", "keywordText", "keyword_text", "targeting"), row })),
    targets: rowsOf(structure.product_targets || structure.targets).map((row) => ({ value: idOf(row, "targetId", "target_id"), label: textOf(row, "商品投放未返回", "targeting", "asin", "resolvedExpression"), row })),
    negativeKeywords: rowsOf(structure.negative_keywords).map((row) => ({ value: idOf(row, "keywordId", "negativeKeywordId", "targetId"), label: textOf(row, "否定关键词未返回", "keywordText", "keyword_text", "targeting"), row })),
    negativeTargets: rowsOf(structure.negative_product_targets || structure.negative_targets).map((row) => ({ value: idOf(row, "targetId", "negativeTargetId"), label: textOf(row, "否定商品未返回", "targeting", "asin", "resolvedExpression"), row })),
  };
}

function parseAdjustments(campaign) {
  try {
    const raw = valueOf(campaign, "adjustments");
    const rows = typeof raw === "string" ? JSON.parse(raw) : rowsOf(raw);
    const find = (predicate) => Number(rows.find((row) => row.predicate === predicate)?.percentage || 0);
    return {
      placement_top: find("placementTop"),
      placement_product: find("placementProductPage"),
      placement_rest: find("placementRestOfSearch"),
    };
  } catch {
    return { placement_top: 0, placement_product: 0, placement_rest: 0 };
  }
}

function initialValues(operationId, model, sources, selectedProduct) {
  const campaign = model?.campaign || {};
  const groups = sources.groups[0];
  const product = sources.products.find((item) => item.value === idOf(selectedProduct || {}, "adId", "ad_id")) || sources.products[0];
  const keyword = sources.keywords[0];
  const target = sources.targets[0];
  const negativeKeyword = sources.negativeKeywords[0];
  const negativeTarget = sources.negativeTargets[0];
  const stateRow = operationId === "ad_group_state" ? groups?.row : operationId === "ad_product_state" ? product?.row : operationId === "keyword_state" ? keyword?.row : operationId === "product_target_state" ? target?.row : campaign;
  return {
    state: String(valueOf(stateRow || {}, "state") || "enabled"),
    budget: Number(valueOf(campaign, "budget") || 0),
    strategy: String(valueOf(campaign, "strategy") || "legacyForSales"),
    ...parseAdjustments(campaign),
    group_id: groups?.value || "",
    ad_id: product?.value || "",
    target_id: operationId.startsWith("keyword_") ? keyword?.value || "" : operationId.startsWith("product_target") ? target?.value || "" : operationId === "negative_keyword_remove" ? negativeKeyword?.value || "" : negativeTarget?.value || "",
    default_bid: Number(valueOf(groups?.row || {}, "defaultBid", "default_bid") || 0.02),
    bid: Number(valueOf((operationId.startsWith("keyword_") ? keyword : target)?.row || {}, "bid", "current_bid") || 0.02),
    sku: String(valueOf(product?.row || {}, "sku", "msku") || ""),
    asin: String(valueOf(product?.row || {}, "asin") || ""),
    name: "",
    keyword_text: "",
    match_type: "exact",
  };
}

function buildValues(operationId, form) {
  const values = { ...form };
  if (operationId === "placement_adjustment") {
    values.adjustments = [
      { predicate: "placementTop", percentage: Number(form.placement_top) },
      { predicate: "placementProductPage", percentage: Number(form.placement_product) },
      { predicate: "placementRestOfSearch", percentage: Number(form.placement_rest) },
    ];
  }
  if (operationId.startsWith("keyword_")) values.targeting_type = "keyword";
  if (operationId.startsWith("product_target")) values.targeting_type = "product";
  return values;
}

function ControlField({ field, value, sources, onChange }) {
  const options = field.source ? sources[field.source] || [] : field.options;
  return (
    <label className="sp-control-field">
      <span>{field.label}</span>
      {options ? (
        <select value={value ?? ""} onChange={(event) => onChange(field.key, event.target.value)}>
          {!options.length && <option value="">暂无可选对象</option>}
          {options.map((option) => {
            const pair = Array.isArray(option) ? { value: option[0], label: option[1] } : option;
            return <option value={pair.value} key={pair.value}>{pair.label}</option>;
          })}
        </select>
      ) : (
        <div className="sp-control-input-wrap">
          <input type={field.type || "text"} value={value ?? ""} min={field.min} max={field.max} step={field.step} onChange={(event) => onChange(field.key, event.target.value)} />
          {field.suffix && <small>{field.suffix}</small>}
        </div>
      )}
    </label>
  );
}

export function SpControlDrawer({ open, shopId, model, selectedProduct, onClose, onExecuted }) {
  const campaignId = campaignIdOf(model?.campaign);
  const campaignName = campaignNameOf(model?.campaign);
  const sources = useMemo(() => controlSources(model), [model]);
  const [capabilities, setCapabilities] = useState(null);
  const [operationId, setOperationId] = useState("keyword_bid");
  const [form, setForm] = useState({});
  const [plan, setPlan] = useState(null);
  const [confirmation, setConfirmation] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadCapabilities(refresh = false) {
    if (!campaignId) return;
    setLoading(true);
    setError("");
    try {
      const payload = await fetchSpControlCapabilities({ shopId, campaignId, refresh });
      setCapabilities(payload);
      const current = payload.operations.find((item) => item.id === operationId);
      if (!current) setOperationId(payload.operations.find((item) => item.available)?.id || payload.operations[0]?.id || "");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open) return;
    loadCapabilities(false);
  }, [open, shopId, campaignId]);

  useEffect(() => {
    setForm(initialValues(operationId, model, sources, selectedProduct));
    setPlan(null);
    setConfirmation("");
    setResult(null);
    setError("");
  }, [operationId, model, selectedProduct, sources]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => { if (event.key === "Escape" && !loading) onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [loading, onClose, open]);

  if (!open) return null;
  const operations = capabilities?.operations || [];
  const selected = operations.find((item) => item.id === operationId);
  const groups = [...new Set(operations.map((item) => item.group))];
  const fields = FIELDS[operationId] || [];

  function updateField(key, value) {
    setForm((current) => {
      const next = { ...current, [key]: value };
      const sourceName = fields.find((field) => field.key === key)?.source;
      const selectedRow = (sources[sourceName] || []).find((item) => item.value === value)?.row || {};
      if (key === "group_id" && operationId === "ad_group_state") next.state = String(valueOf(selectedRow, "state") || "enabled");
      if (key === "group_id" && operationId === "ad_group_default_bid") next.default_bid = Number(valueOf(selectedRow, "defaultBid", "default_bid") || 0.02);
      if (key === "ad_id") next.state = String(valueOf(selectedRow, "state") || "enabled");
      if (key === "target_id" && operationId.endsWith("_bid")) next.bid = Number(valueOf(selectedRow, "bid", "current_bid") || 0.02);
      if (key === "target_id" && operationId.endsWith("_state")) next.state = String(valueOf(selectedRow, "state") || "enabled");
      return next;
    });
    setPlan(null);
    setResult(null);
  }

  async function preview() {
    setLoading(true);
    setError("");
    try {
      const payload = await previewSpControl({ shop_id: shopId, operation: operationId, campaign_id: campaignId, values: buildValues(operationId, form) }, capabilities.control_token);
      setPlan(payload);
      setConfirmation("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function execute() {
    setLoading(true);
    setError("");
    try {
      const payload = await executeSpControl({ shop_id: shopId, plan_id: plan.plan_id, confirmation }, capabilities.control_token);
      setResult(payload);
      setPlan(null);
      onExecuted?.(payload);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return createPortal(
    <div className="sp-control-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !loading) onClose(); }}>
      <aside className="sp-control-drawer" role="dialog" aria-modal="true" aria-label="SP广告调控">
        <header>
          <div><span>人工确认执行</span><h2><SlidersHorizontal size={23} weight="duotone" />SP 广告调控</h2><p>{campaignName} · {campaignId}</p></div>
          <button type="button" onClick={onClose} disabled={loading} aria-label="关闭调控面板"><X size={22} /></button>
        </header>
        <div className="sp-control-policy"><LockKey size={18} weight="fill" /><span>每次只修改一个对象；先生成冻结预览，再输入确认文本执行，并写入本地审计记录。</span></div>
        <div className="sp-control-capability-row">
          <span className={capabilities?.mcp_status === "available" ? "available" : "degraded"}>{capabilities?.mcp_status === "available" ? "MCP能力已同步" : "MCP能力未同步"}</span>
          <button type="button" onClick={() => loadCapabilities(true)} disabled={loading}><ArrowClockwise className={loading ? "spin" : ""} size={15} />重新检测接口</button>
        </div>
        {error && <div className="sp-control-error"><Warning size={18} weight="fill" />{error}</div>}
        {result ? (
          <section className="sp-control-result"><CheckCircle size={46} weight="duotone" /><h3>调控请求已成功提交</h3><p>{result.operation_label} · 计划 {result.plan_id}</p><small>赛狐基础状态通常需要约 2–3 分钟同步到列表，请稍后刷新确认。</small><button type="button" onClick={() => setResult(null)}>继续调控</button></section>
        ) : (
          <div className="sp-control-body">
            <nav className="sp-control-operation-list" aria-label="SP调控操作">
              {groups.map((group) => <section key={group}><h3>{group}</h3>{operations.filter((item) => item.group === group).map((item) => <button className={operationId === item.id ? "active" : ""} type="button" key={item.id} onClick={() => setOperationId(item.id)} disabled={!item.available}><span>{item.label}</span><small>{item.available ? item.availability === "live" ? "接口已验证" : "执行时复核" : "等待接口开放"}</small></button>)}</section>)}
            </nav>
            <section className="sp-control-editor">
              {!selected && <div className="sp-control-placeholder"><ArrowClockwise className="spin" size={28} />正在读取 SP 调控能力…</div>}
              {selected && <>
                <div className="sp-control-editor-title"><span>{selected.group}</span><h3>{selected.label}</h3><p>{selected.description}</p></div>
                <div className="sp-control-form">{fields.map((field) => <ControlField key={field.key} field={field} value={form[field.key]} sources={sources} onChange={updateField} />)}</div>
                {!plan ? (
                  <button className="sp-control-primary" type="button" onClick={preview} disabled={loading || !selected.available || fields.some((field) => !form[field.key] && form[field.key] !== 0)}>{loading ? "正在校验当前接口…" : "预览本次变更"}</button>
                ) : (
                  <div className="sp-control-confirm">
                    <div><span>冻结计划</span><b>{plan.plan_id}</b></div>
                    <dl><div><dt>操作</dt><dd>{plan.operation_label}</dd></div><div><dt>工具</dt><dd>{plan.tool}</dd></div><div><dt>有效期</dt><dd>{new Date(plan.expires_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</dd></div></dl>
                    <label><span>输入“{plan.confirmation}”</span><input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></label>
                    <div><button type="button" onClick={() => setPlan(null)} disabled={loading}>返回修改</button><button className="danger" type="button" onClick={execute} disabled={loading || confirmation !== plan.confirmation}>{loading ? "正在提交…" : "确认执行"}</button></div>
                  </div>
                )}
              </>}
            </section>
          </div>
        )}
      </aside>
    </div>,
    document.body,
  );
}
