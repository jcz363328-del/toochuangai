export const DEPARTMENT_MAPPINGS = Object.freeze([
  { source: "周雪", aliases: [], display: "运营一部" },
  { source: "王钰媛", aliases: [], display: "运营二部" },
  { source: "大张雯", aliases: [], display: "运营三部" },
  { source: "郭鑫", aliases: [], display: "运营六部" },
  { source: "侯瑞昕", aliases: ["侯瑞欣"], display: "运营七部" },
]);

const displayByName = new Map();
const sourceByName = new Map();

for (const mapping of DEPARTMENT_MAPPINGS) {
  for (const name of [mapping.source, ...mapping.aliases, mapping.display]) {
    displayByName.set(name, mapping.display);
    sourceByName.set(name, mapping.source);
  }
}

function normalizedText(value) {
  const text = value == null ? "" : String(value).trim();
  return text || null;
}

export function toDisplayDepartment(value) {
  const text = normalizedText(value);
  return text == null ? null : displayByName.get(text) || text;
}

export function toSourceDepartment(value) {
  const text = normalizedText(value);
  return text == null ? null : sourceByName.get(text) || text;
}
