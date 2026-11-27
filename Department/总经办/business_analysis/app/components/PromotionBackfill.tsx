"use client";

import { useRef, useState } from "react";

type RecordRow = { id: number; store: number; date: string; tier: string; status: string; canSend: boolean; message: string };
const today = () => new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai" }).format(new Date());

export default function PromotionBackfill() {
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState(() => `${today().slice(0, 4)}-01-01`);
  const [end, setEnd] = useState(today);
  const [store, setStore] = useState("");
  const [rows, setRows] = useState<RecordRow[]>([]);
  const [recipients, setRecipients] = useState<string[]>([]);
  const [selected, setSelected] = useState<RecordRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const sending = useRef(false);

  async function load() {
    setBusy(true); setNotice(""); setSelected(null);
    try {
      const query = new URLSearchParams({ start, end, store });
      const response = await fetch(`/api/ai/business-analysis/promotion-backfill?${query}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || "通知记录读取失败");
      setRows(payload.rows); setRecipients(payload.recipients);
      if (!payload.rows.length) setNotice("当前范围暂无晋级台账记录");
    } catch (error) {
      setRows([]);
      setNotice(error instanceof Error ? error.message : "通知记录读取失败");
    } finally { setBusy(false); }
  }

  async function send() {
    if (!selected || sending.current) return;
    sending.current = true; setBusy(true); setNotice("");
    try {
      const response = await fetch("/api/ai/business-analysis/promotion-backfill", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recordId: selected.id }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || "补发失败");
      setRows((current) => current.map((row) => row.id === selected.id ? { ...row, status: payload.status, canSend: payload.status !== "已发送" } : row));
      setSelected(null);
      setNotice(`本次发送成功 ${payload.sent} 人，未成功 ${payload.failed} 人。${payload.message || ""}`);
    } catch (error) {
      // Hide the action until an explicit refresh after an ambiguous response.
      setSelected(null); setRows([]);
      setNotice(error instanceof Error ? error.message : "发送结果暂不可用，请刷新记录核对状态");
    } finally { sending.current = false; setBusy(false); }
  }

  return <section className="promotion-backfill">
    <button type="button" disabled={busy} onClick={() => setOpen(!open)}>晋级通知补发</button>
    {open ? <div className="promotion-backfill-content">
      <div className="promotion-backfill-filters">
        <label>开始日期<input type="date" value={start} disabled={busy} onChange={(e) => { setStart(e.target.value); setSelected(null); }} /></label>
        <label>结束日期<input type="date" value={end} disabled={busy} onChange={(e) => { setEnd(e.target.value); setSelected(null); }} /></label>
        <label>店铺号<input type="number" min="1" placeholder="全部店铺" value={store} disabled={busy} onChange={(e) => { setStore(e.target.value); setSelected(null); }} /></label>
        <button type="button" disabled={busy || !start || !end} onClick={() => void load()}>{busy ? "处理中…" : "查询通知记录"}</button>
      </div>
      <p>按历史晋级台账补发，后续回落不影响历史成绩。已发送记录自动跳过，部分失败仅重试尚未成功的接收人。</p>
      {notice ? <p role="status">{notice}</p> : null}
      {rows.length ? <div className="table-scroll promotion-backfill-list"><table><thead><tr><th>店铺</th><th>晋级日期</th><th>晋级层级</th><th>通知状态</th><th>操作</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}>
        <td>{row.store}号店</td><td>{row.date}</td><td>{row.tier}</td><td>{row.status}</td>
        <td><button type="button" disabled={busy || !row.canSend} onClick={() => setSelected(row)}>{row.status === "已发送" ? "已发送" : "预览补发"}</button></td>
      </tr>)}</tbody></table></div> : null}
      {selected ? <div className="promotion-backfill-preview">
        <b>确认补发内容</b><pre>{selected.message}</pre>
        <p>通知接收人：{recipients.join("、")}。已成功接收者会跳过。</p>
        <button type="button" disabled={busy} onClick={() => void send()}>{busy ? "正在补发…" : "确认发送"}</button>
        <button type="button" disabled={busy} onClick={() => setSelected(null)}>取消</button>
      </div> : null}
    </div> : null}
  </section>;
}
