import type { WorkbookData } from "../lib/dashboard";

const emptyRange = { start: "", end: "" };

export const emptyWorkbookData: WorkbookData = {
  meta: {
    sourceFile: "",
    extractedAt: new Date(0).toISOString(),
    sheetCount: 0,
    nonEmptySheetCount: 0,
    drawingCount: 0,
    dateRanges: {
      shipping: emptyRange,
      unshipped: emptyRange,
      newProductOrders: emptyRange,
      magnetDaily: emptyRange,
      categorySegments: emptyRange,
    },
    rowCounts: {},
    sourceTotals: {},
    reconciliation: {},
  },
  performance: {
    periods: [
      { key: "current", year: 2026, month: 8, label: "2026-08" },
      { key: "previous", year: 2026, month: 7, label: "2026-07" },
      { key: "yearAgo", year: 2025, month: 8, label: "2025-08" },
    ],
    departments: [],
    stores: [],
    periodRows: [],
  },
  slowMoving: [],
  shipping: [],
  newProductOrders: [],
  unshipped: [],
  magnetDaily: [],
  categorySegments: { categories: [] },
};
