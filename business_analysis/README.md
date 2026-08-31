# 经营分析

本地 ECharts 经营分析平台，支持 SQL Server 实时查询、60 秒自动刷新、参数化 SQL、公式追溯与 Excel 快照降级。

## 图创AI主站集成

主站入口为 `/ai/business-analysis`，仅通过 `ai_dept` 权限开放。前端生产资源由 `npm run build:flask` 生成到 `dist-flask/`，并由 Flask 在同一登录会话内提供；实时查询接口只监听 `127.0.0.1:4311`，首次打开页面时主站会调用 `scripts/start-api.ps1` 自动启动。数据库配置默认复用仓库根目录 `.env` 中的 `DB_*` / `SQLSERVER_*`，也可使用本目录 `.env.local` 的 `SALES_DB_*` 单独覆盖。

`app/data/workbook-data.json` 已包含 2026-07 的对毛与簇毛品类快照；实时查询尚未完成或数据库不可用时，品类页会直接展示该快照。

## 启动

```powershell
Copy-Item .env.example .env.local
# 在 .env.local 填写 SALES_DB_SERVER / DATABASE / USER / PASSWORD
npm install
npm run dev -- --port 4310
```

打开 <http://localhost:4310/>。网页端口为 `4310`，仅监听本机的数据库 API 端口为 `4311`。

数据库未配置或暂时不可用时，页面会明确显示“快照/缓存”，并继续使用 `app/data/workbook-data.json`。每个核心 KPI 的 `fx` 可查看公式、输入值、数据口径和计算时间。

请使用单独的只读 SQL Server 账号；不要复用 Excel VBA 中的旧明文凭据。
