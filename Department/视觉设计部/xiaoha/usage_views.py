"""Render Xiaoha usage and account reporting."""

from __future__ import annotations


def build_xiaoha_usage_dashboard_html(
    dashboard_data,
    *,
    XIAOHA_DASHBOARD_CACHE_SECONDS,
    html,
    json,
) -> str:
    serialized_data = (
        json.dumps(dashboard_data, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    empty_note = "" if bool(dashboard_data.get("has_today_data")) else (
        '<div class="empty-note">今天暂时没有使用记录，图表将在产生新记录后自动更新。</div>'
    )
    return f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"
                onerror="this.onerror=null;this.src='https://unpkg.com/echarts@5.5.1/dist/echarts.min.js';"></script>
        <style>
            * {{ box-sizing: border-box; }}
            html, body {{
                margin: 0;
                padding: 0;
                background: transparent;
                color: #f6f7ff;
                font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
            }}
            .dashboard {{ padding: 4px 2px 18px; }}
            .hero {{
                position: relative;
                overflow: hidden;
                padding: 24px 26px;
                border: 1px solid rgba(255,255,255,.09);
                border-radius: 22px;
                background:
                    radial-gradient(circle at 82% 18%, rgba(126,100,255,.28), transparent 32%),
                    linear-gradient(135deg, rgba(15,27,54,.98), rgba(10,18,39,.96));
                box-shadow: 0 20px 55px rgba(0,0,0,.24);
            }}
            .hero::after {{
                content: "";
                position: absolute;
                width: 240px;
                height: 240px;
                right: -80px;
                top: -125px;
                border: 42px solid rgba(102,231,255,.08);
                border-radius: 50%;
            }}
            .eyebrow {{
                display: inline-flex;
                align-items: center;
                gap: 7px;
                padding: 6px 10px;
                border-radius: 999px;
                background: rgba(116,91,255,.18);
                color: #b9adff;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: .08em;
            }}
            .eyebrow::before {{
                content: "";
                width: 7px;
                height: 7px;
                border-radius: 50%;
                background: #6ce5ff;
                box-shadow: 0 0 14px rgba(108,229,255,.9);
            }}
            h1 {{ margin: 12px 0 5px; font-size: 27px; line-height: 1.15; }}
            .subtitle {{ color: rgba(220,226,255,.68); font-size: 13px; }}
            .metrics {{
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 12px;
                margin-top: 18px;
            }}
            .metric {{
                min-height: 100px;
                padding: 15px 16px;
                border: 1px solid rgba(255,255,255,.075);
                border-radius: 16px;
                background: linear-gradient(150deg, rgba(255,255,255,.055), rgba(255,255,255,.018));
            }}
            .metric-label {{ color: rgba(221,226,255,.65); font-size: 12px; }}
            .metric-value {{ margin-top: 6px; font-size: 27px; line-height: 1.05; font-weight: 800; }}
            .metric-sub {{
                margin-top: 8px;
                color: #8fddff;
                font-size: 11px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}
            .empty-note {{
                margin-top: 12px;
                padding: 10px 13px;
                border: 1px solid rgba(247,197,92,.18);
                border-radius: 12px;
                background: rgba(247,197,92,.07);
                color: #f5d990;
                font-size: 12px;
            }}
            .chart-grid {{
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
                gap: 14px;
                margin-top: 14px;
            }}
            .chart-card {{
                min-width: 0;
                padding: 15px 15px 8px;
                border: 1px solid rgba(255,255,255,.075);
                border-radius: 18px;
                background: linear-gradient(145deg, rgba(12,24,49,.94), rgba(8,17,36,.94));
                box-shadow: 0 14px 38px rgba(0,0,0,.18);
            }}
            .chart-card.wide {{ grid-column: 1 / -1; }}
            .chart-title {{ margin: 0 0 1px 4px; font-size: 14px; font-weight: 750; }}
            .chart-caption {{ margin: 3px 0 0 4px; color: rgba(216,223,255,.52); font-size: 11px; }}
            .chart {{ width: 100%; height: 300px; }}
            .chart-card.wide .chart {{ height: 330px; }}
            .load-error {{
                display: none;
                margin-top: 14px;
                padding: 14px;
                border-radius: 14px;
                background: rgba(255,103,133,.10);
                color: #ffb2c0;
                font-size: 13px;
            }}
            @media (max-width: 850px) {{
                .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
                .chart-grid {{ grid-template-columns: 1fr; }}
                .chart-card.wide {{ grid-column: auto; }}
            }}
        </style>
    </head>
    <body>
        <main class="dashboard">
            <section class="hero">
                <div class="eyebrow">TODAY · {html.escape(str(dashboard_data.get('date') or ''))}</div>
                <h1>功能使用仪表盘</h1>
                <div class="subtitle">数据来自 AI_TuPian · 按 GongNeng 统计 · 每 {XIAOHA_DASHBOARD_CACHE_SECONDS} 秒自动更新</div>
                <div class="metrics">
                    <div class="metric">
                        <div class="metric-label">今日使用记录</div>
                        <div class="metric-value">{int(dashboard_data.get('today_total') or 0):,}</div>
                        <div class="metric-sub">{html.escape(str(dashboard_data.get('delta_label') or ''))}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">今日活跃账号</div>
                        <div class="metric-value">{int(dashboard_data.get('active_accounts') or 0):,}</div>
                        <div class="metric-sub">产生过使用记录的账号</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">今日使用功能</div>
                        <div class="metric-value">{int(dashboard_data.get('active_features') or 0):,}</div>
                        <div class="metric-sub">最高：{html.escape(str(dashboard_data.get('top_feature_name') or '暂无'))} · {int(dashboard_data.get('top_feature_count') or 0):,} 次</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">今日高峰时段</div>
                        <div class="metric-value">{html.escape(str(dashboard_data.get('peak_hour') or '—'))}</div>
                        <div class="metric-sub">该小时共 {int(dashboard_data.get('peak_count') or 0):,} 条记录</div>
                    </div>
                </div>
                {empty_note}
            </section>
            <section class="chart-grid">
                <article class="chart-card">
                    <div class="chart-title">今日各功能使用排行</div>
                    <div class="chart-caption">展示当天 AI_TuPian 中全部 GongNeng 记录</div>
                    <div id="featureRanking" class="chart"></div>
                </article>
                <article class="chart-card">
                    <div class="chart-title">最近 7 天使用趋势</div>
                    <div class="chart-caption">按天汇总全部功能，观察整体使用变化</div>
                    <div id="dailyTrend" class="chart"></div>
                </article>
                <article class="chart-card wide">
                    <div class="chart-title">每小时使用对比</div>
                    <div class="chart-caption">今日各功能走势，并以虚线对比昨日总量</div>
                    <div id="hourlyTrend" class="chart"></div>
                </article>
            </section>
            <div id="loadError" class="load-error">图表组件暂时未加载成功，请刷新页面后重试。</div>
        </main>
        <script>
            const dashboardData = {serialized_data};
            const palette = ['#8b78ff', '#55d7ff', '#ff7fa7', '#5ce0a0', '#f6c95c', '#ff9b69'];
            const axisColor = 'rgba(215,223,255,.48)';
            const gridLine = 'rgba(205,216,255,.075)';
            const charts = [];

            function baseTooltip() {{
                return {{
                    trigger: 'axis',
                    backgroundColor: 'rgba(7,14,30,.96)',
                    borderColor: 'rgba(139,120,255,.35)',
                    textStyle: {{ color: '#f5f7ff', fontSize: 12 }},
                    axisPointer: {{ type: 'line', lineStyle: {{ color: 'rgba(108,229,255,.3)' }} }}
                }};
            }}

            function initDashboard() {{
                if (!window.echarts) {{
                    document.getElementById('loadError').style.display = 'block';
                    return;
                }}

                const ranking = echarts.init(document.getElementById('featureRanking'));
                const rankingNames = [...dashboardData.feature_names].reverse();
                const rankingCounts = [...dashboardData.feature_counts].reverse();
                ranking.setOption({{
                    animationDuration: 650,
                    color: [palette[0]],
                    tooltip: baseTooltip(),
                    grid: {{ left: 108, right: 38, top: 18, bottom: 25 }},
                    xAxis: {{
                        type: 'value',
                        minInterval: 1,
                        axisLabel: {{ color: axisColor, fontSize: 10 }},
                        splitLine: {{ lineStyle: {{ color: gridLine }} }}
                    }},
                    yAxis: {{
                        type: 'category',
                        data: rankingNames,
                        axisTick: {{ show: false }},
                        axisLine: {{ show: false }},
                        axisLabel: {{
                            color: '#dfe4ff',
                            fontSize: 11,
                            width: 92,
                            overflow: 'truncate'
                        }}
                    }},
                    series: [{{
                        name: '使用记录',
                        type: 'bar',
                        data: rankingCounts,
                        barMaxWidth: 15,
                        showBackground: true,
                        backgroundStyle: {{ color: 'rgba(255,255,255,.035)', borderRadius: 8 }},
                        itemStyle: {{
                            borderRadius: [0, 8, 8, 0],
                            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                                {{ offset: 0, color: '#715bff' }},
                                {{ offset: 1, color: '#58d8ff' }}
                            ])
                        }},
                        label: {{ show: true, position: 'right', color: '#f5f7ff', fontSize: 10 }}
                    }}]
                }});
                charts.push(ranking);

                const daily = echarts.init(document.getElementById('dailyTrend'));
                daily.setOption({{
                    animationDuration: 650,
                    color: [palette[1]],
                    tooltip: baseTooltip(),
                    grid: {{ left: 44, right: 22, top: 25, bottom: 34 }},
                    xAxis: {{
                        type: 'category',
                        boundaryGap: false,
                        data: dashboardData.day_labels,
                        axisTick: {{ show: false }},
                        axisLine: {{ lineStyle: {{ color: gridLine }} }},
                        axisLabel: {{ color: axisColor, fontSize: 10 }}
                    }},
                    yAxis: {{
                        type: 'value',
                        minInterval: 1,
                        axisLine: {{ show: false }},
                        axisLabel: {{ color: axisColor, fontSize: 10 }},
                        splitLine: {{ lineStyle: {{ color: gridLine }} }}
                    }},
                    series: [{{
                        name: '使用记录',
                        type: 'line',
                        smooth: .28,
                        symbol: 'circle',
                        symbolSize: 7,
                        lineStyle: {{ width: 3 }},
                        areaStyle: {{
                            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                {{ offset: 0, color: 'rgba(85,215,255,.36)' }},
                                {{ offset: 1, color: 'rgba(85,215,255,.015)' }}
                            ])
                        }},
                        data: dashboardData.day_totals
                    }}]
                }});
                charts.push(daily);

                const hourly = echarts.init(document.getElementById('hourlyTrend'));
                const featureSeries = dashboardData.feature_hour_series.map((item, index) => ({{
                    name: item.name,
                    type: 'line',
                    smooth: .32,
                    showSymbol: false,
                    emphasis: {{ focus: 'series' }},
                    lineStyle: {{ width: 2 }},
                    data: item.data,
                    color: palette[index % palette.length]
                }}));
                featureSeries.push({{
                    name: '昨日总量',
                    type: 'line',
                    smooth: .25,
                    showSymbol: false,
                    data: dashboardData.yesterday_hour_totals,
                    color: 'rgba(225,231,255,.46)',
                    lineStyle: {{ width: 1.5, type: 'dashed' }}
                }});
                hourly.setOption({{
                    animationDuration: 650,
                    tooltip: baseTooltip(),
                    legend: {{
                        type: 'scroll',
                        top: 5,
                        left: 45,
                        right: 20,
                        textStyle: {{ color: 'rgba(226,231,255,.72)', fontSize: 10 }},
                        pageTextStyle: {{ color: axisColor }}
                    }},
                    grid: {{ left: 46, right: 22, top: 48, bottom: 35 }},
                    xAxis: {{
                        type: 'category',
                        boundaryGap: false,
                        data: dashboardData.hour_labels,
                        axisTick: {{ show: false }},
                        axisLine: {{ lineStyle: {{ color: gridLine }} }},
                        axisLabel: {{ color: axisColor, fontSize: 9, interval: 2 }}
                    }},
                    yAxis: {{
                        type: 'value',
                        minInterval: 1,
                        axisLine: {{ show: false }},
                        axisLabel: {{ color: axisColor, fontSize: 10 }},
                        splitLine: {{ lineStyle: {{ color: gridLine }} }}
                    }},
                    series: featureSeries
                }});
                charts.push(hourly);
                window.addEventListener('resize', () => charts.forEach(chart => chart.resize()));
            }}

            if (document.readyState === 'complete') {{
                initDashboard();
            }} else {{
                window.addEventListener('load', initDashboard, {{ once: true }});
            }}
        </script>
    </body>
    </html>
    """
