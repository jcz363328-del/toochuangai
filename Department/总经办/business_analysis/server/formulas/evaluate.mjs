import { formulaRegistry, inputLabels, metricsFromWorkbook } from "./registry.mjs";

function round(value, precision) {
  const factor = 10 ** precision;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

export function evaluateFormulaMetrics(metrics, {
  stale = false,
  evaluatedAt = new Date().toISOString(),
  inputSources = {},
} = {}) {
  return formulaRegistry.map((formula) => {
    const missing = formula.dependencies.some((key) => metrics[key] == null || !Number.isFinite(metrics[key]));
    const zeroDenominator = formula.denominator && metrics[formula.denominator] === 0;
    let status = missing ? "missing-input" : zeroDenominator ? "divide-by-zero" : "ok";
    let value = null;
    if (status === "ok") {
      const computed = formula.compute(metrics);
      if (Number.isFinite(computed)) value = round(computed, formula.precision);
      else status = "missing-input";
    }
    if (stale && status === "ok") status = "stale";
    return {
      id: formula.id,
      label: formula.label,
      expression: formula.expression,
      value,
      unit: formula.unit,
      status,
      inputs: formula.dependencies.map((key) => ({
        key,
        label: inputLabels[key] || key,
        value: metrics[key] ?? null,
        source: inputSources[key] || "calculated",
      })),
      evaluatedAt,
    };
  });
}

export function buildFormulaTraces(data, effective, options = {}) {
  return evaluateFormulaMetrics(metricsFromWorkbook(data, effective), options);
}

export function publicFormulaCatalog() {
  return formulaRegistry.map((formula) => ({
    id: formula.id,
    label: formula.label,
    expression: formula.expression,
    unit: formula.unit,
    dependencies: formula.dependencies,
  }));
}
