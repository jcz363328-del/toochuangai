# 智能补货中心-AI版

独立 Vue 3 / Ant Design Vue 前端，沿用 Vben Demo 的布局和交互。原运营版的模板与路由不替换。

- 入口：`/ai/replenishment-vben`，位于“AI部功能”。
- 权限：独立 `replenishment_vben` 权限与 AI 部身份检查；底层数据和写操作仍通过原补货接口校验店铺权限。
- 数据：读取运营快照中的“日常补货”和“近15天销量”，按原行号、SKU、店铺、运营身份保存数量，避免同 SKU 多店铺串行。
- 销量：每行 SVG 曲线从左到右展开，悬停显示日期与销量，可重播；尊重系统减少动画设置。缺少销量快照时批量请求原逐日销量接口，失败时显示缺失状态，不生成模拟生产数据。
- 海运：`mark-ocean` 对应 SKU 蓝色字体。
- 采购：沿用原 `purchase-plan` 接口导出下单模板，仅提交已选、可写且订货量大于10件的行。

## 开发与构建

```powershell
cd frontend/replenishment-vben
npm ci
npm run dev
npm run build
```

开发地址：`http://127.0.0.1:5679/static/replenishment-vben/`。开发环境需要同源 Flask API；只看交互时可显式添加 `?demo=1`，演示模式不会连接生产接口。

构建输出到 `static/replenishment-vben`，由 Flask 提供。数据库权限登记脚本：`migrations/20261124_add_replenishment_vben_permission.py`。更新运行环境时需同步构建产物与 Python、菜单模板，并重新加载主站进程。

CountTo 组件来自 [Vue Vben Admin](https://github.com/vbenjs/vue-vben-admin)，MIT 许可证见 `LICENSE.vben`；只将原工具类型判断替换为原生判断，并展开样式用于独立工程构建。
