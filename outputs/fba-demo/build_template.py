from pathlib import Path
p=Path('outputs/fba-demo/index.html');s=p.read_text(encoding='utf-8-sig');s=s[:s.index('<script>')]
s=s.replace('FBA货件追踪 · 优化Demo','FBA货件追踪 / IEN - 图创AI')
s=s.replace('<span class="demo right">交互 Demo · 示例数据</span><span class="crumb">运营团队</span>','<a class="btn right" href="{{ back_url }}" style="text-decoration:none">返回{{ source_name }}</a><span class="crumb">{{ user_name }}</span>')
s=s.replace('<button class="btn" id="reset">↻ 重置筛选</button>','<button class="btn" id="reset">↻ 重置筛选</button>')
s=s.replace('当前筛选范围内的示例记录','当前筛选范围内的全部货件')
s=s.replace('追踪码缺失、格式或数量待核对','追踪码缺失、格式或数量待核对')
for name in ['total','filled','issues','checked']:
 import re
 s=re.sub(r'(<strong id="'+name+r'">)\d+',r'\g<1>—',s)
s=s.replace('<span>8</span>','<span id="tabAll">—</span>').replace('<span>3</span>','<span id="tabIssue">—</span>').replace('<span>5</span>','<span id="tabFilled">—</span>').replace('<span>2</span>','<span id="tabUnchecked">—</span>')
start=s.index('<select id="shop">');end=s.index('</div><div class="note">',start)
s=s[:start]+'''<select id="shop" aria-label="店铺"><option value="">全部店铺</option></select><select id="shipping" aria-label="运输方式"><option value="">全部运输方式</option></select><select id="status" aria-label="填写状态"><option value="">全部填写状态</option><option value="Y">已填写</option><option value="unmarked">未标记</option></select><select id="sort" aria-label="排序"><option value="import_desc">最新导入优先</option><option value="import_asc">最早导入优先</option><option value="check_desc">最近检查优先</option></select>'''+s[end:]
s=s.replace('共 8 条货件 · 已按最新导入排序','正在读取货件数据…').replace('追踪码支持一键复制　 ·　 点击详情查看完整信息','<span id="updatedAt">数据每 30 秒更新缓存</span>　·　点击详情查看完整信息')
start=s.index('<div class="pages">');end=s.index('</div></div></section>',start)
s=s[:start]+'''<div class="pages"><select id="pageSize" aria-label="每页条数"><option value="20">每页 20 条</option><option value="50">每页 50 条</option><option value="100">每页 100 条</option></select><button id="prev" disabled aria-label="上一页">‹</button><span id="pageInfo">1 / 1</span><button id="next" disabled aria-label="下一页">›</button>'''+s[end:]
s=s.replace('所有货件与单号均为示例；筛选、详情、复制及 CSV 导出可交互体验。','填写状态、记录个数和检查日期均来自原表；本页仅查询，不修改货件数据。')
s=s.replace('<div class="overlay" id="overlay"><aside class="drawer" id="drawer"></aside></div>','<div class="overlay" id="overlay" aria-hidden="true"><aside class="drawer" id="drawer" role="dialog" aria-modal="true" aria-label="货件详情"></aside></div>')
s=s.replace('<tbody id="rows"></tbody>','<tbody id="rows"><tr><td colspan="10" class="empty">正在读取货件数据…</td></tr></tbody>')
s+='''<script src="{{ url_for('static', filename='js/fba_shipping.js', v='20261119') }}" defer></script></html>'''
Path('templates/operation_fba_shipping_methods.html').write_text(s,encoding='utf-8')
