# 财年排行信息横排 Design QA

- source visual truth paths:
  - `D:\系统TMP\codex-clipboard-73ee18ee-e10b-4449-997d-534287696fc4.png`
  - `D:\系统TMP\codex-clipboard-fb216c68-1bb8-4677-b674-15ac7fa87cf3.png`
- source pixels: 1520 × 389 and 1460 × 748
- implementation screenshot path: `E:\Python项目\toochuangai\business_analysis\fiscal-ranking-layout-after.png`
- implementation pixels: 1280 × 720
- viewport: 1280 × 720 CSS px, device scale factor 1
- density normalization: all captures are 1× desktop captures; focused comparison images normalize each source and implementation crop to the same 760 px display width without changing aspect ratio.
- state: light theme, 财年首页, 全部部门, 年度, live cached data through 2026-09-03.

## Findings

- No actionable P0/P1/P2 differences remain for the requested change.
- Department name and store count now share one baseline and use 12 px / 10 px type instead of the original 10 px / 8 px stacked treatment.
- Person name, department, and real store labels now share one baseline. Multiple stores render in numeric order, for example `2号店、26号店`.
- At 1280 px the page, department table, and person table have no horizontal overflow or truncated requested labels.

## Required fidelity surfaces

- Fonts and typography: existing system font stack retained; primary labels are 12 px and secondary department/store labels are 10 px with stronger weight for legibility.
- Spacing and layout rhythm: inline flex layout uses a 9–10 px gap and baseline alignment; existing row heights and table rhythm are preserved.
- Colors and visual tokens: existing ink, faint, accent, status, surface, and border tokens are unchanged; store labels use the existing accent token.
- Image quality and assets: these tables contain no raster imagery or custom visual assets; chart rendering remains unchanged and sharp.
- Copy and content: department rows retain `N 家店`; person header now states `负责人 / 所属部门 / 店铺`, and each row shows its actual store number(s).

## Full-view comparison evidence

- Browser-rendered implementation: `E:\Python项目\toochuangai\business_analysis\fiscal-ranking-layout-after.png`.
- The department and person panels retain the original widths, hierarchy, progress bars, values, and status colors while the requested identity metadata is denser and more readable.

## Focused comparison evidence

- Department before/after: `E:\Python项目\toochuangai\.codex-audit\fiscal-department-before-after.png`.
- Person before/after: `E:\Python项目\toochuangai\.codex-audit\fiscal-people-before-after.png`.
- Focused inspection confirms the labels are horizontal, larger, and aligned without colliding with adjacent numeric columns.

## Comparison history

1. Initial source finding (P2): department/store count and person/department labels were stacked at 10 px / 8 px; person rows omitted store identity.
2. Fix: converted both metadata groups to baseline-aligned flex layouts, increased typography to 12 px / 10 px, widened the person identity column, and added backend `storeNames` data plus numeric sorting.
3. Post-fix evidence: browser screenshot and focused comparison images show the requested inline layouts; computed layout reports `display: flex`, 12 px primary labels, 10 px secondary labels, and no desktop overflow.

## Browser verification

- Live fiscal overview API loaded successfully with five department rows and 36 person rows.
- Verified single-store and multi-store examples (`52号店`, `2号店、26号店`).
- Checked page, department-table, and person-table overflow at 1280 × 720.
- Browser console warnings/errors: 0.

## Implementation checklist

- [x] Department and store count inline and larger.
- [x] Person, department, and store inline and larger.
- [x] Real store identifiers included for every person.
- [x] Multiple stores sorted and displayed without duplication.
- [x] Backend tests, Flask frontend build, browser render, overflow, and console checks passed.

final result: passed
