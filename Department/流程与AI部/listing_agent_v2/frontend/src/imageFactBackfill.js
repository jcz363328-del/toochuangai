const FACT_FIELD_ALIASES = new Map(
  [
    ["brandname", "brandName"],
    ["brand", "brandName"],
    ["品牌", "brandName"],
    ["品牌名称", "brandName"],
    ["producttype", "productType"],
    ["category", "productType"],
    ["商品种类", "productType"],
    ["产品类型", "productType"],
    ["lengths", "lengths"],
    ["length", "lengths"],
    ["规格/长度", "lengths"],
    ["长度", "lengths"],
    ["curl", "curl"],
    ["卷度", "curl"],
    ["bandtype", "bandType"],
    ["band", "bandType"],
    ["带型", "bandType"],
    ["piececount", "pieceCount"],
    ["quantity", "pieceCount"],
    ["数量", "pieceCount"],
    ["根数", "pieceCount"],
    ["styleangle", "styleAngle"],
    ["style", "styleAngle"],
    ["风格/主要场景", "styleAngle"],
    ["风格", "styleAngle"],
    ["contents", "contents"],
    ["packagecontents", "contents"],
    ["包装内容", "contents"],
    ["内容物", "contents"],
  ].map(([alias, field]) => [normalizeAlias(alias), field]),
);

function normalizeAlias(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s_\-]+/g, "")
    .replace(/[：:]/g, "");
}

function cleanValue(value) {
  if (Array.isArray(value)) return value.map(cleanValue).filter(Boolean).join(", ");
  return String(value || "").trim();
}

function resolveField(fact) {
  return FACT_FIELD_ALIASES.get(normalizeAlias(fact?.key))
    || FACT_FIELD_ALIASES.get(normalizeAlias(fact?.label))
    || "";
}

export function backfillImageFacts(currentForm, facts) {
  const nextForm = { ...currentForm };
  const valuesByField = new Map();

  for (const fact of Array.isArray(facts) ? facts : []) {
    const field = resolveField(fact);
    const value = cleanValue(fact?.value);
    if (!field || !value) continue;
    const values = valuesByField.get(field) || [];
    if (!values.some((item) => item.toLowerCase() === value.toLowerCase())) values.push(value);
    valuesByField.set(field, values);
  }

  const filledFields = [];
  for (const [field, values] of valuesByField) {
    if (cleanValue(nextForm[field])) continue;
    nextForm[field] = field === "contents" ? values.join(", ") : values[0];
    filledFields.push(field);
  }

  return { nextForm, filledFields };
}

