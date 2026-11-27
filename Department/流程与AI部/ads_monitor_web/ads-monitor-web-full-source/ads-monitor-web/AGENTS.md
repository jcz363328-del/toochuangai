# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

## Selected design direction

- Source visual: `C:\Users\Administrator\.codex\generated_images\019fa115-c007-7622-9a6e-690c19488e33\exec-071cf47f-d889-4cd9-8c17-cb868bd13c11.png`.
- Direction: iOS-inspired desktop master-detail workspace with a recommendation queue on the left and a detailed review inspector on the right.
- Diagnostic evidence remains read-only. Real SP changes are allowed only from the in-page control drawer after a frozen preview, exact typed confirmation, single-object scope, capability recheck, and local audit record.
- Keep the full SP control catalog visible in the drawer. Disable unsupported Sellfox MCP operations honestly; never simulate success or invent a write endpoint.
- Keep overview and structure as the only detail tabs. Open SP controls from the campaign header in a right-side drawer instead of adding another tab.
- In mature search-term tables, show impressions, CTR, total cost, CPC, and ROAS; use green rows for CPC-adjustment candidates and red rows for negative-keyword candidates.
- Optimize the single-shop diagnostic for first-screen readiness: load the overview first, then preload structure and SKU detail in the background.
- Keep only overview, structure, and SKU detail tabs; remove the data-source tab from the UI while retaining source metadata for backend auditing.
- Do not keep a separate top-level SKU-new page. Show the selected SKU's new/established status in the diagnostic overview.
- Use wide screens instead of leaving large outer margins. Keep selected-SKU hourly context in a compact insight rail, without a machine-action recommendation card.
- Do not show machine recommendation banners or recommendation codes in the overview. Present neutral evidence and comparisons so operators make the final adjustment decision.
- Search-term tables use real 10-row pagination and fetch later pages only when requested.
- For automatic campaigns, never describe a green search-term row as a direct CPC adjustment. Treat it as a high-quality term to move into new manual exact and broad targeting.
- Campaign cards show status, default bid, target count, products, and complete mature performance. They switch between D-2 rolling 7/14/30-day windows and never invent missing values.
- Campaign performance grades render for every card directly from the selected mature window without requiring detail selection. Keep lifecycle separate from the display-only grades: excellent, good, average, poor, insufficient sample, and unavailable.
- Every campaign card must open immediately from its own published snapshot. Live Sellfox detail enriches the view when available, but a transient API failure must never blank the selected campaign or substitute another campaign's data.
- On desktop, the campaign information rail is wider and flush with the left edge; Top conversion and Top waste stay side by side, with a stacked fallback on narrower screens.
- Campaign-card metric labels and values stay on one line to reduce card height.
- Do not show the campaign status filter tabs for All, Enabled, or Attention; keep search and sorting as the list controls.
- Put the 14-day mature daily trend and the selected SKU's inventory, sales, margin, break-even ACoS, profit, and SP cost at the top of the overview. Keep operator-facing copy concise and hide technical grain or refresh-source badges from this section.
- Do not show a separate focus-ad-product selector between the campaign header and detail tabs. Keep the active SKU implicit in the campaign header and insight rail.
- Background snapshot refresh must not insert or remove layout rows or poll the full detail view every few seconds. Keep refresh state in a fixed-width header status so tables and charts stay visually stable.
- The overview's ad-placement table must use the standard SP ad-placement report (`adSpaceReport`), never the Amazon Business placement report.
- Show the full standard placement view: placement name, campaign bidding strategy, bid adjustment, impressions, clicks, CTR, spend, CPC, purchases, sales, ACoS, and a total row.
- Add a neutral budget-and-traffic panel with daily budget, last-7-day budget exhaustion count, today's spend progress, mature ACoS, and break-even ACoS. Budget restriction is traffic evidence, never direct proof to increase budget.
- Above the mature search-term tables, summarize converting-term orders, sales and order share; zero-order spend and spend share; the highest-click zero-order term; and counts for effective samples, attention, and insufficient samples. Use clicks >= 10 as the effective-sample threshold and show missing data as dashes instead of zero.
- Extend the placement table with spend share, order share, CVR, ACoS percentage-point delta from the campaign total, current bid adjustment, and sample confidence.
- Pace the unfinished US business day in the Amazon Ads account timezone, not by averaging US state clocks. Compare spend through the latest complete hour with yesterday at the same cutoff and the prior-7-day same-hour median; keep yesterday's full day and D-2 mature efficiency in a separate reference row, and avoid directional language before four complete hours.
- When the current business day's hourly endpoints have not backfilled yet, show the previous day's available hourly rows with the actual report date and an explicit historical-fallback badge. Never feed those fallback rows into today's budget, pacing, or control decisions.
- Use `MAGIC AD` as the product brand. Do not show the Sellfox fox avatar or call the product `赛狐广告监控`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.
