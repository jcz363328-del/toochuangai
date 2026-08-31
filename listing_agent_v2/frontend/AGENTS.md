# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

## Selected Product Direction

- Source visual: `C:\Users\admin\.codex\generated_images\01a013cb-7dbb-7ff3-ae53-1bd44f0f5527\exec-22908972-b294-4424-af75-8a6a4940b465.png`.
- Build the Focused Split Studio direction: progressive inputs on the left and generated Listing delivery on the right.
- This is an independent V2 route. Never edit or replace the existing `/listing-agent/` frontend.
- Reuse the existing Listing generation API so V2 benefits from the same persistence and compliance behavior.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.
