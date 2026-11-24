# 智能补货中心交互 Demo

基于下载的官方 Vue Vben Admin 源码，在 `apps/web-antd` 中新增独立入口。使用 Vue 3、Ant Design Vue，并直接复用 Vben 的 CountTo 动态数字组件。保留上游 MIT LICENSE。

这是独立模拟数据页面，未替换 Flask 模板、未连接真实接口。模拟数据中的推荐海运条件和补货建议仅用于界面演示，不代表生产算法。

## 启动

在本目录执行：

```powershell
npx --yes pnpm@11.16.0 install --ignore-scripts
cd apps/web-antd
npx --yes pnpm@11.16.0 exec vite --config vite.demo.config.ts
```

打开 http://127.0.0.1:5678/replenishment-demo.html 。

## 构建

在 `apps/web-antd` 执行 `npx --yes pnpm@11.16.0 exec vite build --config vite.demo.config.ts`，输出到 `dist-demo`。

## 可以体验

- 搜索、店铺及状态筛选、分页、海运蓝色 SKU。
- 订货量直接编辑、Esc 撤销单项修改、同步至当前会话。
- 勾选商品后预览并导出 CSV 采购清单。
- 点击 SKU 打开抽屉；统计数字滚动、筛选行切换、刷新加载、按钮反馈。
- 导航折叠、显示密度和列设置。
- 尊重系统减少动画偏好。

所有修改仅存在当前页面内存中，重新加载后重置。运营参数只演示编辑和显示，不执行生产补货算法。
