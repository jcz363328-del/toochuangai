
// 加载统计数据
function loadStatistics() {
    axios.get('/innovation/api/get_statistics')
        .then(response => {
            if (response.data.success) {
                const data = response.data.data;
                // 检查元素是否存在再设置内容
                const totalCountEl = document.getElementById('total-count');
                const pendingCountEl = document.getElementById('pending-count');
                const processingCountEl = document.getElementById('processing-count');
                const completedCountEl = document.getElementById('completed-count');

                if (totalCountEl) totalCountEl.textContent = data.total_count;
                if (pendingCountEl) pendingCountEl.textContent = data.pending_count;
                if (processingCountEl) processingCountEl.textContent = data.processing_count;
                if (completedCountEl) completedCountEl.textContent = data.completed_count;
            }
        })
        .catch(error => {
            console.error('加载统计数据失败:', error);
        });
}

// 积分排行榜相关函数
function loadPointsRanking(type = 'current') {
    console.log(`加载积分排行榜: ${type}`);

    // 显示加载状态
    const loadingEl = document.getElementById('ranking-loading');
    const contentEl = document.getElementById('ranking-content');
    const emptyEl = document.getElementById('ranking-empty');

    if (loadingEl) loadingEl.style.display = 'block';
    if (contentEl) contentEl.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'none';

    axios.get(`/innovation/api/get_points_ranking?type=${type}&limit=10`)
        .then(response => {
            if (response.data.success) {
                const rankings = response.data.data.rankings;
                displayRankings(rankings, type);
            } else {
                console.error('获取排行榜失败:', response.data.message);
                showEmptyRanking();
            }
        })
        .catch(error => {
            console.error('获取排行榜失败:', error);
            showEmptyRanking();
        })
        .finally(() => {
            const loadingEl = document.getElementById('ranking-loading');
            if (loadingEl) loadingEl.style.display = 'none';
        });
}

function displayRankings(rankings, type) {
    const container = document.getElementById('ranking-list');

    if (!container) {
        console.warn('ranking-list 元素不存在');
        return;
    }

    if (rankings.length === 0) {
        showEmptyRanking();
        return;
    }

let html = '';
rankings.forEach((item, index) => {
    const medalIcon = index === 0 ? '🥇' :
                      index === 1 ? '🥈' :
                      index === 2 ? '🥉' :
                      index === 3 ? '🔥' :
                      index === 4 ? '🔥' :
                      index === 5 ? '🔥' :
                      index === 6 ? '🔥' :
                      index === 7 ? '🔥' :
                      index === 8 ? '🔥' :
                      index === 9 ? '🔥' :
                      index === 10 ? '🔥' :
                      index === 11? '🔥' :
                      index === 12? '🔥' :
                      index === 13? '🔥' :
                      index ===14 ? '🔥' :
                          `${index + 1}`;
    html += `
        <div class="col-md-6 col-lg-4 mb-3">
            <div class="card h-100 ${rankClass}">
                <div class="card-body">
                    <div class="d-flex align-items-center">
                        <div class="rank-badge me-3">
                            <span class="rank-number">${medalIcon}</span>
                        </div>
                        <div class="flex-grow-1">
                            <h6 class="card-title mb-1">${item.user_name}</h6>
                            <p class="card-text mb-1">
                                <strong class="text-primary">${item.points}</strong> 积分
                            </p>
                            <small class="text-muted">
                                当前: ${item.current_points} |
                                年度: ${item.annual_points} |
                                总计: ${item.total_points}
                            </small>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
});


    container.innerHTML = html;
    const contentEl = document.getElementById('ranking-content');
    if (contentEl) contentEl.style.display = 'block';
}

function showEmptyRanking() {
    const contentEl = document.getElementById('ranking-content');
    const emptyEl = document.getElementById('ranking-empty');
    if (contentEl) contentEl.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'block';
}
// 数字看板相关函数
const dashboardCharts = new Map();
const dashboardChartIds = [
    'top-department',
    'top-person',
    'top-proposal-counts',
    'top-highest-scores',
    'category-distribution',
    'monthly-trend'
];
const dashboardPalette = ['#4465d8', '#17a078', '#e99735', '#7657c8', '#da6175', '#3796b7', '#8ba84b', '#9b7049'];
let dashboardRequestId = 0;
let dashboardResizeFrame = null;
const dashboardResizeObserver = window.ResizeObserver
    ? new ResizeObserver(scheduleDashboardResize)
    : null;

function scheduleDashboardResize() {
    if (dashboardResizeFrame !== null) return;
    dashboardResizeFrame = requestAnimationFrame(() => {
        dashboardResizeFrame = null;
        dashboardCharts.forEach(chart => chart.resize());
    });
}

function setDashboardStatus(message, state = 'ready') {
    const status = document.getElementById('dashboardDataStatus');
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('loading', state === 'loading');
    status.classList.toggle('error', state === 'error');
}

function getDashboardChart(id) {
    const element = document.getElementById(id);
    if (!element) return null;
    if (!window.echarts) {
        element.innerHTML = '<div class="h-100 d-flex align-items-center justify-content-center text-muted small">图表组件加载失败，请刷新页面重试</div>';
        return null;
    }
    if (!dashboardCharts.has(id)) {
        dashboardCharts.set(id, echarts.init(element, null, { renderer: 'canvas' }));
        if (dashboardResizeObserver) dashboardResizeObserver.observe(element);
    }
    return dashboardCharts.get(id);
}

function dashboardBaseOption() {
    return {
        animationDuration: 650,
        animationEasing: 'cubicOut',
        textStyle: {
            fontFamily: '"Microsoft YaHei", "PingFang SC", Arial, sans-serif',
            color: '#5f6c82'
        },
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(23, 33, 59, .95)',
            borderWidth: 0,
            padding: [9, 11],
            textStyle: { color: '#fff' }
        },
        toolbox: {
            right: 10,
            top: 5,
            feature: {
                saveAsImage: {
                    name: '创新数据看板',
                    title: '保存图表',
                    pixelRatio: 2
                }
            },
            iconStyle: { borderColor: '#8d99aa' },
            emphasis: { iconStyle: { borderColor: '#4465d8' } }
        }
    };
}

function dashboardEmptyOption(message = '当前筛选范围暂无数据') {
    return {
        title: {
            text: message,
            left: 'center',
            top: 'middle',
            textStyle: { color: '#96a1b2', fontSize: 13, fontWeight: 400 }
        },
        xAxis: { show: false },
        yAxis: { show: false },
        series: []
    };
}

function setDashboardChartOption(id, option, hasData) {
    const chart = getDashboardChart(id);
    if (!chart) return;
    chart.hideLoading();
    chart.clear();
    chart.setOption(hasData ? option : dashboardEmptyOption(), true);
}

function showDashboardLoading() {
    document.getElementById('total-proposals').textContent = '—';
    document.getElementById('adopted-proposals').textContent = '—';
    document.getElementById('effectiveness-rate').textContent = '—';
    setDashboardStatus('正在加载数据', 'loading');
    dashboardChartIds.forEach(id => {
        const chart = getDashboardChart(id);
        if (chart) {
            chart.showLoading('default', {
                text: '数据加载中',
                color: '#4465d8',
                textColor: '#6b7890',
                maskColor: 'rgba(255,255,255,.82)'
            });
        }
    });
}

function renderHorizontalDashboardChart(id, items, valueKey, seriesName, color, limit = 10) {
    const values = (items || [])
        .filter(item => item && item.name && item.name !== '暂无数据')
        .slice(0, limit)
        .reverse();
    const option = {
        ...dashboardBaseOption(),
        grid: { left: 18, right: 48, top: 42, bottom: 18, containLabel: true },
        xAxis: {
            type: 'value',
            minInterval: 1,
            axisLabel: { color: '#8793a6' },
            splitLine: { lineStyle: { color: '#edf1f6', type: 'dashed' } }
        },
        yAxis: {
            type: 'category',
            data: values.map(item => item.name),
            axisLine: { show: false },
            axisTick: { show: false },
            axisLabel: { color: '#536078', width: 110, overflow: 'truncate' }
        },
        series: [{
            name: seriesName,
            type: 'bar',
            barMaxWidth: 22,
            data: values.map(item => Number(item[valueKey] || 0)),
            itemStyle: { color, borderRadius: [0, 7, 7, 0] },
            label: {
                show: true,
                position: 'right',
                color: '#536078',
                fontWeight: 700
            }
        }]
    };
    setDashboardChartOption(id, option, values.length > 0);
}

function renderProposalPerformanceChart(items) {
    const values = (items || []).filter(item => item && item.name).slice(0, 8);
    const option = {
        ...dashboardBaseOption(),
        legend: {
            top: 5,
            left: 12,
            data: ['提案总量', '有效提案'],
            textStyle: { color: '#6b7890' }
        },
        grid: { left: 44, right: 20, top: 52, bottom: 48 },
        xAxis: {
            type: 'category',
            data: values.map(item => item.name),
            axisLine: { lineStyle: { color: '#d8e0ea' } },
            axisTick: { show: false },
            axisLabel: { color: '#647188', interval: 0, overflow: 'truncate', width: 70 }
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            axisLabel: { color: '#8793a6' },
            splitLine: { lineStyle: { color: '#edf1f6', type: 'dashed' } }
        },
        media: [
            {
                query: { maxWidth: 480 },
                option: {
                    grid: { bottom: 76 },
                    xAxis: { axisLabel: { rotate: 40, width: 48, fontSize: 10 } }
                }
            },
            {
                query: { minWidth: 481 },
                option: {
                    grid: { bottom: 48 },
                    xAxis: { axisLabel: { rotate: 0, width: 70, fontSize: 12 } }
                }
            }
        ],
        series: [
            {
                name: '提案总量',
                type: 'bar',
                barMaxWidth: 26,
                data: values.map(item => Number(item.count || 0)),
                itemStyle: { color: '#4465d8', borderRadius: [6, 6, 2, 2] }
            },
            {
                name: '有效提案',
                type: 'bar',
                barMaxWidth: 26,
                data: values.map(item => Number(item.effective_count || 0)),
                itemStyle: { color: '#17a078', borderRadius: [6, 6, 2, 2] }
            }
        ]
    };
    setDashboardChartOption('top-proposal-counts', option, values.length > 0);
}

function renderHighestScoreChart(items) {
    const values = (items || []).filter(item => item && item.name).slice(0, 10);
    const option = {
        ...dashboardBaseOption(),
        grid: { left: 46, right: 20, top: 45, bottom: 52 },
        xAxis: {
            type: 'category',
            data: values.map(item => item.name),
            axisLine: { lineStyle: { color: '#d8e0ea' } },
            axisTick: { show: false },
            axisLabel: { color: '#647188', interval: 0, rotate: values.length > 5 ? 25 : 0 }
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            name: '分数',
            nameTextStyle: { color: '#8793a6' },
            axisLabel: { color: '#8793a6' },
            splitLine: { lineStyle: { color: '#edf1f6', type: 'dashed' } }
        },
        media: [
            {
                query: { maxWidth: 480 },
                option: {
                    grid: { bottom: 76 },
                    xAxis: { axisLabel: { rotate: 40, width: 48, overflow: 'truncate', fontSize: 10 } }
                }
            },
            {
                query: { minWidth: 481 },
                option: {
                    grid: { bottom: 52 },
                    xAxis: { axisLabel: { rotate: values.length > 5 ? 25 : 0, width: 70, overflow: 'truncate', fontSize: 12 } }
                }
            }
        ],
        series: [{
            name: '最高分',
            type: 'bar',
            barMaxWidth: 32,
            data: values.map(item => Number(item.score || 0)),
            itemStyle: {
                borderRadius: [7, 7, 2, 2],
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: '#34b78f' },
                    { offset: 1, color: '#128c68' }
                ])
            },
            label: { show: true, position: 'top', color: '#536078', fontWeight: 700 }
        }]
    };
    setDashboardChartOption('top-highest-scores', option, values.length > 0);
}

function renderCategoryDashboardChart(items) {
    const values = (items || []).filter(item => item && item.name);
    const option = {
        ...dashboardBaseOption(),
        color: dashboardPalette,
        tooltip: {
            trigger: 'item',
            formatter: '{b}<br/>{c} 个提案（{d}%）',
            backgroundColor: 'rgba(23, 33, 59, .95)',
            borderWidth: 0,
            textStyle: { color: '#fff' }
        },
        legend: {
            type: 'scroll',
            orient: 'vertical',
            right: 4,
            top: 'middle',
            height: '72%',
            textStyle: { color: '#647188' }
        },
        media: [
            {
                query: { maxWidth: 520 },
                option: {
                    legend: {
                        orient: 'horizontal', left: 'center', right: 'auto',
                        top: 'auto', bottom: 0, width: '90%', height: 45,
                        textStyle: { width: 140, overflow: 'truncate' }
                    },
                    series: [{
                        radius: ['38%', '60%'], center: ['50%', '43%'],
                        label: { show: false }, labelLine: { show: false }
                    }]
                }
            },
            {
                query: { minWidth: 521 },
                option: {
                    legend: {
                        orient: 'vertical', left: 'auto', right: 4,
                        top: 'middle', bottom: 'auto', width: 'auto', height: '72%',
                        textStyle: { width: 140, overflow: 'truncate' }
                    },
                    series: [{
                        radius: ['43%', '68%'], center: ['38%', '53%'],
                        label: { show: true }, labelLine: { show: true }
                    }]
                }
            }
        ],
        series: [{
            name: '创新类别',
            type: 'pie',
            radius: ['43%', '68%'],
            center: ['38%', '53%'],
            padAngle: 2,
            avoidLabelOverlap: true,
            itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 7 },
            label: { formatter: '{b}\n{d}%', color: '#536078', lineHeight: 17 },
            emphasis: { scaleSize: 7 },
            data: values.map(item => ({ name: item.name, value: Number(item.count || 0) }))
        }]
    };
    setDashboardChartOption('category-distribution', option, values.length > 0);
}

function renderMonthlyDashboardChart(items) {
    const values = (items || []).slice().sort((left, right) => String(left.month).localeCompare(String(right.month)));
    const option = {
        ...dashboardBaseOption(),
        grid: { left: 48, right: 24, top: 50, bottom: 42 },
        xAxis: {
            type: 'category',
            data: values.map(item => item.month),
            axisLine: { lineStyle: { color: '#d8e0ea' } },
            axisTick: { show: false },
            axisLabel: { color: '#647188', margin: 12 }
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            axisLabel: { color: '#8793a6' },
            splitLine: { lineStyle: { color: '#edf1f6', type: 'dashed' } }
        },
        series: [{
            name: '提案数量',
            type: 'bar',
            barMaxWidth: 42,
            data: values.map(item => Number(item.count || 0)),
            itemStyle: {
                borderRadius: [7, 7, 2, 2],
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: '#6380e5' },
                    { offset: 1, color: '#4465d8' }
                ])
            },
            label: { show: true, position: 'top', color: '#536078', fontWeight: 700 },
            markLine: {
                symbol: 'none',
                label: { formatter: '平均 {c}', color: '#7657c8', position: 'insideEndTop' },
                lineStyle: { color: '#9c87db', type: 'dashed' },
                data: [{ type: 'average', name: '平均值' }]
            }
        }]
    };
    setDashboardChartOption('monthly-trend', option, values.length > 0);
}

async function loadDashboardData() {
    const requestId = ++dashboardRequestId;
    const startDate = document.getElementById('startDateFilter').value;
    const endDate = document.getElementById('endDateFilter').value;
    const refreshButton = document.getElementById('dashboardRefreshBtn');
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);

    showDashboardLoading();
    if (refreshButton) refreshButton.disabled = true;
    try {
        const url = '/innovation/api/get_dashboard_data' + (params.toString() ? '?' + params.toString() : '');
        const response = await axios.get(url);
        if (requestId !== dashboardRequestId) return;
        if (!response.data.success) throw new Error(response.data.message || '获取看板数据失败');
        displayDashboardData(response.data.data || {});
    } catch (error) {
        if (requestId !== dashboardRequestId) return;
        console.error('获取看板数据失败:', error);
        showDashboardError(error.message || '加载失败');
    } finally {
        if (requestId === dashboardRequestId && refreshButton) refreshButton.disabled = false;
    }
}

function displayDashboardData(data) {
    const basicStats = data.basic_stats || {};
    document.getElementById('total-proposals').textContent = Number(basicStats.total_count || 0).toLocaleString('zh-CN');
    document.getElementById('adopted-proposals').textContent = Number(basicStats.adopted_count || 0).toLocaleString('zh-CN');
    document.getElementById('effectiveness-rate').textContent = `${Number(basicStats.effectiveness_rate || 0).toLocaleString('zh-CN')}%`;

    renderHorizontalDashboardChart('top-department', data.top_departments, 'score', '部门积分', '#4465d8', 10);
    renderHorizontalDashboardChart('top-person', data.top_persons, 'score', '个人积分', '#7657c8', 5);
    renderProposalPerformanceChart(data.top_proposal_counts);
    renderHighestScoreChart(data.top_highest_scores);
    renderCategoryDashboardChart(data.categories);
    renderMonthlyDashboardChart(data.monthly_trend);

    const startDate = document.getElementById('startDateFilter').value;
    const endDate = document.getElementById('endDateFilter').value;
    const periodText = startDate || endDate
        ? `${startDate || '最早'} 至 ${endDate || '今天'}`
        : '全部日期';
    setDashboardStatus(`${periodText} · 已更新`);
}

function showDashboardError(message = '加载失败') {
    document.getElementById('total-proposals').textContent = '—';
    document.getElementById('adopted-proposals').textContent = '—';
    document.getElementById('effectiveness-rate').textContent = '—';
    setDashboardStatus(message, 'error');
    dashboardChartIds.forEach(id => {
        const chart = getDashboardChart(id);
        if (!chart) return;
        chart.hideLoading();
        chart.clear();
        chart.setOption(dashboardEmptyOption('数据加载失败，请稍后重试'), true);
    });
}

function refreshDashboard() {
    loadDashboardData();
}

function filterByDateRange() {
    const startInput = document.getElementById('startDateFilter');
    const endInput = document.getElementById('endDateFilter');
    startInput.setCustomValidity('');
    if (startInput.value && endInput.value && startInput.value > endInput.value) {
        startInput.setCustomValidity('开始日期不能晚于结束日期');
        startInput.reportValidity();
        return;
    }
    loadDashboardData();
}

function clearDateFilter() {
    document.getElementById('startDateFilter').value = '';
    document.getElementById('endDateFilter').value = '';
    loadDashboardData();
}

function formatLocalDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function initializeDateFilter() {
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    const startDateInput = document.getElementById('startDateFilter');
    const endDateInput = document.getElementById('endDateFilter');
    if (startDateInput && endDateInput) {
        startDateInput.value = formatLocalDate(firstDay);
        endDateInput.value = formatLocalDate(lastDay);
    }
}

// 页面加载时获取数据
document.addEventListener('DOMContentLoaded', function() {
    initializeDateFilter(); // 初始化日期筛选器
    loadStatistics();
    loadDashboardData(); // 加载数字看板数据
    
    // 初始加载排行榜（仅当相关元素存在时）
    if (document.getElementById('ranking-list')) {
        loadPointsRanking('current');
    }

    // 排行榜类型切换
    document.querySelectorAll('input[name="rankingType"]').forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.checked) {
                loadPointsRanking(this.value);
            }
        });
    });
});

window.addEventListener('resize', scheduleDashboardResize);
