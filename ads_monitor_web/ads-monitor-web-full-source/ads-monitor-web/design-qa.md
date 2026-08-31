# Design QA — 广告活动指标排序与购买率

## Evidence

- Source visual truth: `qa/campaign-sort-source-reference.png` (`497 × 283` px), the user-provided selected campaign card.
- Browser-rendered implementation: `qa/campaign-sort-reference-state-final-1440x1024.png` (`1425 × 1013` px) at a `1440 × 1024` CSS viewport and device pixel ratio `1`.
- Focused implementation: `qa/campaign-sort-card-final.png` (`346 × 275` px), cropped from the browser-rendered selected card.
- Combined comparison: `qa/campaign-sort-comparison.png` (`1014 × 395` px), with the implementation crop width-normalized from `346` to `497` px beside the `497` px source. Height was not forced because the requested purchase-rate row intentionally makes the implementation taller.
- Responsive evidence: `qa/campaign-sort-mobile-final-390x844.png` (`375 × 812` px) at a `390 × 844` CSS viewport and device pixel ratio `1`; the image excludes the browser scrollbar area.
- State: 单店诊断 → 近14天 → 综合排序 for the source-matched card; 购买率 descending and ascending were also exercised with live catalog data.

## Comparison history

- Pass 1 finding (P2): a four-column performance grid kept the card short but truncated currency values in the `390` px desktop rail.
- Fix: restored the source card's three-column desktop rhythm, reduced horizontal metric padding, and added 购买率 as a centered full-width final row. Mobile switches to two columns so all ten performance metrics remain readable.
- Post-fix evidence: `qa/campaign-sort-comparison.png` shows the original card anatomy, border rhythm, typography, colors, complete currency values, and the added purchase-rate row. `qa/campaign-sort-mobile-final-390x844.png` shows no horizontal overflow and complete metric values.

## Required fidelity surfaces

- Fonts and typography: the existing Inter stack, label/value hierarchy, weights, line heights, truncation rules, and tabular numeric treatment are preserved. Desktop currency values no longer truncate.
- Spacing and layout rhythm: card padding, gaps, radii, borders, status header, config row, and SKU row match the source. The extra purchase-rate row is the only intentional height increase.
- Colors and visual tokens: the selected blue border/background, neutral metric cells, muted labels, dark values, and green running status use the existing dashboard tokens.
- Image and asset fidelity: the card has no custom raster imagery. The existing Phosphor package and sort icons are retained; no placeholder, emoji, CSS drawing, or handcrafted SVG was introduced.
- Copy and content: all source metrics remain unchanged, 购买率 is labeled in operator language and displays `购买量 ÷ 点击量`, and missing denominators remain `—` rather than a fabricated zero.

## Interaction and runtime checks

- The sort menu exposes 综合排序 plus all 13 numeric metrics: 默认竞价、总投放数、商品、展示量、点击量、点击率、总成本、CPC、购买量、购买率、销售额、ACoS、ROAS.
- Purchase-rate descending produced `35.0%, 29.2%, 29.0%, 25.4%...`; ascending produced the lowest valid rates first. Missing values remain last in both directions.
- Switching 7/14/30-day windows reuses the selected window's values for display and sorting.
- Browser console warnings/errors: `0`.
- Frontend tests: `29/29` passed.
- Backend tests: `26/26` passed.
- Production build: passed.

## Findings

- No actionable P0/P1/P2 visual, responsive, data, or interaction mismatch remains.
- P3 only: at the narrow mobile breakpoint, the default-bid config value may ellipsize because the three-column configuration row is intentionally preserved; the requested performance metrics remain fully readable.

## Implementation checklist

- [x] Add purchase rate to every campaign card.
- [x] Support ascending and descending sorting for every displayed numeric metric.
- [x] Keep missing values last and preserve the existing comprehensive default order.
- [x] Verify desktop and mobile layouts, primary interactions, console, tests, and production build.

final result: passed
