# Design QA

source visual truth: `D:/系统TMP/codex-clipboard-922b8af6-2323-46e0-8b1e-e4f38dea069c.png`
implementation screenshot: `demo/innovation-skill-demos/previews/blue-1503.png`
comparison input: `demo/innovation-skill-demos/previews/qa-comparison.png`
viewport: 1503 × 1046 CSS px, device scale factor 1
source and implementation pixels: both 1503 × 1046; no density normalization
state: blue reference theme, overview, 2026-11-01 through 2026-11-30, example data

## Findings

- [P2] Initial layout had a white preview/header stack and a single large dashboard surface. Fixed by using the supplied blue top bar, transparent pale-blue page surface, independent shortcut/metric/chart cards, and the screenshot's chart grid.
- [P2] The first reference pass used a narrow filter column, which wrapped the toolbar action. Fixed by changing the blue workspace grid to a 1:1.27 filter/metrics split.
- [P2] Mobile chart labels could widen the intrinsic grid. Fixed with `min-width: 0`, mobile chart tracks, and wrapped donut legend labels.
- [P3] The supplied sticker crop includes a small white image background, which matches the light reference surface closely but is not alpha-masked.

## Fidelity surfaces

- Fonts and typography: Microsoft YaHei UI / PingFang SC fallbacks, dark navy display text, 12–15px dashboard copy, tabular metric numbers, and readable Chinese line lengths. The rendered hierarchy matches the reference's large title, compact subtitle, section headings, labels, and chart annotations.
- Spacing and layout rhythm: 47px blue navigation, compact title row, four equal shortcut cards, filter/metric summary row, 2+1 chart row, three-card analysis row, and full-width monthly trend. The implementation keeps the source's generous 32px desktop gutter and collapses to a single-column mobile layout.
- Colors and visual tokens: blue navigation and primary actions, pale-blue page background, white cards, navy text, muted slate copy, green status dot, blue/purple/green chart series, and light dividers/shadows sampled or inferred from the source.
- Image quality and asset fidelity: the user-supplied innovation sticker is cropped from the provided reference into `assets/innovation-star.png`, rendered with explicit width and height, and used in the title area. The remaining marks are functional UI icon treatments from the existing demo.
- Copy and content: “创新奖励管理系统”, “创新数据看板”, the four entry labels, date range, metrics, department/ranking labels, chart titles, and sample values follow the reference intent.

## Focused comparison evidence

The side-by-side comparison focuses on the top bar/title/mascot, shortcut row, summary row, first chart row, three analysis cards, and trend chart because these are the high-salience regions that changed. The source and implementation use the same pixel dimensions and overview state.

## Interaction verification

`verify_demo.py` passed three themes at 1503/1440/390/2340px: no horizontal overflow, metric rendering, status filters, search empty state/reset, invalid date validation, simulated proposal submission, HTML escaping, detail dialog, points view, and innovation-star view. `node --check app.js` and `py_compile verify_demo.py` passed.

## Implementation checklist

- [x] Match blue top navigation and pale-blue canvas.
- [x] Match independent shortcut, metric, chart, and trend surfaces.
- [x] Use supplied innovation sticker asset with fixed dimensions.
- [x] Preserve working date filters, status filters, proposal search, detail dialog, submission, and export.
- [x] Verify desktop and mobile overflow and interaction states.

## Follow-up Polish

- P3: replace the cropped sticker with a source-provided transparent asset if one becomes available.
- P3: replace text-based shortcut marks with the production icon set when the existing application exposes those assets.

final result: passed
