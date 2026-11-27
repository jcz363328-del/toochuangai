# SP 广告 MCP 调控 Demo

这是一个单店、单对象、默认 Dry-run 的最小调控闭环：

1. 读取广告监控发布的真实 `live` 数据。
2. 重新检查 ACoS、订单、点击、花费和数据完整度。
3. 单次只选择一个 USD 店铺的 SP 关键词或商品投放。
4. 将原建议收敛为较小步长：降竞价 5%、加竞价 3%。
5. 可通过 MCP 只读复查当前值；默认只保存执行计划，不发送写请求。

计划还会读取 `ads-realtime.json` 的活动级门禁。实时层缺失、过期、未覆盖、`BLOCK` 或 `REVIEW` 时，即使成熟层有建议也不能进入真实执行确认；只有同一成熟层哈希下的 `NO_OBJECTION + fresh` 才能通过。`NO_OBJECTION` 只表示实时层未发现冲突，不代表系统批准调价。

## 直接运行

可以直接双击 `运行SP广告调控DryRun.bat`，它只做 MCP 读取核验和 Dry-run，不会写广告。

```powershell
& '.\.venv\Scripts\python.exe' '.\sellfox_sp_adjust_demo.py'
```

默认从 `ads-monitor-web/public/data/ads-monitor.json` 选择一条高 ACoS 降竞价建议，输出到：

```text
outputs/sp_mcp_demo/decision-plan.json
```

指定店铺或动作：

```powershell
& '.\.venv\Scripts\python.exe' '.\sellfox_sp_adjust_demo.py' `
  --shop-id 475202 --action DECREASE_BID
```

通过 MCP 只读核对当前值，不修改广告：

```powershell
& '.\.venv\Scripts\python.exe' '.\sellfox_sp_adjust_demo.py' --verify-mcp
```

## 安全边界

- 只接受系统默认发布路径下、`mode=live` 且 36 小时内的数据。
- 只接受 `data_status=complete` 的最终建议。
- 拒绝 `text:` 合成投放 ID。
- 每次只允许一个对象，变化不超过 10%。
- 当前真实执行只允许 USD 和 `edit_sp_targeting`，不支持预算、暂停、归档、否定词、新建投放或批量操作。
- 写入前重新读取并比较当前值，写入后再次读回验证。
- 源文件摘要、规则证据、MCP inputSchema 和预检签名必须一致。
- 跨进程锁、写前原子占位、48小时冷却共同阻止本机重复提交。
- 凭据只从环境变量或现有 DPAPI 加密配置读取，不进入计划文件。

程序包含真实 MCP 写入通道，但不会因普通运行而触发。真实执行必须同时提供冻结计划、精确 `plan_id`，并在同一进程环境中显式设置写入总开关。不要在测试阶段设置该总开关。

## 测试

```powershell
& '.\.venv\Scripts\python.exe' -m unittest -v test_sellfox_sp_adjust_demo.py
```
