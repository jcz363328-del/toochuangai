# 创新奖励前端 Demo

在本目录运行 `python -m http.server 8767 --bind 127.0.0.1`，打开 http://127.0.0.1:8767 。也可以直接打开 index.html，无构建步骤和外部运行依赖。

## 本次应用的 GitHub Skills

- Anthropic frontend-design：https://github.com/anthropics/skills/tree/main/skills/frontend-design
- Vercel web-design-guidelines：https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines
- 最新检查规则：https://github.com/vercel-labs/web-interface-guidelines/blob/main/command.md

通过官方 skill-installer 脚本将原 Skill 下载到本目录 skills/ 供查阅，本次按原文执行；未安装到全局技能目录。

## 设计计划与检查

使用 Microsoft YaHei UI / PingFang SC 适配中文；正文 14px，数据等宽数字，标题按层级变化。主界面左对齐，避免原页面在宽屏下固定居中导致大面积空白。

- 蓝白工作台：#2563db 主色、#172741 正文、#65748a 次级文字、#e4e9f0 分隔线、#f3f6fa 底色、#ffffff 表面。横向导航、紧凑入口、图表与榜单并排。
- 侧栏管理台：#3464d8 主色、#17263d 侧栏、#b7c7de 侧栏文字、#f1f3f7 底色、#ffffff 表面。侧栏导航，把四个大入口收进导航，节省垂直空间，突出提案表。
- 创新社区：#237454 主色、#173e31 正文、#657b70 次级文字、#f5f9f5 底色、#e9f4eb 浅绿、#bd8e35 荣誉强调。扩大参与文案与优秀实践入口，提供更柔和的阅读节奏。

复核后去掉三版通用的装饰统计、重复大卡片和无意义动效；保留原系统的总提案数、采纳数、有效率、积分与四项入口。每版更换布局和优先级，而不只是换色。最新蓝色方案按用户参考页重排：蓝色顶栏、浅蓝背景、原版 Bootstrap 图标、创新贴纸、四张入口卡、筛选与指标同排、3 列横向图表和月度趋势。

交互包括：主题切换、日期筛选、模拟提交、CSV 导出、积分和优秀案例视图。首页底部不再渲染“创新提案”明细表，提案数据只用于看板指标和图表演示；URL 保存主题与日期筛选，刷新重置内存数据。演示日期固定为 2026-11-06，与本次截图背景一致。

按 Vercel 规则检查：语义按钮/链接、表单标签、可见焦点、原生 dialog 焦点限制与 Escape 关闭、动态结果提示、减少动效、移动端布局、长文本转义、日期范围校验、CSV 公式前缀处理。生产首页同步清理了遗留的“最新创新项目”请求，避免在没有容器时加载提案明细；承接管理页的正式提案列表保留。

预览截图位于 previews/，其中 blue-1503.png 与用户参考图同尺寸。JavaScript 通过 node --check；静态资源使用版本参数，避免浏览器继续使用旧 CSS/JS 缓存。CSV 已做代码检查，未验证 Excel 打开效果。

