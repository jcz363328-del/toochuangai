import assert from "node:assert/strict";
import test from "node:test";

import { backfillImageFacts } from "../src/imageFactBackfill.js";

const blankForm = {
  productType: "",
  brandName: "",
  styleAngle: "",
  lengths: "",
  curl: "",
  bandType: "",
  pieceCount: "",
  contents: "",
};

test("backfills recognized product facts into empty fields", () => {
  const facts = [
    { key: "brandName", value: "GODDVENUS" },
    { key: "productType", value: "Wispy Cluster Lashes" },
    { key: "lengths", value: "10/12/14mm" },
    { key: "curl", value: "D Curl" },
    { key: "bandType", value: "clear band" },
    { key: "pieceCount", value: "120 clusters" },
    { key: "styleAngle", value: "wispy" },
    { key: "contents", value: "lash tray" },
    { key: "contents", value: "applicator" },
  ];

  const { nextForm, filledFields } = backfillImageFacts(blankForm, facts);

  assert.equal(nextForm.brandName, "GODDVENUS");
  assert.equal(nextForm.productType, "Wispy Cluster Lashes");
  assert.equal(nextForm.lengths, "10/12/14mm");
  assert.equal(nextForm.curl, "D Curl");
  assert.equal(nextForm.bandType, "clear band");
  assert.equal(nextForm.pieceCount, "120 clusters");
  assert.equal(nextForm.styleAngle, "wispy");
  assert.equal(nextForm.contents, "lash tray, applicator");
  assert.deepEqual(filledFields.sort(), Object.keys(blankForm).sort());
});

test("preserves manually entered values and accepts Chinese fact labels", () => {
  const current = { ...blankForm, brandName: "Manual Brand", productType: "Manual Type" };
  const facts = [
    { key: "brandName", value: "Recognized Brand" },
    { label: "商品种类", value: "Recognized Type" },
    { label: "卷度", value: "D Curl" },
    { label: "包装内容", value: "lash tray" },
  ];

  const { nextForm, filledFields } = backfillImageFacts(current, facts);

  assert.equal(nextForm.brandName, "Manual Brand");
  assert.equal(nextForm.productType, "Manual Type");
  assert.equal(nextForm.curl, "D Curl");
  assert.equal(nextForm.contents, "lash tray");
  assert.deepEqual(filledFields.sort(), ["contents", "curl"]);
});

test("ignores unsupported facts instead of forcing them into product fields", () => {
  const { nextForm, filledFields } = backfillImageFacts(blankForm, [
    { key: "rowCount", value: "12 rows" },
    { key: "packageText", value: "D Curl" },
  ]);

  assert.deepEqual(nextForm, blankForm);
  assert.deepEqual(filledFields, []);
});

