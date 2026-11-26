# 每日订餐推送

AI部功能 → 每日订餐推送。每天北京时间 09:25（含周末）读取当天 Lunch 表已确认记录，排除教师。

整体堂食与整体盒饭发送到“图创星链（青岛）创新科技有限公司”；TK 堂食与 TK 盒饭发送到“图创——内容生产工厂”。整体包含 TK，TK 以原部门“内容生产工厂”为准。

页面提供今日预览、向周俊成发送测试、补发未成功的群卡片，以及最近发送记录。正式推送去除测试字样，保留默认宽度、白蓝部门底色、人数汇总和每人一格的名单图片。

`lunch_push.py` 使用现有 SQL Server 和飞书消息应用配置。Flask 主程序与 Docker Web 入口启动模块线程；需 `TC_BACKGROUND_JOBS=1` 和 `LUNCH_PUSH_ENABLED=1`（后者默认 1）。这是应用内调度，不使用 Codex 自动任务或系统计划任务。

服务需在 09:25 运行；09:25–10:00 内重启可补发，失败在此窗口内重试，每张卡片最多尝试 5 次。10:00 后不自动补发，可在页面手动补发。程序停机时无法执行。

发送结果保存在 `TUCHUANGAI_STORAGE_ROOT/lunch_push/delivery.sqlite3`；未配置存储根目录时位于项目 `outputs/lunch_push`。所有服务实例必须共享该目录，SQLite 写事务串行化发送；同日期、范围、形式、接收方的成功卡片不会重复发送。网络重试复用飞书幂等 UUID；飞书端幂等有效期有限，异常中断且回执未保存时跨有效期手动补发仍应人工核对。

名单图片位于同目录 `images/YYYY-MM-DD`。Windows 使用微软雅黑，Linux 使用 Noto Sans CJK；也可通过 `LUNCH_FONT` 和 `LUNCH_FONT_BOLD` 指定中文字体路径。

只读预览：`python lunch_push.py`。核验群配置：`python lunch_push.py --validate-groups`。发送测试：`python lunch_push.py --send --test`。补发正式群消息：`python lunch_push.py --send`。独立运行模块：`python lunch_push.py --serve`。

验证：`python -m unittest discover -s tests -p test_lunch_push.py`。
