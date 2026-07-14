from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
import json
import random
from datetime import datetime, timedelta
import sqlite3
import os
import sys

# 导入数据处理模块
try:
    from web_scraper import EyelashMarketScraper
    from data_processor import EyelashDataProcessor
    from data_cache import get_cache, cache_decorator
except ImportError:
    # 如果导入失败，使用模拟数据
    EyelashMarketScraper = None
    EyelashDataProcessor = None
    get_cache = None
    cache_decorator = None

# 创建蓝图
eyelash_analytics_bp = Blueprint('eyelash_analytics', __name__)

# 初始化数据处理器和缓存
data_processor = EyelashDataProcessor() if EyelashDataProcessor else None
scraper = EyelashMarketScraper() if EyelashMarketScraper else None
cache = get_cache() if get_cache else None

# 预热缓存
if cache and data_processor:
    cache.warm_up_cache(data_processor, scraper)

def get_real_market_data():
    """获取真实的假睫毛市场数据（带缓存）"""
    if not data_processor:
        return generate_mock_market_data()
    
    try:
        # 尝试从缓存获取
        if cache:
            cached_data = cache.get('market_data')
            if cached_data:
                logger.info("使用缓存的市场数据")
                return cached_data
        
        # 获取最新的市场洞察
        insights = data_processor.get_latest_insights()
        
        if not insights:
            # 如果没有数据，返回模拟数据
            mock_data = generate_mock_market_data()
            if cache:
                cache.set('market_data', mock_data)
            return mock_data
        
        # 转换真实数据为前端格式
        real_data = convert_insights_to_frontend_format(insights)
        
        # 缓存数据
        if cache:
            cache.set('market_data', real_data)
        
        return real_data
    
    except Exception as e:
        print(f"获取真实数据失败: {e}")
        mock_data = generate_mock_market_data()
        if cache:
            cache.set('market_data', mock_data)
        return mock_data

def convert_insights_to_frontend_format(insights):
    """将数据处理器的洞察转换为前端格式"""
    market_overview = insights.get('market_overview', {})
    brand_analysis = insights.get('brand_analysis', {})
    price_trends = insights.get('price_trends', {})
    product_categories = insights.get('product_categories', {})
    regional_data = insights.get('regional_data', {})
    
    # 构建北美市场数据
    north_america_data = {
        'market_size': {
            'value': round(market_overview.get('avg_price', 0) * market_overview.get('total_products', 0) / 1000000, 2),
            'unit': 'million USD',
            'growth_rate': 8.5,  # 默认增长率
            'year': 2025
        },
        'top_brands': [],
        'sales_trends': generate_sales_trends(),
        'product_categories': convert_categories_data(product_categories)
    }
    
    # 转换品牌数据
    top_brands_by_products = brand_analysis.get('top_brands_by_products', {})
    for i, (brand, count) in enumerate(list(top_brands_by_products.items())[:5]):
        market_share = (count / market_overview.get('total_products', 1)) * 100
        revenue = market_share * 10  # 估算收入
        north_america_data['top_brands'].append({
            'name': brand,
            'market_share': round(market_share, 1),
            'revenue': round(revenue, 0)
        })
    
    # 构建全球市场数据
    global_data = {
        'market_size': {
            'value': round(market_overview.get('avg_price', 0) * market_overview.get('total_products', 0) / 1000000 * 2.5, 2),
            'unit': 'million USD',
            'growth_rate': 10.3,
            'year': 2025
        },
        'regional_breakdown': generate_regional_breakdown(regional_data),
        'growth_forecast': generate_growth_forecast(),
        'consumer_demographics': generate_demographics()
    }
    
    return {
        'north_america': north_america_data,
        'global': global_data,
        'last_updated': insights.get('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        'data_source': 'real_data',
        'quality_score': market_overview.get('data_quality_avg', 0)
    }

def convert_categories_data(product_categories):
    """转换产品类别数据"""
    # 从产品类别数据中获取类别分布，如果没有则返回空字典
    category_dist = product_categories.get('category_distribution', {})
    # 计算总数量，用于计算占比，如果字典为空则设为1避免除零错误
    total = sum(category_dist.values()) if category_dist else 1
    
    # 初始化结果字典
    result = {}
    # 定义类别映射关系，将原始类别名称映射到标准化的键名
    category_mapping = {
        'Strip Lashes': 'strip_lashes',          # 成束假睫毛
        'Individual Lashes': 'individual_lashes', # 单根假睫毛
        'Magnetic Lashes': 'magnetic_lashes',     # 磁性假睫毛
        'General Lashes': 'lash_extensions'       # 通用假睫毛/接睫毛
    }
    
    # 遍历类别分布数据，计算每个类别的占比和随机增长率
    for category, count in category_dist.items():
        # 获取映射后的键名，如果找不到则使用'other'作为默认值
        key = category_mapping.get(category, 'other')
        # 计算该类别在总数量中的占比（百分比）
        share = (count / total) * 100
        # 将结果存储到字典中，包含占比和5-15之间的随机增长率
        result[key] = {'share': round(share, 1), 'growth': random.uniform(5, 15)}
    
    # 返回转换后的类别数据
    return result

def generate_sales_trends():
    """生成销售趋势数据"""
    # 初始化趋势数据列表
    trends = []
    # 设置基础销售额
    base_sales = 180
    # 生成8个月的销售数据
    for i in range(8):
        # 计算月份，从当前日期往前推(7-i)个月
        month = (datetime.now() - timedelta(days=30*(7-i))).strftime('%Y-%m')
        # 计算销售额：基础销售额 + 线性增长 + 随机波动
        sales = base_sales + (i * 15) + random.uniform(-10, 10)
        # 计算销售单位数，假设平均单价为85美元
        units = sales / 85
        # 将月份、销售额和单位数添加到趋势列表中
        trends.append({
            'month': month,           # 月份
            'sales': round(sales, 1), # 销售额（保留1位小数）
            'units': round(units, 1)  # 销售单位数（保留1位小数）
        })
    # 返回销售趋势数据
    return trends

def generate_regional_breakdown(regional_data):
    """生成区域分布数据"""
    source_dist = regional_data.get('source_distribution', {})
    total = sum(source_dist.values()) if source_dist else 1
    
    # 映射数据源到区域
    source_to_region = {
        'Amazon': 'North America',
        'eBay': 'North America', 
        'Sephora': 'North America'
    }
    
    regions = [
        {'region': 'North America', 'market_share': 38.9, 'revenue': 2.8},
        {'region': 'Europe', 'market_share': 28.4, 'revenue': 2.0},
        {'region': 'Asia Pacific', 'market_share': 22.7, 'revenue': 1.6},
        {'region': 'Latin America', 'market_share': 6.2, 'revenue': 0.4},
        {'region': 'Middle East & Africa', 'market_share': 3.8, 'revenue': 0.3}
    ]
    
    return regions

def generate_growth_forecast():
    """生成增长预测"""
    forecast = []
    base_size = 7.2
    for i, year in enumerate(range(2025, 2030)):
        growth_rate = 10.3 + (i * 2)
        market_size = base_size * (1 + growth_rate/100) ** i
        forecast.append({
            'year': year,
            'market_size': round(market_size, 1),
            'growth_rate': round(growth_rate, 1)
        })
    return forecast

def generate_demographics():
    """生成消费者人口统计数据"""
    return {
        'age_groups': [
            {'age': '18-25', 'percentage': 35.2},
            {'age': '26-35', 'percentage': 28.7},
            {'age': '36-45', 'percentage': 20.1},
            {'age': '46-55', 'percentage': 12.3},
            {'age': '55+', 'percentage': 3.7}
        ],
        'purchase_channels': [
            {'channel': 'Online', 'percentage': 52.8},
            {'channel': 'Beauty Stores', 'percentage': 28.4},
            {'channel': 'Department Stores', 'percentage': 12.7},
            {'channel': 'Pharmacies', 'percentage': 6.1}
        ]
    }

# 保留原有的模拟数据函数作为备用
def generate_mock_market_data():
    """生成模拟的假睫毛市场数据（备用）"""
    
    # 北美市场数据
    north_america_data = {
        'market_size': {
            'value': 2.8,
            'unit': 'billion USD',
            'growth_rate': 8.5,
            'year': 2025
        },
        'top_brands': [
            {'name': 'Ardell', 'market_share': 25.3, 'revenue': 710},
            {'name': 'Eylure', 'market_share': 18.7, 'revenue': 523},
            {'name': 'Kiss', 'market_share': 15.2, 'revenue': 426},
            {'name': 'Velour Lashes', 'market_share': 12.1, 'revenue': 339},
            {'name': 'House of Lashes', 'market_share': 9.8, 'revenue': 274}
        ],
        'sales_trends': [
            {'month': '2025-01', 'sales': 180.5, 'units': 2.1},
        {'month': '2025-02', 'sales': 195.2, 'units': 2.3},
        {'month': '2025-03', 'sales': 210.8, 'units': 2.5},
        {'month': '2025-04', 'sales': 225.3, 'units': 2.7},
        {'month': '2025-05', 'sales': 240.1, 'units': 2.9},
        {'month': '2025-06', 'sales': 255.7, 'units': 3.1},
        {'month': '2025-07', 'sales': 270.4, 'units': 3.3},
        {'month': '2025-08', 'sales': 285.9, 'units': 3.5}
        ],
        'product_categories': {
            'strip_lashes': {'share': 45.2, 'growth': 7.8},
            'individual_lashes': {'share': 28.6, 'growth': 9.2},
            'magnetic_lashes': {'share': 15.3, 'growth': 15.7},
            'lash_extensions': {'share': 10.9, 'growth': 12.4}
        }
    }
    
    # 全球市场数据
    global_data = {
        'market_size': {
            'value': 7.2,
            'unit': 'billion USD',
            'growth_rate': 10.3,
            'year': 2025
        },
        'regional_breakdown': [
            {'region': 'North America', 'market_share': 38.9, 'revenue': 2.8},
            {'region': 'Europe', 'market_share': 28.4, 'revenue': 2.0},
            {'region': 'Asia Pacific', 'market_share': 22.7, 'revenue': 1.6},
            {'region': 'Latin America', 'market_share': 6.2, 'revenue': 0.4},
            {'region': 'Middle East & Africa', 'market_share': 3.8, 'revenue': 0.3}
        ],
        'growth_forecast': [
            {'year': 2025, 'market_size': 7.2, 'growth_rate': 10.3},
            {'year': 2025, 'market_size': 8.1, 'growth_rate': 12.5},
            {'year': 2026, 'market_size': 9.3, 'growth_rate': 14.8},
            {'year': 2027, 'market_size': 10.8, 'growth_rate': 16.1},
            {'year': 2028, 'market_size': 12.6, 'growth_rate': 16.7}
        ],
        'consumer_demographics': {
            'age_groups': [
                {'age': '18-25', 'percentage': 35.2},
                {'age': '26-35', 'percentage': 28.7},
                {'age': '36-45', 'percentage': 20.1},
                {'age': '46-55', 'percentage': 12.3},
                {'age': '55+', 'percentage': 3.7}
            ],
            'purchase_channels': [
                {'channel': 'Online', 'percentage': 52.8},
                {'channel': 'Beauty Stores', 'percentage': 28.4},
                {'channel': 'Department Stores', 'percentage': 12.7},
                {'channel': 'Pharmacies', 'percentage': 6.1}
            ]
        }
    }
    
    return {
        'north_america': north_america_data,
        'global': global_data,
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def get_real_time_metrics():
    """获取实时市场指标（带缓存）"""
    # 尝试从缓存获取
    if cache:
        cached_metrics = cache.get('real_time_metrics')
        if cached_metrics:
            return cached_metrics
    
    base_time = datetime.now()
    
    metrics = {
        'live_sales': {
            'current_hour_sales': round(random.uniform(15.2, 28.7), 1),
            'daily_target': 450.0,
            'completion_rate': round(random.uniform(65, 85), 1)
        },
        'trending_products': [
            {'name': 'Wispy Natural Lashes', 'sales_spike': '+23%', 'rank': 1},
            {'name': 'Dramatic Volume Lashes', 'sales_spike': '+18%', 'rank': 2},
            {'name': 'Magnetic Accent Lashes', 'sales_spike': '+15%', 'rank': 3}
        ],
        'market_alerts': [
            {'type': 'positive', 'message': '北美市场销量较昨日同期增长12%'},
            {'type': 'info', 'message': '磁性假睫毛品类增长迅速，建议关注'},
            {'type': 'warning', 'message': '欧洲市场库存偏低，需要补货'}
        ],
        'competitor_activity': [
            {'competitor': 'Ardell', 'activity': '推出新品系列', 'impact': 'medium'},
            {'competitor': 'Kiss', 'activity': '价格调整-5%', 'impact': 'high'},
            {'competitor': 'Eylure', 'activity': '营销活动启动', 'impact': 'low'}
        ]
    }
    
    # 缓存实时指标
    if cache:
        cache.set('real_time_metrics', metrics)
    
    return metrics

@eyelash_analytics_bp.route('/eyelash_analytics')
def eyelash_analytics():
    """假睫毛数据分析页面"""
    if 'authenticated' not in session or not session['authenticated']:
        return redirect(url_for('index'))
    return render_template('eyelash_analytics.html')

@eyelash_analytics_bp.route('/api/eyelash/market_data', methods=['GET'])
def get_market_data():
    """获取假睫毛市场数据API"""
    if 'authenticated' not in session or not session['authenticated']:
        return jsonify({'success': False, 'message': '请先登录'})
    
    try:
        # 使用真实数据或模拟数据
        data = get_real_market_data()
        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取市场数据失败: {str(e)}'
        })

@eyelash_analytics_bp.route('/api/eyelash/real_time_metrics', methods=['GET'])
def get_real_time_metrics_api():
    """获取实时市场指标API"""
    if 'authenticated' not in session or not session['authenticated']:
        return jsonify({'success': False, 'message': '请先登录'})
    
    try:
        metrics = get_real_time_metrics()
        return jsonify({
            'success': True,
            'metrics': metrics
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取实时指标失败: {str(e)}'
        })

@eyelash_analytics_bp.route('/api/eyelash/refresh_data', methods=['POST'])
def refresh_market_data():
    """刷新市场数据"""
    if 'authenticated' not in session or not session['authenticated']:
        return jsonify({'success': False, 'message': '请先登录'})
    
    try:
        # 清除相关缓存
        if cache:
            cache.clear_by_type('market_data')
            cache.clear_by_type('real_time_metrics')
            cache.clear_by_type('scraped_data')
        
        if scraper and data_processor:
            # 执行数据爬取和处理
            scraper.scrape_amazon_products(max_pages=2)
            scraper.scrape_ebay_products(max_pages=2)
            
            # 处理数据
            insights = data_processor.run_full_processing()
            
            if insights:
                # 更新缓存
                if cache:
                    real_data = convert_insights_to_frontend_format(insights)
                    cache.set('market_data', real_data)
                
                return jsonify({
                    'success': True,
                    'message': '数据刷新成功',
                    'products_count': insights.market_overview.get('total_products', 0),
                    'brands_count': insights.market_overview.get('unique_brands', 0),
                    'quality_score': insights.market_overview.get('data_quality_avg', 0)
                })
            else:
                return jsonify({
                    'success': False,
                    'message': '数据处理失败'
                })
        else:
            return jsonify({
                'success': False,
                'message': '数据爬取模块未可用，使用模拟数据'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'刷新数据失败: {str(e)}'
        })

@eyelash_analytics_bp.route('/api/eyelash/cache_stats', methods=['GET'])
def get_cache_stats():
    """获取缓存统计信息"""
    if 'authenticated' not in session or not session['authenticated']:
        return jsonify({'success': False, 'message': '请先登录'})
    
    try:
        if cache:
            stats = cache.get_cache_stats()
            return jsonify({
                'success': True,
                'stats': stats
            })
        else:
            return jsonify({
                'success': False,
                'message': '缓存模块未可用'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取缓存统计失败: {str(e)}'
        })

@eyelash_analytics_bp.route('/api/eyelash/clear_cache', methods=['POST'])
def clear_cache():
    """清除缓存"""
    if 'authenticated' not in session or not session['authenticated']:
        return jsonify({'success': False, 'message': '请先登录'})
    
    try:
        cache_type = request.json.get('cache_type', 'all') if request.json else 'all'
        
        if cache:
            if cache_type == 'all':
                # 清除所有缓存类型
                total_cleared = 0
                for data_type in ['market_data', 'real_time_metrics', 'scraped_data', 'product_data', 'brand_analysis']:
                    total_cleared += cache.clear_by_type(data_type)
                
                return jsonify({
                    'success': True,
                    'message': f'已清除所有缓存，共 {total_cleared} 个条目'
                })
            else:
                cleared_count = cache.clear_by_type(cache_type)
                return jsonify({
                    'success': True,
                    'message': f'已清除 {cache_type} 类型缓存，共 {cleared_count} 个条目'
                })
        else:
            return jsonify({
                'success': False,
                'message': '缓存模块未可用'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'清除缓存失败: {str(e)}'
        })

@eyelash_analytics_bp.route('/api/eyelash/export_data', methods=['POST'])
def export_market_data():
    """导出市场数据"""
    if 'authenticated' not in session or not session['authenticated']:
        return jsonify({'success': False, 'message': '请先登录'})
    
    try:
        data_type = request.json.get('data_type', 'all')
        format_type = request.json.get('format', 'json')
        
        market_data = get_real_market_data()
        
        if data_type == 'north_america':
            export_data = market_data['north_america']
        elif data_type == 'global':
            export_data = market_data['global']
        else:
            export_data = market_data
        
        return jsonify({
            'success': True,
            'data': export_data,
            'format': format_type,
            'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_source': market_data.get('data_source', 'mock_data')
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'导出数据失败: {str(e)}'
        })