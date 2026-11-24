<script setup lang="ts">
import { computed, ref } from 'vue';
import { Button, ConfigProvider, Drawer, Input, InputNumber, Modal, Select, Switch, Tag, Tooltip, message } from 'ant-design-vue';
import CountTo from '../../../../packages/effects/common-ui/src/components/count-to/count-to.vue';
type Row = { sku: string; name: string; store: string; status: string; ocean: boolean; sales: number; fba: number; domestic: number; transit: number; days: number; suggested: number; quantity: number; price: number };
const rows = ref<Row[]>(Array.from({length: 36}, (_, i) => {
  const sales = [18.6,12.4,9.8,14.6,6.8,2.1][i%6]!;
  const days = [0,8,22,28,18,60][i%6]!;
  const quantity = [720,480,360,600,240,0][i%6]!;
  return {sku: `TC-${1024+i*112}`, name: ['抽屉收纳盒','桌面置物架','厨房密封罐','衣柜收纳篮','浴室置物架','桌面收纳盒'][i%6]!, store: i%3 ? '美国一店':'美国二店', status: ['断货','低库存','待下单','待下单','待下单','清货'][i%6]!, ocean: i%3===1, sales, days, fba: Math.round(sales*days), domestic: 240+i*20, transit: i%4===0 ? 120:0, suggested: quantity, quantity, price: [12,26,18,16,24,9][i%6]! };
}));
const baseline = ref(Object.fromEntries(rows.value.map(r => [r.sku,r.quantity])));
const query = ref(''), status = ref('全部'), store = ref('全部店铺'), page = ref(1), busy = ref(false), selected = ref<string[]>([]), active = ref<Row>(), drawer = ref(false), plan = ref(false), params = ref(false), columnsOpen = ref(false), showDomestic = ref(true), collapsed = ref(false), compact = ref(false);
const targetDays = ref(45), leadDays = ref(15), safetyDays = ref(7), updated = ref('09:30:00');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const filters = ['全部','断货','低库存','待下单','清货','海运 SKU','推荐海运'];
const count = (s:string) => rows.value.filter(r => s==='全部' || (s==='海运 SKU' ? r.ocean : s==='推荐海运' ? !r.ocean && r.sales>12 : r.status===s)).length;
const filtered = computed(() => rows.value.filter(r => (status.value==='全部' || (status.value==='海运 SKU' ? r.ocean : status.value==='推荐海运' ? !r.ocean && r.sales>12 : r.status===status.value)) && (store.value==='全部店铺' || r.store===store.value) && `${r.sku} ${r.name}`.toLowerCase().includes(query.value.toLowerCase())));
const visible = computed(() => filtered.value.slice((page.value-1)*10,page.value*10));
const pages = computed(() => Math.max(1,Math.ceil(filtered.value.length/10)));
const dirty = computed(() => rows.value.filter(r=>r.quantity!==baseline.value[r.sku]));
const total = computed(()=> rows.value.reduce((s,r)=>s+r.quantity,0));
const chosen = computed(()=>rows.value.filter(r=>selected.value.includes(r.sku)));
const chosenTotal = computed(()=>chosen.value.reduce((s,r)=>s+r.quantity,0));
const amount = computed(()=>chosen.value.reduce((s,r)=>s+r.quantity*r.price,0));
function setStatus(s:string) { status.value=s;page.value=1; }
function toggle(r:Row) { selected.value=selected.value.includes(r.sku) ? selected.value.filter(s=>s!==r.sku): [...selected.value,r.sku]; }
function toggleAll(e:Event) { const checked=(e.target as HTMLInputElement).checked; selected.value=checked ? [...new Set([...selected.value,...visible.value.map(r=>r.sku)])] : selected.value.filter(s=>!visible.value.some(r=>r.sku===s)); }
function undo() { rows.value.forEach(r=>r.quantity=baseline.value[r.sku]);message.info('已撤销未同步修改'); }
function sync() { baseline.value=Object.fromEntries(rows.value.map(r=>[r.sku,r.quantity]));message.success('演示：订货量已同步至本次会话'); }
async function refresh() { if(dirty.value.length) {message.warning('请先同步或撤销订货量修改');return;} busy.value=true;await new Promise(r=>setTimeout(r,1000));updated.value=new Date().toLocaleTimeString('zh-CN',{hour12:false});busy.value=false;message.success('演示数据已刷新'); }
function inspect(r:Row) {active.value=r;drawer.value=true;}
function exportCsv(planOnly=false) { const data=planOnly?chosen.value:filtered.value;const csv='\uFEFFSKU,店铺,状态,海运,订货量\n'+data.map(r=>[r.sku,r.store,r.status,r.ocean?'是':'否',r.quantity].join(',')).join('\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=planOnly?'演示采购计划.csv':'补货视图.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
</script>

<template>
<ConfigProvider :theme="{token:{colorPrimary:'#3166e8',borderRadius:6,fontFamily:'Inter, Microsoft YaHei, sans-serif',fontSize:14},components:{Button:{controlHeight:34},Input:{controlHeight:34}}}">
<div class="shell" :class="{collapsed,compact}">
 <aside class="sidebar">
  <div class="brand"><span class="brandmark">T</span><span class="navtext">图创 AI<span class="brand-sub">运营工作台</span></span></div>
  <div class="nav-caption navtext">补货管理</div>
  <button class="nav active" @click="setStatus('全部')"><span class="nav-icon">▦</span><span class="navtext">智能补货中心</span><span class="navtext nav-end">⌄</span></button>
  <div class="nav-caption navtext">SKU 状态</div>
  <button v-for="s in filters" :key="s" class="filter" :class="{selected:status===s}" @click="setStatus(s)"><span class="filter-mark" :class="{'ocean-dot':s==='海运 SKU'}"></span><span class="navtext">{{s}}</span><span class="navtext count">{{count(s)}}</span></button>
  <div class="sidebar-note navtext"><span class="blue-key"></span>蓝色 SKU 为海运管理商品</div>
  <div class="sidebar-bottom"><div class="avatar">运</div><div class="navtext">运营人员<small>演示工作空间</small></div></div>
 </aside>
 <section class="workspace">
  <header class="header"><button class="icon-button" aria-label="收起导航" @click="collapsed=!collapsed">☰</button><span class="breadcrumb">运营管理 <span>/</span> 智能补货中心</span><div class="header-end"><span class="demo-pill">交互演示</span><Tooltip title="调整显示密度"><button class="icon-button" @click="compact=!compact" aria-label="调整显示密度">☷</button></Tooltip><span class="avatar small">运</span></div></header>
  <div class="tabbar"><span class="route-tab">智能补货中心 <span>·</span></span></div>
  <main>
   <div class="page-heading"><div><div class="eyebrow">INVENTORY WORKSPACE</div><h1>智能补货中心 <span>亚马逊</span></h1><p>从库存洞察，到精准补货。</p></div><div class="actions"><Button @click="params=true">运营参数</Button><Button :disabled="!dirty.length" @click="sync">同步订货量 <span v-if="dirty.length" class="mini-count">{{dirty.length}}</span></Button><Button :disabled="!chosen.length" @click="plan=true">生成采购计划</Button><Button type="primary" :loading="busy" @click="refresh">刷新数据</Button></div></div>
   <div class="metadata"><span class="live-dot"></span> 数据已载入 <span class="divider">/</span> 今日 {{updated}} <span class="divider">/</span> 销量截止 11-23 <span class="divider">/</span> 2 家店铺 <span class="metadata-end">演示数据 · 不连接生产系统</span></div>
   <section class="metrics">
    <div class="metric"><span>参与计算 SKU</span><div class="metric-value"><CountTo :end-val="rows.length" :duration="900" :disabled="reduceMotion"/><small>个</small></div><span class="metric-note">当前店铺在售商品</span><span class="metric-icon">▦</span></div>
    <div class="metric"><span>断货 / 低库存</span><div class="metric-value"><span class="danger">{{count('断货')}}</span><span class="slash">/</span><span class="warning">{{count('低库存')}}</span></div><span class="metric-note">优先关注库存风险</span><span class="metric-icon amber">!</span></div>
    <div class="metric"><span>建议补货量</span><div class="metric-value"><CountTo :end-val="rows.reduce((s,r)=>s+r.suggested,0)" :duration="1100" :disabled="reduceMotion"/><small>件</small></div><span class="metric-note">目标覆盖 {{targetDays}} 天</span><span class="metric-icon">▤</span></div>
    <div class="metric"><span>本次订货量</span><div class="metric-value"><CountTo :end-val="total" :duration="700" :disabled="reduceMotion"/><small>件</small></div><span class="metric-note">{{dirty.length ? `${dirty.length} 项修改待同步` : '所有修改已同步'}}</span><span class="metric-icon">✓</span></div>
   </section>
   <section class="data-panel">
    <div class="sheet-tabs"><button class="sheet-tab selected" @click="setStatus('全部')">智能补货</button><button class="sheet-tab" @click="setStatus('海运 SKU')">海运 SKU <span>{{count('海运 SKU')}}</span></button><span class="sheet-tabs-end">订货口径 {{targetDays}} 天</span></div>
    <div class="table-toolbar"><div class="table-title">补货明细 <span>{{filtered.length}} 个 SKU</span><Transition name="fade"><span v-if="dirty.length" class="pending">{{dirty.length}} 项待同步</span></Transition></div><div class="table-tools"><Input v-model:value="query" allow-clear placeholder="搜索 SKU / 产品名称" @change="page=1"><template #prefix><span class="search-icon">⌕</span></template></Input><Select v-model:value="store" :options="['全部店铺','美国一店','美国二店'].map(value=>({value}))" @change="page=1"/><Tooltip title="显示或隐藏国内库存列"><Button @click="columnsOpen=!columnsOpen">列设置</Button></Tooltip><Button @click="exportCsv(false)">导出</Button></div></div>
    <Transition name="fade"><div v-if="columnsOpen" class="column-settings">显示国内库存 <Switch v-model:checked="showDomestic" size="small"/><span>列设置仅影响当前视图</span></div></Transition>
    <div class="table-scroll" :class="{refreshing:busy}"><div v-if="busy" class="refresh-line"></div><table><thead><tr><th class="check-col"><input type="checkbox" aria-label="选择本页" :checked="visible.length>0 && visible.every(r=>selected.includes(r.sku))" @change="toggleAll"></th><th>商品 / SKU</th><th>店铺</th><th>状态</th><th class="num">日均销量</th><th class="num">FBA 库存</th><th v-if="showDomestic" class="num">国内库存</th><th class="num">在途</th><th class="num">可售天数</th><th class="num">建议订货</th><th class="num order-head">订货量</th><th class="num">订货后天数</th></tr></thead>
     <TransitionGroup tag="tbody" name="row"><tr v-for="r in visible" :key="r.sku" :class="{'checked-row':selected.includes(r.sku)}"><td><input type="checkbox" :aria-label="`选择 ${r.sku}`" :checked="selected.includes(r.sku)" @change="toggle(r)"></td><td><button class="sku-button" :class="{ocean:r.ocean}" @click="inspect(r)">{{r.sku}}</button><div class="product-name">{{r.name}}</div></td><td class="muted">{{r.store}}</td><td><Tag :bordered="false" :color="r.status==='断货'?'error':r.status==='低库存'?'warning':r.status==='清货'?'default':'success'">{{r.status}}</Tag></td><td class="num">{{r.sales.toFixed(1)}}</td><td class="num">{{r.fba.toLocaleString()}}</td><td v-if="showDomestic" class="num">{{r.domestic.toLocaleString()}}</td><td class="num" :class="{muted:!r.transit}">{{r.transit||'—'}}</td><td class="num" :class="{danger:r.days===0,warning:r.days>0&&r.days<15}">{{r.days}} <small>天</small></td><td class="num">{{r.suggested.toLocaleString()}}</td><td class="num quantity-cell"><InputNumber v-model:value="r.quantity" :min="0" :max="999999" :precision="0" :controls="false" :bordered="false" :aria-label="`${r.sku} 订货量`" @change="r.quantity=Math.max(0,Number(r.quantity)||0)" @keydown.esc="r.quantity=baseline[r.sku]" @press-enter="($event.target as HTMLInputElement).blur()"/><Tooltip v-if="r.quantity!==baseline[r.sku]" title="已修改，待同步；Esc 撤销"><span class="dirty-dot"></span></Tooltip></td><td class="num">{{Math.round((r.fba+r.transit+r.quantity)/r.sales)}} <small>天</small></td></tr></TransitionGroup>
    </table><div v-if="!visible.length" class="empty">没有匹配的商品<Button type="link" @click="query='';store='全部店铺';setStatus('全部')">重置筛选</Button></div></div>
    <footer class="table-footer"><span>显示 {{filtered.length?(page-1)*10+1:0}}–{{Math.min(page*10,filtered.length)}} 条，共 {{filtered.length}} 条</span><span class="edit-hint">点击 SKU 查看明细 · 直接编辑订货量</span><div class="pagination"><button :disabled="page===1" @click="page--" aria-label="上一页">‹</button><button v-for="p in pages" :key="p" :class="{current:page===p}" @click="page=p">{{p}}</button><button :disabled="page===pages" @click="page++" aria-label="下一页">›</button></div></footer>
   </section>
   <Transition name="selection"><div v-if="selected.length" class="selection-bar"><span>已选 <b>{{selected.length}}</b> 个 SKU</span><span class="divider">|</span><span>订货合计 <b>{{chosenTotal.toLocaleString()}}</b> 件</span><Button type="link" @click="selected=[]">取消选择</Button><div class="selection-end"><Button v-if="status==='推荐海运'" @click="chosen.forEach(r=>r.ocean=true);selected=[];message.success('演示：已加入海运管理')">加入海运</Button><Button type="primary" @click="plan=true">预览采购计划</Button></div></div></Transition>
   <div class="page-foot">基于 Vue Vben Admin · Vue 3 + Ant Design Vue <span>蓝色 SKU 表示海运商品</span></div>
  </main>
 </section>
</div>
<Drawer v-model:open="drawer" :width="480" title="SKU 明细" :destroy-on-close="true"><template v-if="active"><div class="detail-top"><div class="eyebrow">补货决策</div><h2 :class="{ocean:active.ocean}">{{active.sku}}</h2><p>{{active.name}} · {{active.store}}</p><Tag v-if="active.ocean" color="blue">海运管理</Tag><Tag>{{active.status}}</Tag></div><div class="detail-verdict"><span>建议订货</span><strong>{{active.suggested.toLocaleString()}} <small>件</small></strong><p>{{active.status==='清货'?'当前商品处于清货状态，建议不下单。':`按照 ${targetDays} 天目标覆盖，结合销量、可用库存与在途计算。`}}</p></div><div class="detail-grid"><div><span>日均销量</span><b>{{active.sales}}</b></div><div><span>FBA 库存</span><b>{{active.fba}}</b></div><div><span>在途数量</span><b>{{active.transit}}</b></div><div><span>可售天数</span><b>{{active.days}} 天</b></div></div><h3>本次订货</h3><div class="detail-edit"><InputNumber v-model:value="active.quantity" :min="0" :max="999999" :precision="0" :controls="false" @change="active.quantity=Math.max(0,Number(active.quantity)||0)"/><span>件</span></div><p class="muted">修改会同步反映在主表，确认后请点击“同步订货量”。</p><div class="demo-note">演示说明：使用本地模拟数据，刷新浏览器后重置。</div></template></Drawer>
<Modal v-model:open="plan" title="采购计划预览" :width="680" ok-text="导出演示计划" cancel-text="继续调整" @ok="exportCsv(true);plan=false"><div class="plan-summary"><div>已选 SKU<strong>{{chosen.length}}</strong></div><div>采购数量<strong>{{chosenTotal.toLocaleString()}} 件</strong></div><div>预估金额<strong>¥{{amount.toLocaleString()}}</strong></div></div><div class="plan-list"><div v-for="r in chosen" :key="r.sku"><span :class="{ocean:r.ocean}">{{r.sku}}</span><span>{{r.name}}</span><b>{{r.quantity}} 件</b></div></div><p class="demo-note">这是演示采购清单，导出 CSV 不会提交真实采购单。</p></Modal>
<Modal v-model:open="params" title="运营参数" ok-text="应用到演示" cancel-text="关闭" @ok="params=false;message.info('已更新展示口径；演示建议量为固定样例，未执行真实算法')"><div class="param-row"><label>目标覆盖天数</label><InputNumber v-model:value="targetDays" :min="1" :max="180" :precision="0"/></div><div class="param-row"><label>采购交期</label><InputNumber v-model:value="leadDays" :min="1" :max="120" :precision="0"/></div><div class="param-row"><label>安全库存天数</label><InputNumber v-model:value="safetyDays" :min="0" :max="60" :precision="0"/></div><p class="demo-note">仅演示参数交互，不运行生产补货算法。</p></Modal>
</ConfigProvider>
</template>
