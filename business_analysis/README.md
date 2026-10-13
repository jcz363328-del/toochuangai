# 经营分析

本地 ECharts 经营分析平台，支持 SQL Server 实时查询、60 秒自动刷新、参数化 SQL、公式追溯与 Excel 快照降级。

## 图创AI主站集成

主站入口为 `/ai/business-analysis`，通过 `business_analysis` 权限开放，并用 `business_analysis_all` 区分全量金额视角。前端生产资源由 `npm run build:flask` 生成到 `dist-flask/`，并由 Flask 在同一登录会话内提供；实时查询接口只监听 `127.0.0.1:4311`，首次打开页面时主站会调用 `scripts/start-api.ps1` 自动启动。数据库配置默认复用仓库根目录 `.env` 中的 `DB_*` / `SQLSERVER_*`，也可使用本目录 `.env.local` 的 `SALES_DB_*` 单独覆盖。

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

## 店铺层级

“店铺层级”页签从 `CengJi` 历史表的最近业务日读取 `CengJi1 + CengJi2` 完整等级（例如“金5”“钻3”），以 `CengJiID` 作为排序值，并根据最近一次等级变化计算当前等级连续天数。层级缓存按 `Asia/Shanghai` 自然日分桶，API 进程会在每天本地零点后自动重查；若查询为空或零点刷新失败，优先保留最后一次成功结果。数据库不可用时回退到 `app/data/store-tiers.json` 中由《每日数据模板-8.xlsm》提取的最近快照，并在页面标记为快照数据。

## 财年首页

默认首页固定展示 `2026-2027` 财年目标达成情况：

- 年度目标：`SUM(v_ZhiBiao.ZhiBiao)`，筛选 `CaiNian='2026-2027'`。
- 当前实绩：`SUM(v_MaoLiLv.XiaoShouE)`，仅纳入目标表中的店铺，按店铺编号和自然月与目标对齐。
- YTD 达成率：累计实绩 ÷ 截至最新实绩日的进度目标；历史月份目标全额计入，当前月目标按最新实绩日占当月自然日的比例折算。
- 月度完成率：所选月实绩 ÷ 整月指标，不按数据日对月目标进行均分或折算；部门和店铺月度排名使用同一完整月口径。
- 当前缺口：YTD 累计目标 − 累计实绩；负值表示超额完成。
- 周期整体目标：年度、季度和月度主卡均显示完整周期目标；时间进度与目标完成进度按同一 0–100% 刻度对比，当前月另行保留截至数据日的折算进度指标。
- 年度剩余：全财年目标 − 累计实绩。
- 首页部门和店铺排名统一按所选期间达成率降序；达成率相同时按累计实绩降序。

普通成员只显示本人范围，部门负责人只显示本部门；没有 `business_analysis_all` 的用户只展示达成率和排名，不返回金额字段。首页原始查询按自然月持久化到 `data/fiscal-overview-<财年>.json`：当月请求直接读取缓存，跨月先返回已有缓存并在后台更新一次，避免用户等待 SQL 汇总。

## 关键任务

“关键任务”页签按 5 个运营部门和 7 个关键专项展示任务矩阵，支持单条录入、批量粘贴、JSON 导入/导出、编辑与删除。任务直接保存到 `data/key-tasks.json`，也可通过 `SALES_KEY_TASKS_FILE` 指定其他 JSON 路径；“风险或阻塞”为选填项，数据结构不包含节点日期。
