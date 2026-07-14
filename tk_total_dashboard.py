from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, date, timedelta
import time
import threading
from calendar import monthrange
from department_permissions import require_permission
import bjc

tk_dashboard_bp = Blueprint('tk_dashboard', __name__)

admin_users = ['周俊成', '毕景春', '陶晓飞', '李昌翰', '孙军', '李春', '宋亚倩', '王丰慧', '陈梦昭']
partial_admin_users = ['张莉','周俊成', '毕景春', '陶晓飞', '李昌翰', '孙军', '李春', '宋亚倩', '王丰慧', '陈梦昭']
dashboard_82_users = ['张莉', '周俊成', '毕景春', '陶晓飞', '李昌翰', '孙军', '李春', '宋亚倩', '王丰慧', '陈梦昭', '朱晓禹', '侯梁']
dashboard_88_users = ['张莉', '周俊成', '毕景春', '陶晓飞', '李昌翰', '孙军', '李春', '宋亚倩', '王丰慧', '陈梦昭', '朱晓禹', '侯梁', '刘俊霞', '李晓明']
dashboard_90_users = ['张莉', '周俊成', '毕景春', '陶晓飞', '李昌翰', '孙军', '李春', '宋亚倩', '王丰慧', '陈梦昭', '朱晓禹', '侯梁', '孙洁']

def is_admin_user():
    return session.get('feishu_user_name', '') in admin_users

def is_partial_admin_user():
    return session.get('feishu_user_name', '') in partial_admin_users

def is_dashboard_82_user():
    return session.get('feishu_user_name', '') in dashboard_82_users

def is_dashboard_88_user():
    return session.get('feishu_user_name', '') in dashboard_88_users

def is_dashboard_90_user():
    return session.get('feishu_user_name', '') in dashboard_90_users

METRICS_CACHE_TTL = 60
_metrics_cache = {}
DEFAULT_SHOP_NAME = '86'
DEFAULT_CACHE_REFRESH_SEC = 7200
_default_cached_payload = None
_default_cached_exp = 0
_default_thread_started = False
_precomputed_shop_payloads = {}
_precomputed_week_shop_payloads = {}

def _compute_metrics_payload(start_dt, end_dt, shops, target_net_profit_param):
    safe_shops = [str(s).replace("'", "''") for s in shops]
    in_clause = ','.join([f"'{s}'" for s in safe_shops])
    yday = date.today() - timedelta(days=1)
    yday_str = yday.strftime('%Y-%m-%d')
    total_val = 0.0

    today = date.today()
    period_days = (end_dt - start_dt).days + 1
    month_total_days = monthrange(end_dt.year, end_dt.month)[1]
    progress_day = max(0, min(month_total_days, (today - start_dt).days))
    progress_pct = round(0.0 if month_total_days <= 0 else (progress_day / month_total_days) * 100, 2)

    curr_year = end_dt.year
    curr_month = end_dt.month

    prev_month = end_dt.month - 1
    prev_year = end_dt.year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    prev_start = date(prev_year, prev_month, 1)
    prev_last_day = monthrange(prev_year, prev_month)[1]
    prev_end = date(prev_year, prev_month, prev_last_day)

    prev_start_str = prev_start.strftime('%Y-%m-%d')
    prev_end_str = prev_end.strftime('%Y-%m-%d')

    def _get_influencer_video_fee_detail(start_str, end_str):
        sql = f"""
            SELECT
                ISNULL(SUM(CASE WHEN xiangmu = '刷单费' THEN feiyonge ELSE 0 END), 0) AS shuadan_fee,
                ISNULL(SUM(CASE WHEN xiangmu = '售后' THEN feiyonge ELSE 0 END), 0) AS shouhou_fee,
                ISNULL(SUM(CASE WHEN xiangmu = '网红坑位费' THEN feiyonge ELSE 0 END), 0) AS wanghong_kengwei_fee,
                ISNULL(SUM(CASE WHEN xiangmu = '给网红购买产品费' THEN feiyonge ELSE 0 END), 0) AS buy_product_for_influencer_fee,
                ISNULL(SUM(CASE WHEN xiangmu = '达人礼品费' THEN feiyonge ELSE 0 END), 0) AS influencer_gift_fee
            FROM v_TK_FeiYong WITH (NOLOCK)
            WHERE riqi >= '{start_str}' AND riqi <= '{end_str}' AND dian IN ({in_clause})
        """
        rows = bjc.sf_db(sql, single=False) or []
        r = rows[0] if rows else [0, 0, 0, 0, 0]
        return {
            'shuadan_fee': float(r[0] or 0),
            'shouhou_fee': float(r[1] or 0),
            'wanghong_kengwei_fee': float(r[2] or 0),
            'buy_product_for_influencer_fee': float(r[3] or 0),
            'influencer_gift_fee': float(r[4] or 0)
        }

    def _get_influencer_commission_detail(start_str, end_str):
        sql = f"""
            SELECT
                ISNULL(SUM(创作者佣金), 0) AS creator_commission,
                ISNULL(SUM(联盟伙伴佣金), 0) AS partner_commission,
                ISNULL(SUM(广告订单佣金), 0) AS ad_order_commission
            FROM v_TK_JieSuan WITH (NOLOCK)
            WHERE 结算日期 >= '{start_str}' AND 结算日期 <= '{end_str}' AND 店 IN ({in_clause})
        """
        rows = bjc.sf_db(sql, single=False) or []
        r = rows[0] if rows else [0, 0, 0]
        sql_channel = f"""
            SELECT ISNULL(SUM(feiyonge), 0)
            FROM v_TK_FeiYong WITH (NOLOCK)
            WHERE riqi >= '{start_str}' AND riqi <= '{end_str}' AND dian IN ({in_clause}) AND xiangmu = '达人渠道号佣金'
        """
        channel_val = bjc.sf_db(sql_channel, single=True) or 0
        return {
            'creator_commission': float(r[0] or 0),
            'partner_commission': float(r[1] or 0),
            'ad_order_commission': float(r[2] or 0),
            'channel_commission': float(channel_val or 0)
        }

    def _get_storage_return_detail(start_str, end_str):
        sql = f"""
            SELECT
                ISNULL(SUM(CASE WHEN xiangmu = '入库费' THEN feiyonge ELSE 0 END), 0) AS inbound_fee,
                ISNULL(SUM(CASE WHEN xiangmu = '仓储费' THEN feiyonge ELSE 0 END), 0) AS storage_fee,
                ISNULL(SUM(CASE WHEN xiangmu = '退货费' THEN feiyonge ELSE 0 END), 0) AS return_fee
            FROM v_TK_FeiYong WITH (NOLOCK)
            WHERE riqi >= '{start_str}' AND riqi <= '{end_str}' AND dian IN ({in_clause})
        """
        rows = bjc.sf_db(sql, single=False) or []
        r = rows[0] if rows else [0, 0, 0]
        return {
            'inbound_fee': float(r[0] or 0),
            'storage_fee': float(r[1] or 0),
            'return_fee': float(r[2] or 0)
        }

    def _get_product_cost_detail(start_str, end_str):
        sql_platform = f"""
            SELECT ISNULL(SUM(d.xiaoliang * zd.caigoujia), 0) / 6.5
            FROM v_TK_JieSuan AS j WITH (NOLOCK)
            INNER JOIN TK_DingDan AS d WITH (NOLOCK) ON d.danhao = j.单号
            INNER JOIN zidian AS zd WITH (NOLOCK) ON zd.sku = d.sku
            WHERE j.结算日期 >= '{start_str}'
              AND j.结算日期 <= '{end_str}'
              AND j.店 IN ({in_clause})
              AND j.销量 > 0
              AND d.sku IS NOT NULL
        """
        sql_sample = f"""
            SELECT ISNULL(SUM(dd.xiaoliang * zd.caigoujia), 0) / 6.5
            FROM TK_DingDan AS dd WITH (NOLOCK)
            INNER JOIN zidian AS zd WITH (NOLOCK) ON zd.sku = dd.sku
            WHERE dd.shifouyangpin = '是'
              AND zd.dian IN ({in_clause})
              AND dd.fahuoshijian >= '{start_str}'
              AND dd.fahuoshijian <= '{end_str}'
        """
        sql_self_sample = f"""
            SELECT ISNULL(SUM(caigouchengben), 0)
            FROM TK_DingDan_ShouHou WITH (NOLOCK)
            WHERE dingdanleixing = '自发样品'
              AND baoguozhuangtai <> '已作废'
              AND dian IN ({in_clause})
              AND fahuoshijian >= '{start_str}'
              AND fahuoshijian <= '{end_str}'
        """
        sql_aftersales = f"""
            SELECT ISNULL(SUM(caigouchengben), 0)
            FROM TK_DingDan_ShouHou WITH (NOLOCK)
            WHERE dingdanleixing = '售后'
              AND baoguozhuangtai <> '已作废'
              AND dian IN ({in_clause})
              AND fahuoshijian >= '{start_str}'
              AND fahuoshijian <= '{end_str}'
        """
        platform_val = bjc.sf_db(sql_platform, single=True) or 0
        sample_val = bjc.sf_db(sql_sample, single=True) or 0
        self_sample_val = bjc.sf_db(sql_self_sample, single=True) or 0
        aftersales_val = bjc.sf_db(sql_aftersales, single=True) or 0
        return {
            'platform_product_cost': float(platform_val or 0),
            'sample_cost': float(sample_val or 0),
            'self_sample_cost': float(self_sample_val or 0),
            'aftersales_cost': float(aftersales_val or 0)
        }

    shop_list_literal = "N'" + in_clause.replace("'", "''") + "'"
    sql_prev_sp = (
        f"EXEC sp_TK_Dashboard_GetMetrics "
        f"'{prev_start_str}','{prev_end_str}', {shop_list_literal}, {prev_year}, {prev_month}"
    )
    prev_list = bjc.sf_db(sql_prev_sp, single=False)
    prev_raw = prev_list[0] if prev_list else [0]*24
    if len(prev_raw) < 24:
        prev_vals = list(prev_raw) + [0]*(24 - len(prev_raw))
    else:
        prev_vals = list(prev_raw[:24])
    (platform_commission, vat_tax, adjustment_fee, other_platform_fee,
     monthly_sales_prev, wei_cheng_cost, influencer_commission, activity_service_fee,
     tax_fee_prev, storage_return_cost, influencer_video_fee, ad_fee,
     qingdao_wage, shenzhen_wage, qingdao_rent, shenzhen_rent,
     product_cost, tou_cheng_cost,
     order_count, influencer_count, video_count,
     op_mgmt_qd, op_mgmt_sz, rijun_total) = (
        float(prev_vals[0] or 0), float(prev_vals[1] or 0), float(prev_vals[2] or 0), float(prev_vals[3] or 0),
        float(prev_vals[4] or 0), float(prev_vals[5] or 0), float(prev_vals[6] or 0), float(prev_vals[7] or 0),
        float(prev_vals[8] or 0), float(prev_vals[9] or 0), float(prev_vals[10] or 0), float(prev_vals[11] or 0),
        float(prev_vals[12] or 0), float(prev_vals[13] or 0), float(prev_vals[14] or 0), float(prev_vals[15] or 0),
        float(prev_vals[16] or 0), float(prev_vals[17] or 0),
        int(prev_vals[18] or 0), int(prev_vals[19] or 0), int(prev_vals[20] or 0),
        float(prev_vals[21] or 0), float(prev_vals[22] or 0), float(prev_vals[23] or 0)
    )
    vat_fee = (vat_tax or 0) + (tax_fee_prev or 0)

    fixed_costs = {
        'period': {'start': prev_start_str, 'end': prev_end_str},
        'qingdao_wage': qingdao_wage,
        'shenzhen_wage': shenzhen_wage,
        'qingdao_rent': qingdao_rent,
        'shenzhen_rent': shenzhen_rent
    }

    prod_cost_detail_prev = _get_product_cost_detail(prev_start_str, prev_end_str)
    prod_platform_prev = float((prod_cost_detail_prev.get('platform_product_cost') or 0) or 0)
    prod_sample_prev = float((prod_cost_detail_prev.get('sample_cost') or 0) or 0)
    prod_self_sample_prev = float((prod_cost_detail_prev.get('self_sample_cost') or 0) or 0)
    prod_aftersales_prev = float((prod_cost_detail_prev.get('aftersales_cost') or 0) or 0)
    product_cost = (
        prod_platform_prev
        + prod_sample_prev
        + prod_self_sample_prev
        + prod_aftersales_prev
    )

    product_logistics_costs = {
        'period': {'start': prev_start_str, 'end': prev_end_str},
        'product_cost': product_cost,
        'product_cost_detail': prod_cost_detail_prev,
        'tou_cheng_cost': tou_cheng_cost,
        'wei_cheng_cost': wei_cheng_cost,
        'storage_return_cost': storage_return_cost,
        'storage_return_cost_detail': _get_storage_return_detail(prev_start_str, prev_end_str)
    }

    prev_comm_detail = _get_influencer_commission_detail(prev_start_str, prev_end_str)
    prev_channel_commission = float((prev_comm_detail.get('channel_commission') or 0) or 0)
    base_influencer_commission_cost = abs(influencer_commission or 0)
    channel_commission_cost = abs(prev_channel_commission or 0)
    influencer_commission_total = base_influencer_commission_cost + channel_commission_cost
    prev_video_detail = _get_influencer_video_fee_detail(prev_start_str, prev_end_str)
    influencer_video_fee = float((influencer_video_fee or 0) + float((prev_video_detail.get('influencer_gift_fee') or 0) or 0))

    promotional_costs = {
        'period': {'start': prev_start_str, 'end': prev_end_str},
        'influencer_commission': influencer_commission_total,
        'influencer_commission_detail': prev_comm_detail,
        'influencer_count': influencer_count,
        'influencer_video_fee': influencer_video_fee,
        'influencer_video_fee_detail': prev_video_detail,
        'video_count': video_count,
        'activity_service_fee': activity_service_fee,
        'ad_fee': ad_fee
    }

    variable_costs = {
        'period': {'start': prev_start_str, 'end': prev_end_str},
        'platform_commission': platform_commission,
        'vat_fee': vat_fee,
        'adjustment_fee': adjustment_fee,
        'other_platform_fee': other_platform_fee,
        'op_mgmt_qd': op_mgmt_qd,
        'op_mgmt_sz': op_mgmt_sz
    }

    gross_profit = (
        (monthly_sales_prev or 0)
        - abs(influencer_commission_total or 0)
        - abs(influencer_video_fee or 0)
        - abs(ad_fee or 0)
        - abs(activity_service_fee or 0)
        - abs(platform_commission or 0)
        - abs(vat_fee or 0)
        - abs(adjustment_fee or 0)
        - abs(product_cost or 0)
        - abs(tou_cheng_cost or 0)
        - abs(wei_cheng_cost or 0)
        - abs(storage_return_cost or 0)
        - abs(other_platform_fee or 0)
    )

    fixed_total = (
        (op_mgmt_qd or 0) + (op_mgmt_sz or 0)
        + (qingdao_wage or 0) + (shenzhen_wage or 0)
        + (qingdao_rent or 0) + (shenzhen_rent or 0)
    )

    net_profit = gross_profit - fixed_total
    gross_margin_raw = 0.0 if monthly_sales_prev == 0 else (gross_profit / monthly_sales_prev)
    gross_margin = round(gross_margin_raw, 4) if gross_margin_raw != 0 else 0.0

    fixed_total_rounded = (
        round(op_mgmt_qd or 0, 2) + round(op_mgmt_sz or 0, 2)
        + round(qingdao_wage or 0, 2) + round(shenzhen_wage or 0, 2)
        + round(qingdao_rent or 0, 2) + round(shenzhen_rent or 0, 2)
    )
    break_even_revenue = 0.0 if gross_margin == 0 else (fixed_total_rounded / gross_margin)
    profit_target_revenue = 0.0  # 将在获取本月目标净利后重新计算

    business_results = {
        'period': {'start': prev_start_str, 'end': prev_end_str},
        'break_even_revenue': break_even_revenue,
        'order_count': order_count,
        'profit_target_revenue': profit_target_revenue,
        'monthly_sales': monthly_sales_prev,
        'net_profit': net_profit,
        'gross_profit': gross_profit,
        'gross_margin': gross_margin
    }

    sql_targets_sp = f"EXEC sp_TK_Dashboard_GetTargets {curr_year}, {curr_month}, {shop_list_literal}"
    targets_list = bjc.sf_db(sql_targets_sp, single=False)
    tr = list(targets_list[0]) if targets_list else []
    expected_len = 37
    if len(tr) < expected_len:
        tr = tr + [0] * (expected_len - len(tr))
    (t_break_even, t_order_count, t_monthly_sales, t_net_profit, t_gross_profit,
     t_infl_comm, t_infl_count, t_infl_video, t_video_count,
     t_act_service, t_ad_fee, t_plat_comm, t_vat, t_adjust, t_other,
     t_op_qd, t_op_sz, t_prod_cost, t_tou_cheng, t_wei_cheng, t_storage,
     t_wage_qd, t_wage_sz, t_rent_qd, t_rent_sz,
     t_creator_commission, t_partner_commission, t_ad_order_commission, t_channel_commission,
     t_shuadan_fee, t_shouhou_fee, t_kengwei_fee, t_buy_product_fee, t_gift_fee,
     t_inbound_fee, t_storage_fee, t_return_fee) = (
        float(tr[0] or 0), int(tr[1] or 0), float(tr[2] or 0), float(tr[3] or 0), float(tr[4] or 0),
        float(tr[5] or 0), int(tr[6] or 0), float(tr[7] or 0), int(tr[8] or 0),
        float(tr[9] or 0), float(tr[10] or 0), float(tr[11] or 0), float(tr[12] or 0), float(tr[13] or 0), float(tr[14] or 0),
        float(tr[15] or 0), float(tr[16] or 0), float(tr[17] or 0), float(tr[18] or 0), float(tr[19] or 0), float(tr[20] or 0),
        float(tr[21] or 0), float(tr[22] or 0), float(tr[23] or 0), float(tr[24] or 0),
        float(tr[25] or 0), float(tr[26] or 0), float(tr[27] or 0), float(tr[28] or 0),
        float(tr[29] or 0), float(tr[30] or 0), float(tr[31] or 0), float(tr[32] or 0), float(tr[33] or 0),
        float(tr[34] or 0), float(tr[35] or 0), float(tr[36] or 0)
    )

    monthly_targets = {
        'break_even_revenue': float(t_break_even),
        'order_count': int(t_order_count),
        'monthly_sales': float(t_monthly_sales),
        'net_profit': float(t_net_profit),
        'gross_profit': float(t_gross_profit),
        'influencer_commission': float(t_infl_comm),
        'influencer_count': int(t_infl_count),
        'influencer_video_fee': float(t_infl_video),
        'video_count': int(t_video_count),
        'activity_service_fee': float(t_act_service),
        'ad_fee': float(t_ad_fee),
        'platform_commission': float(t_plat_comm),
        'vat_fee': float(t_vat),
        'adjustment_fee': float(t_adjust),
        'other_platform_fee': float(t_other),
        'op_mgmt_qd': float(t_op_qd),
        'op_mgmt_sz': float(t_op_sz),
        'product_cost': float(t_prod_cost),
        'tou_cheng_cost': float(t_tou_cheng),
        'wei_cheng_cost': float(t_wei_cheng),
        'storage_return_cost': float(t_storage),
        'qingdao_wage': float(t_wage_qd),
        'shenzhen_wage': float(t_wage_sz),
        'qingdao_rent': float(t_rent_qd),
        'shenzhen_rent': float(t_rent_sz),
        'influencer_commission_detail': {
            'creator_commission': float(t_creator_commission),
            'partner_commission': float(t_partner_commission),
            'ad_order_commission': float(t_ad_order_commission),
            'channel_commission': float(t_channel_commission)
        },
        'influencer_video_fee_detail': {
            'shuadan_fee': float(t_shuadan_fee),
            'shouhou_fee': float(t_shouhou_fee),
            'wanghong_kengwei_fee': float(t_kengwei_fee),
            'buy_product_for_influencer_fee': float(t_buy_product_fee),
            'influencer_gift_fee': float(t_gift_fee)
        },
        'storage_return_cost_detail': {
            'inbound_fee': float(t_inbound_fee),
            'storage_fee': float(t_storage_fee),
            'return_fee': float(t_return_fee)
        }
    }

    # 使用“本月目标净利”重新计算实时保利额
    target_net_profit = float(t_net_profit or 0)
    profit_target_revenue = 0.0 if gross_margin == 0 else ((fixed_total_rounded + target_net_profit) / gross_margin)
    business_results['profit_target_revenue'] = profit_target_revenue

    sel_start_str = start_dt.strftime('%Y-%m-%d')
    sel_end_str = end_dt.strftime('%Y-%m-%d')
    sel_year = end_dt.year
    sel_month = end_dt.month

    sql_sel_sp = (
        f"EXEC sp_TK_Dashboard_GetMetrics "
        f"'{sel_start_str}','{sel_end_str}', {shop_list_literal}, {sel_year}, {sel_month}"
    )
    sel_list = bjc.sf_db(sql_sel_sp, single=False)
    sel_raw = sel_list[0] if sel_list else [0]*24
    if len(sel_raw) < 24:
        sel_vals = list(sel_raw) + [0]*(24 - len(sel_raw))
    else:
        sel_vals = list(sel_raw[:24])
    yesterday_total = float(sel_raw[24] or 0) if len(sel_raw) > 24 else 0.0

    (plat_comm_sel, vat_tax_sel, adjust_sel, other_fee_sel,
     monthly_sales_sel, wei_cheng_sel, infl_comm_sel, act_service_sel,
     tax_sel, storage_return_sel, infl_video_sel, ad_fee_sel,
     qd_wage_sel, sz_wage_sel, qd_rent_sel, sz_rent_sel,
     prod_cost_sel, tou_cheng_sel,
     order_count_sel, infl_count_sel, video_count_sel,
     op_qd_sel, op_sz_sel, rijun_total_sel) = (
        float(sel_vals[0] or 0), float(sel_vals[1] or 0), float(sel_vals[2] or 0), float(sel_vals[3] or 0),
        float(sel_vals[4] or 0), float(sel_vals[5] or 0), float(sel_vals[6] or 0), float(sel_vals[7] or 0),
        float(sel_vals[8] or 0), float(sel_vals[9] or 0), float(sel_vals[10] or 0), float(sel_vals[11] or 0),
        float(sel_vals[12] or 0), float(sel_vals[13] or 0), float(sel_vals[14] or 0), float(sel_vals[15] or 0),
        float(sel_vals[16] or 0), float(sel_vals[17] or 0),
        int(sel_vals[18] or 0), int(sel_vals[19] or 0), int(sel_vals[20] or 0),
        float(sel_vals[21] or 0), float(sel_vals[22] or 0), float(sel_vals[23] or 0)
    )
    vat_sel_total = (vat_tax_sel or 0) + (tax_sel or 0)

    sel_comm_detail = _get_influencer_commission_detail(sel_start_str, sel_end_str)
    sel_channel_commission = float((sel_comm_detail.get('channel_commission') or 0) or 0)
    base_influencer_commission_cost_sel = abs(infl_comm_sel or 0)
    channel_commission_cost_sel = abs(sel_channel_commission or 0)
    infl_comm_total_sel = base_influencer_commission_cost_sel + channel_commission_cost_sel
    sel_video_detail = _get_influencer_video_fee_detail(sel_start_str, sel_end_str)
    infl_video_sel = float((infl_video_sel or 0) + float((sel_video_detail.get('influencer_gift_fee') or 0) or 0))

    prod_cost_detail_sel = _get_product_cost_detail(sel_start_str, sel_end_str)
    prod_platform_sel = float((prod_cost_detail_sel.get('platform_product_cost') or 0) or 0)
    prod_sample_sel = float((prod_cost_detail_sel.get('sample_cost') or 0) or 0)
    prod_self_sample_sel = float((prod_cost_detail_sel.get('self_sample_cost') or 0) or 0)
    prod_aftersales_sel = float((prod_cost_detail_sel.get('aftersales_cost') or 0) or 0)
    prod_cost_sel = (
        prod_platform_sel
        + prod_sample_sel
        + prod_self_sample_sel
        + prod_aftersales_sel
    )

    gross_profit_sel = (
        (monthly_sales_sel or 0)
        - abs(infl_comm_total_sel or 0)
        - abs(infl_video_sel or 0)
        - abs(ad_fee_sel or 0)
        - abs(act_service_sel or 0)
        - abs(plat_comm_sel or 0)
        - abs(vat_sel_total or 0)
        - abs(adjust_sel or 0)
        - abs(prod_cost_sel or 0)
        - abs(tou_cheng_sel or 0)
        - abs(wei_cheng_sel or 0)
        - abs(storage_return_sel or 0)
        - abs(other_fee_sel or 0)
    )

    fixed_total_sel = (
        (op_qd_sel or 0) + (op_sz_sel or 0)
        + (qd_wage_sel or 0) + (sz_wage_sel or 0)
        + (qd_rent_sel or 0) + (sz_rent_sel or 0)
    )

    net_profit_sel = gross_profit_sel - fixed_total_sel
    gross_margin_sel_raw = 0.0 if monthly_sales_sel == 0 else (gross_profit_sel / monthly_sales_sel)
    gross_margin_sel = round(gross_margin_sel_raw, 4) if gross_margin_sel_raw != 0 else 0.0
    fixed_total_sel_rounded = (
        round(op_qd_sel or 0, 2) + round(op_sz_sel or 0, 2)
        + round(qd_wage_sel or 0, 2) + round(sz_wage_sel or 0, 2)
        + round(qd_rent_sel or 0, 2) + round(sz_rent_sel or 0, 2)
    )
    break_even_sel = 0.0 if gross_margin_sel == 0 else (fixed_total_sel_rounded / gross_margin_sel)
    profit_target_sel = 0.0 if gross_margin_sel == 0 else ((fixed_total_sel_rounded + target_net_profit) / gross_margin_sel)

    actuals = {
        'break_even_revenue': break_even_sel,
        'order_count': order_count_sel,
        'monthly_sales': monthly_sales_sel,
        'net_profit': net_profit_sel,
        'gross_profit': gross_profit_sel,
        'influencer_commission': infl_comm_total_sel,
        'influencer_commission_detail': sel_comm_detail,
        'influencer_count': infl_count_sel,
        'influencer_video_fee': infl_video_sel,
        'influencer_video_fee_detail': sel_video_detail,
        'video_count': video_count_sel,
        'activity_service_fee': act_service_sel,
        'ad_fee': ad_fee_sel,
        'platform_commission': plat_comm_sel,
        'vat_fee': vat_sel_total,
        'adjustment_fee': adjust_sel,
        'other_platform_fee': other_fee_sel,
        'op_mgmt_qd': op_qd_sel,
        'op_mgmt_sz': op_sz_sel,
        'product_cost': prod_cost_sel,
        'tou_cheng_cost': tou_cheng_sel,
        'wei_cheng_cost': wei_cheng_sel,
        'storage_return_cost': storage_return_sel,
        'product_cost_detail': prod_cost_detail_sel,
        'storage_return_cost_detail': _get_storage_return_detail(sel_start_str, sel_end_str),
        'qingdao_wage': qd_wage_sel,
        'shenzhen_wage': sz_wage_sel,
        'qingdao_rent': qd_rent_sel,
        'shenzhen_rent': sz_rent_sel,
        'profit_target_revenue': profit_target_sel
    }
    total_val = yesterday_total

    payload = {
        'success': True,
        'total_sales': total_val,
        'yesterday': yday_str,
        'progress_pct': progress_pct,
        'period_days': period_days,
        'progress_day': progress_day,
        'month_total_days': month_total_days,
        'total_days': month_total_days,
        'today_day': progress_day,
        'fixed_costs': fixed_costs,
        'product_logistics_costs': product_logistics_costs,
        'promotional_costs': promotional_costs,
        'variable_costs': variable_costs,
        'business_results': business_results,
        'monthly_targets': monthly_targets,
        'actuals': actuals
    }
    return payload


def _merge_numeric_dicts(dicts):
    result = {}
    for d in dicts:
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            if isinstance(v, (int, float)):
                result[k] = float(result.get(k, 0) or 0) + float(v or 0)
            elif isinstance(v, dict):
                existing = result.get(k, {})
                if not isinstance(existing, dict):
                    existing = {}
                result[k] = _merge_numeric_dicts([existing, v])
            else:
                if k not in result:
                    result[k] = v
    return result


def _merge_metrics_payloads(payload_list):
    if not payload_list:
        return None
    first = payload_list[0] or {}
    total_sales = 0.0
    for p in payload_list:
        if not isinstance(p, dict):
            continue
        total_sales += float((p.get('total_sales') or 0) or 0)
    merged = dict(first)
    merged['total_sales'] = total_sales
    for k in ['fixed_costs', 'product_logistics_costs', 'promotional_costs', 'variable_costs', 'business_results', 'monthly_targets', 'actuals']:
        dicts = []
        for p in payload_list:
            if isinstance(p, dict):
                dicts.append(p.get(k) or {})
        merged[k] = _merge_numeric_dicts(dicts)
    return merged


def _refresh_default_cache_once():
    today = date.today()
    start_dt = date(today.year, today.month, 1)
    end_dt = today
    week_start_dt = today - timedelta(days=6)
    week_end_dt = today
    payload = _compute_metrics_payload(start_dt, end_dt, [DEFAULT_SHOP_NAME], 0.0)
    global _default_cached_payload, _default_cached_exp, _precomputed_shop_payloads, _precomputed_week_shop_payloads
    _default_cached_payload = payload
    _default_cached_exp = time.time() + DEFAULT_CACHE_REFRESH_SEC
    shops_rows = bjc.sf_db("SELECT DISTINCT 店 FROM v_TK_JieSuan") or []
    shops = []
    if isinstance(shops_rows, list):
        for r in shops_rows:
            s = str(r).strip()
            if s:
                shops.append(s)
    shops = sorted(list(set(shops)))
    new_map = {}
    new_week_map = {}
    for s in shops:
        try:
            p = _compute_metrics_payload(start_dt, end_dt, [s], 0.0)
            new_map[s] = p
        except Exception:
            pass
        try:
            p_week = _compute_metrics_payload(week_start_dt, week_end_dt, [s], 0.0)
            new_week_map[s] = p_week
        except Exception:
            pass
    if new_map:
        payloads = list(new_map.values())
        try:
            p_all = _compute_metrics_payload(start_dt, end_dt, shops, 0.0)
        except Exception:
            p_all = _merge_metrics_payloads(payloads)
        if p_all:
            new_map['ALL'] = p_all
    if new_week_map:
        payloads_week = list(new_week_map.values())
        try:
            p_week_all = _compute_metrics_payload(week_start_dt, week_end_dt, shops, 0.0)
        except Exception:
            p_week_all = _merge_metrics_payloads(payloads_week)
        if p_week_all:
            new_week_map['ALL'] = p_week_all
    _precomputed_shop_payloads = new_map
    _precomputed_week_shop_payloads = new_week_map

def _default_cache_worker():
    while True:
        try:
            _refresh_default_cache_once()
        except Exception:
            pass
        time.sleep(DEFAULT_CACHE_REFRESH_SEC)

def _ensure_default_cache_thread():
    global _default_thread_started
    if _default_thread_started:
        return
    t = threading.Thread(target=_default_cache_worker, daemon=True)
    t.start()
    _default_thread_started = True
_ensure_default_cache_thread()


@tk_dashboard_bp.route('/tk/dashboard')
@require_permission('tk_total_dashboard')
def tk_dashboard_page():
    if not is_admin_user():
        return redirect(url_for('dashboard'))
    if (_default_cached_payload is None) or (time.time() >= _default_cached_exp):
        try:
            _refresh_default_cache_once()
        except Exception:
            pass
    shop_options = []
    for key, payload in (_precomputed_shop_payloads or {}).items():
        if key == 'ALL':
            label = '全部店铺'
        else:
            label = f'店铺 {key}'
        shop_options.append({'key': key, 'label': label})
    shop_options = sorted(shop_options, key=lambda x: (0 if x['key'] == 'ALL' else 1, x['label']))
    return render_template(
        'tk_total_dashboard.html',
        default_payload=_default_cached_payload,
        default_shop_name=DEFAULT_SHOP_NAME,
        precomputed_shops=shop_options,
        precomputed_shop_payloads=_precomputed_shop_payloads,
        precomputed_week_shop_payloads=_precomputed_week_shop_payloads,
        page_title='TK整体看板',
        page_desc='选择日期范围和店铺，查看昨日实时结算销售额（USD）与时间进度',
        fixed_shop=None,
    )


@tk_dashboard_bp.route('/tk/dashboard_project')
@require_permission('tk_total_dashboard')
def tk_dashboard_project_page():
    if not is_partial_admin_user():
        return redirect(url_for('dashboard'))
    if (_default_cached_payload is None) or (time.time() >= _default_cached_exp):
        try:
            _refresh_default_cache_once()
        except Exception:
            pass
    shop_options = []
    for key, payload in (_precomputed_shop_payloads or {}).items():
        if key == 'ALL':
            label = '全部店铺'
        else:
            label = f'店铺 {key}'
        shop_options.append({'key': key, 'label': label})
    shop_options = sorted(shop_options, key=lambda x: (0 if x['key'] == 'ALL' else 1, x['label']))
    return render_template(
        'tk_total_dashboard.html',
        default_payload=_default_cached_payload,
        default_shop_name=DEFAULT_SHOP_NAME,
        precomputed_shops=shop_options,
        precomputed_shop_payloads=_precomputed_shop_payloads,
        precomputed_week_shop_payloads=_precomputed_week_shop_payloads,
        page_title='TK项目组部分权限看板',
        page_desc='和TK整体看板一样可查看所有店铺，但展示字段与82号店看板一致',
        fixed_shop=None,
        restrict_like_82=True,
    )


@tk_dashboard_bp.route('/tk/dashboard_sz')
@require_permission('tk_total_dashboard')
def tk_dashboard_sz_page():
    if (_default_cached_payload is None) or (time.time() >= _default_cached_exp):
        try:
            _refresh_default_cache_once()
        except Exception:
            pass
    shop_options = []
    for key, payload in (_precomputed_shop_payloads or {}).items():
        if key == 'ALL':
            label = '全部店铺'
        else:
            label = f'店铺 {key}'
        shop_options.append({'key': key, 'label': label})
    shop_options = sorted(shop_options, key=lambda x: (0 if x['key'] == 'ALL' else 1, x['label']))
    return render_template(
        'tk_total_dashboard.html',
        default_payload=_default_cached_payload,
        default_shop_name=DEFAULT_SHOP_NAME,
        precomputed_shops=shop_options,
        precomputed_shop_payloads=_precomputed_shop_payloads,
        precomputed_week_shop_payloads=_precomputed_week_shop_payloads,
        page_title='深圳看板',
        page_desc='查看与TK整体看板一致的深圳看板内容',
        fixed_shop=None,
    )


@tk_dashboard_bp.route('/tk/dashboard_82')
def tk_dashboard_82_page():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    if not is_dashboard_82_user():
        return redirect(url_for('dashboard'))
    if (_default_cached_payload is None) or (time.time() >= _default_cached_exp):
        try:
            _refresh_default_cache_once()
        except Exception:
            pass
    payload_82 = None
    if isinstance(_precomputed_shop_payloads, dict):
        payload_82 = _precomputed_shop_payloads.get('82')
    payload_82_week = None
    if isinstance(_precomputed_week_shop_payloads, dict):
        payload_82_week = _precomputed_week_shop_payloads.get('82')
    if not payload_82:
        today = date.today()
        start_dt = date(today.year, today.month, 1)
        end_dt = today
        payload_82 = _compute_metrics_payload(start_dt, end_dt, ['82'], 0.0)
    if not payload_82_week:
        today = date.today()
        payload_82_week = _compute_metrics_payload(today - timedelta(days=6), today, ['82'], 0.0)
    shop_options = [{'key': '82', 'label': '店铺 82'}]
    return render_template(
        'tk_total_dashboard.html',
        default_payload=payload_82,
        default_shop_name='82',
        precomputed_shops=shop_options,
        precomputed_shop_payloads={'82': payload_82},
        precomputed_week_shop_payloads={'82': payload_82_week},
        page_title='82号店看板',
        page_desc='选择日期范围，查看 82 号店昨日实时结算销售额（USD）与时间进度',
        fixed_shop='82',
    )


@tk_dashboard_bp.route('/tk/dashboard_88')
def tk_dashboard_88_page():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    if not is_dashboard_88_user():
        return redirect(url_for('dashboard'))
    if (_default_cached_payload is None) or (time.time() >= _default_cached_exp):
        try:
            _refresh_default_cache_once()
        except Exception:
            pass
    payload_88 = None
    if isinstance(_precomputed_shop_payloads, dict):
        payload_88 = _precomputed_shop_payloads.get('88')
    payload_88_week = None
    if isinstance(_precomputed_week_shop_payloads, dict):
        payload_88_week = _precomputed_week_shop_payloads.get('88')
    if not payload_88:
        today = date.today()
        start_dt = date(today.year, today.month, 1)
        end_dt = today
        payload_88 = _compute_metrics_payload(start_dt, end_dt, ['88'], 0.0)
    if not payload_88_week:
        today = date.today()
        payload_88_week = _compute_metrics_payload(today - timedelta(days=6), today, ['88'], 0.0)
    shop_options = [{'key': '88', 'label': '店铺 88'}]
    return render_template(
        'tk_total_dashboard.html',
        default_payload=payload_88,
        default_shop_name='88',
        precomputed_shops=shop_options,
        precomputed_shop_payloads={'88': payload_88},
        precomputed_week_shop_payloads={'88': payload_88_week},
        page_title='88号店看板',
        page_desc='选择日期范围，查看 88 号店昨日实时结算销售额（USD）与时间进度',
        fixed_shop='88',
    )


@tk_dashboard_bp.route('/tk/dashboard_90')
def tk_dashboard_90_page():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    if not is_dashboard_90_user():
        return redirect(url_for('dashboard'))
    if (_default_cached_payload is None) or (time.time() >= _default_cached_exp):
        try:
            _refresh_default_cache_once()
        except Exception:
            pass
    payload_90 = None
    if isinstance(_precomputed_shop_payloads, dict):
        payload_90 = _precomputed_shop_payloads.get('90')
    payload_90_week = None
    if isinstance(_precomputed_week_shop_payloads, dict):
        payload_90_week = _precomputed_week_shop_payloads.get('90')
    if not payload_90:
        today = date.today()
        start_dt = date(today.year, today.month, 1)
        end_dt = today
        payload_90 = _compute_metrics_payload(start_dt, end_dt, ['90'], 0.0)
    if not payload_90_week:
        today = date.today()
        payload_90_week = _compute_metrics_payload(today - timedelta(days=6), today, ['90'], 0.0)
    shop_options = [{'key': '90', 'label': '店铺 90'}]
    return render_template(
        'tk_total_dashboard.html',
        default_payload=payload_90,
        default_shop_name='90',
        precomputed_shops=shop_options,
        precomputed_shop_payloads={'90': payload_90},
        precomputed_week_shop_payloads={'90': payload_90_week},
        page_title='90号店看板',
        page_desc='选择日期范围，查看 90 号店昨日实时结算销售额（USD）与时间进度',
        fixed_shop='90',
    )


@tk_dashboard_bp.route('/tk/metrics_82', methods=['POST'])
def tk_metrics_82():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    if not is_dashboard_82_user():
        return jsonify({'success': False, 'message': '权限不足'}), 403
    try:
        data = request.get_json() or {}
        start_date_str = (data.get('start_date') or '').strip()
        end_date_str = (data.get('end_date') or '').strip()

        if not start_date_str or not end_date_str:
            return jsonify({'success': False, 'message': '请选择开始日期和结束日期'})

        try:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            return jsonify({'success': False, 'message': '日期格式错误，应为YYYY-MM-DD'})

        target_net_profit_param = float((data.get('target_net_profit') or 0) or 0)
        cache_key = (start_date_str, end_date_str, '82', target_net_profit_param)
        now_ts = time.time()
        cached = _metrics_cache.get(cache_key)
        if cached and cached[0] > now_ts:
            return jsonify(cached[1])

        payload = _compute_metrics_payload(start_dt, end_dt, ['82'], target_net_profit_param)
        _metrics_cache[cache_key] = (now_ts + METRICS_CACHE_TTL, payload)
        return jsonify(payload)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@tk_dashboard_bp.route('/tk/metrics_88', methods=['POST'])
def tk_metrics_88():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    if not is_dashboard_88_user():
        return jsonify({'success': False, 'message': '权限不足'}), 403
    try:
        data = request.get_json() or {}
        start_date_str = (data.get('start_date') or '').strip()
        end_date_str = (data.get('end_date') or '').strip()

        if not start_date_str or not end_date_str:
            return jsonify({'success': False, 'message': '请选择开始日期和结束日期'})

        try:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            return jsonify({'success': False, 'message': '日期格式错误，应为YYYY-MM-DD'})

        target_net_profit_param = float((data.get('target_net_profit') or 0) or 0)
        cache_key = (start_date_str, end_date_str, '88', target_net_profit_param)
        now_ts = time.time()
        cached = _metrics_cache.get(cache_key)
        if cached and cached[0] > now_ts:
            return jsonify(cached[1])

        payload = _compute_metrics_payload(start_dt, end_dt, ['88'], target_net_profit_param)
        _metrics_cache[cache_key] = (now_ts + METRICS_CACHE_TTL, payload)
        return jsonify(payload)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@tk_dashboard_bp.route('/tk/metrics_90', methods=['POST'])
def tk_metrics_90():
    user_id = session.get('feishu_user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '未登录'}), 401
    if not is_dashboard_90_user():
        return jsonify({'success': False, 'message': '权限不足'}), 403
    try:
        data = request.get_json() or {}
        start_date_str = (data.get('start_date') or '').strip()
        end_date_str = (data.get('end_date') or '').strip()

        if not start_date_str or not end_date_str:
            return jsonify({'success': False, 'message': '请选择开始日期和结束日期'})

        try:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            return jsonify({'success': False, 'message': '日期格式错误，应为YYYY-MM-DD'})

        target_net_profit_param = float((data.get('target_net_profit') or 0) or 0)
        cache_key = (start_date_str, end_date_str, '90', target_net_profit_param)
        now_ts = time.time()
        cached = _metrics_cache.get(cache_key)
        if cached and cached[0] > now_ts:
            return jsonify(cached[1])

        payload = _compute_metrics_payload(start_dt, end_dt, ['90'], target_net_profit_param)
        _metrics_cache[cache_key] = (now_ts + METRICS_CACHE_TTL, payload)
        return jsonify(payload)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


def _normalize_ratio_month(month_text):
    now = datetime.now()
    default_month = f"{now.year:04d}-{now.month:02d}"
    if not month_text:
        return now.year, now.month, default_month
    try:
        dt = datetime.strptime(month_text, '%Y-%m')
        return dt.year, dt.month, dt.strftime('%Y-%m')
    except Exception:
        return now.year, now.month, default_month


@tk_dashboard_bp.route('/tk/gmv_ratio_card')
@require_permission('tk_project_group')
def tk_gmv_ratio_page():
    user_id = session.get('feishu_user_id')
    user_name = session.get('feishu_user_name', '用户')
    now = datetime.now()
    return render_template(
        'tk_gmv_ratio_card.html',
        user_name=user_name,
        user_id=user_id,
        default_month=f"{now.year:04d}-{now.month:02d}",
        default_shop='86'
    )


@tk_dashboard_bp.route('/api/tk/gmv_ratio/shops', methods=['GET'])
@require_permission('tk_project_group')
def tk_gmv_ratio_shops():
    try:
        rows = bjc.sf_db("SELECT DISTINCT CAST(dian AS NVARCHAR(50)) AS dian FROM v_tk_dingdan WHERE dian IS NOT NULL") or []
        shops = []
        for row in rows:
            if isinstance(row, (list, tuple)):
                val = row[0] if row else ''
            else:
                val = row
            s = str(val or '').strip()
            if s:
                shops.append(s)
        shops = sorted(set(shops), key=lambda x: (0, int(x)) if x.isdigit() else (1, x))
        return jsonify({'success': True, 'shops': shops})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'shops': []})


@tk_dashboard_bp.route('/api/tk/gmv_ratio', methods=['GET'])
@require_permission('tk_project_group')
def tk_gmv_ratio_data():
    try:
        month_text = (request.args.get('month') or '').strip()
        shop = (request.args.get('shop') or '86').strip() or '86'
        year, month, normalized_month = _normalize_ratio_month(month_text)

        shop_condition_bd = ''
        shop_condition_d = ''
        if shop.upper() != 'ALL':
            safe_shop = shop.replace("'", "''")
            shop_condition_bd = f" AND CAST(dian AS NVARCHAR(50)) = '{safe_shop}'"
            shop_condition_d = f" AND CAST(d.dian AS NVARCHAR(50)) = '{safe_shop}'"

        sql = f"""
WITH bd_agg AS (
    SELECT
        DATEFROMPARTS(YEAR(dinggoushijian), MONTH(dinggoushijian), 1) AS 月份,
        CASE
            WHEN bd IN ('李欣纳','杨薛') THEN '视频产出'
            ELSE '达人产出'
        END AS 项目,
        SUM(xiaoshoue) AS 金额
    FROM V_tk_bddingdan
    WHERE YEAR(dinggoushijian) = {year}
      AND MONTH(dinggoushijian) = {month}
      {shop_condition_bd}
    GROUP BY
        DATEFROMPARTS(YEAR(dinggoushijian), MONTH(dinggoushijian), 1),
        CASE
            WHEN bd IN ('李欣纳','杨薛') THEN '视频产出'
            ELSE '达人产出'
        END
),
other_agg AS (
    SELECT
        DATEFROMPARTS(YEAR(d.dinggoushijian), MONTH(d.dinggoushijian), 1) AS 月份,
        '商品卡' AS 项目,
        SUM(d.xiaoshoue) AS 金额
    FROM V_tk_dingdan d
    LEFT JOIN V_tk_bddingdan b
        ON b.danhao = d.danhao
       AND b.dian = d.dian
    WHERE YEAR(d.dinggoushijian) = {year}
      AND MONTH(d.dinggoushijian) = {month}
      {shop_condition_d}
      AND b.danhao IS NULL
    GROUP BY DATEFROMPARTS(YEAR(d.dinggoushijian), MONTH(d.dinggoushijian), 1)
),
t AS (
    SELECT * FROM bd_agg
    UNION ALL
    SELECT * FROM other_agg
)
SELECT
    项目,
    CAST(ROUND(金额, 2) AS FLOAT) AS 金额,
    CAST(ROUND(金额 * 100.0 / NULLIF(SUM(金额) OVER (), 0), 2) AS FLOAT) AS 占比百分比
FROM t
ORDER BY 项目
"""
        rows = bjc.sf_db(sql, single=False) or []
        ordered_projects = ['视频产出', '商品卡', '达人产出']
        result_map = {k: {'项目': k, '金额': 0.0, '占比百分比': 0.0} for k in ordered_projects}

        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue
            project = str(row[0] or '').strip()
            if project == '其他产出':
                project = '商品卡'
            if project not in result_map:
                continue
            amount_val = float(row[1] or 0)
            ratio_val = float(row[2] or 0)
            result_map[project] = {'项目': project, '金额': round(amount_val, 2), '占比百分比': round(ratio_val, 2)}

        result_data = [result_map[p] for p in ordered_projects]
        total_amount = round(sum(item['金额'] for item in result_data), 2)

        return jsonify({
            'success': True,
            'month': normalized_month,
            'shop': shop,
            'total_amount': total_amount,
            'data': result_data
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'data': []}), 500


@tk_dashboard_bp.route('/tk/shops', methods=['GET'])
@require_permission('tk_total_dashboard')
def tk_shops():
    try:
        rows = bjc.sf_db("SELECT DISTINCT 店 FROM v_TK_JieSuan") or []
        shops = []
        if isinstance(rows, list):
            for r in rows:
                s = str(r).strip()
                if s:
                    shops.append(s)
        shops = sorted(list(set(shops)))
        return jsonify({'success': True, 'shops': shops})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@tk_dashboard_bp.route('/tk/metrics', methods=['POST'])
@require_permission('tk_total_dashboard')
def tk_metrics():
    if not (is_admin_user() or is_partial_admin_user()):
        return jsonify({'success': False, 'message': '权限不足'}), 403
    try:
        data = request.get_json() or {}
        start_date_str = (data.get('start_date') or '').strip()
        end_date_str = (data.get('end_date') or '').strip()
        shops = data.get('shops') or []

        if not start_date_str or not end_date_str:
            return jsonify({'success': False, 'message': '请选择开始日期和结束日期'})
        if not shops:
            rows = bjc.sf_db("SELECT DISTINCT 店 FROM v_TK_JieSuan") or []
            shops = []
            if isinstance(rows, list):
                for r in rows:
                    s = str(r).strip()
                    if s:
                        shops.append(s)

        try:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            return jsonify({'success': False, 'message': '日期格式错误，应为YYYY-MM-DD'})

        safe_shops = [str(s).replace("'", "''") for s in shops]
        in_clause = ','.join([f"'{s}'" for s in safe_shops])
        yday = date.today() - timedelta(days=1)
        yday_str = yday.strftime('%Y-%m-%d')
        total_val = 0.0

        # 缓存命中检查（相同开始/结束/店铺/目标利润 在 TTL 内直接返回）
        target_net_profit_param = float((data.get('target_net_profit') or 0) or 0)
        shops_key = '|'.join(sorted([str(s) for s in shops]))
        cache_key = (start_date_str, end_date_str, shops_key, target_net_profit_param)
        now_ts = time.time()
        cached = _metrics_cache.get(cache_key)
        if cached and cached[0] > now_ts:
            return jsonify(cached[1])

        today = date.today()
        period_days = (end_dt - start_dt).days + 1
        month_total_days = monthrange(end_dt.year, end_dt.month)[1]
        progress_day = max(0, min(month_total_days, (today - start_dt).days))
        progress_pct = round(0.0 if month_total_days <= 0 else (progress_day / month_total_days) * 100, 2)

        curr_year = end_dt.year
        curr_month = end_dt.month

        prev_month = end_dt.month - 1
        prev_year = end_dt.year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        prev_start = date(prev_year, prev_month, 1)
        prev_last_day = monthrange(prev_year, prev_month)[1]
        prev_end = date(prev_year, prev_month, prev_last_day)

        prev_start_str = prev_start.strftime('%Y-%m-%d')
        prev_end_str = prev_end.strftime('%Y-%m-%d')

        def fetch_batch_results(sql_list, as_int_indices=None):
            if not sql_list: return []
            combined_sql = "SELECT " + ",".join([f"({s})" for s in sql_list])
            try:
                row = bjc.sf_db(combined_sql, single=False)
                if not row: return [0] * len(sql_list)
                vals = row[0]
                results = []
                for i, v in enumerate(vals):
                    try:
                        if as_int_indices and i in as_int_indices:
                            results.append(int(v or 0))
                        else:
                            results.append(float(v or 0))
                    except:
                        results.append(0 if as_int_indices and i in as_int_indices else 0.0)
                return results
            except Exception:
                return [0] * len(sql_list)

        def _get_influencer_video_fee_detail(start_str, end_str):
            sql = f"""
                SELECT
                    ISNULL(SUM(CASE WHEN xiangmu = '刷单费' THEN feiyonge ELSE 0 END), 0) AS shuadan_fee,
                    ISNULL(SUM(CASE WHEN xiangmu = '售后' THEN feiyonge ELSE 0 END), 0) AS shouhou_fee,
                    ISNULL(SUM(CASE WHEN xiangmu = '网红坑位费' THEN feiyonge ELSE 0 END), 0) AS wanghong_kengwei_fee,
                    ISNULL(SUM(CASE WHEN xiangmu = '给网红购买产品费' THEN feiyonge ELSE 0 END), 0) AS buy_product_for_influencer_fee,
                    ISNULL(SUM(CASE WHEN xiangmu = '达人礼品费' THEN feiyonge ELSE 0 END), 0) AS influencer_gift_fee
                FROM v_TK_FeiYong WITH (NOLOCK)
                WHERE riqi >= '{start_str}' AND riqi <= '{end_str}' AND dian IN ({in_clause})
            """
            rows = bjc.sf_db(sql, single=False) or []
            r = rows[0] if rows else [0, 0, 0, 0, 0]
            return {
                'shuadan_fee': float(r[0] or 0),
                'shouhou_fee': float(r[1] or 0),
                'wanghong_kengwei_fee': float(r[2] or 0),
                'buy_product_for_influencer_fee': float(r[3] or 0),
                'influencer_gift_fee': float(r[4] or 0)
            }

        def _get_influencer_commission_detail(start_str, end_str):
            sql = f"""
                SELECT
                    ISNULL(SUM(创作者佣金), 0) AS creator_commission,
                    ISNULL(SUM(联盟伙伴佣金), 0) AS partner_commission,
                    ISNULL(SUM(广告订单佣金), 0) AS ad_order_commission
                FROM v_TK_JieSuan WITH (NOLOCK)
                WHERE 结算日期 >= '{start_str}' AND 结算日期 <= '{end_str}' AND 店 IN ({in_clause})
            """
            rows = bjc.sf_db(sql, single=False) or []
            r = rows[0] if rows else [0, 0, 0]
            sql_channel = f"""
                SELECT ISNULL(SUM(feiyonge), 0)
                FROM v_TK_FeiYong WITH (NOLOCK)
                WHERE riqi >= '{start_str}' AND riqi <= '{end_str}' AND dian IN ({in_clause}) AND xiangmu = '达人渠道号佣金'
            """
            channel_val = bjc.sf_db(sql_channel, single=True) or 0
            return {
                'creator_commission': float(r[0] or 0),
                'partner_commission': float(r[1] or 0),
                'ad_order_commission': float(r[2] or 0),
                'channel_commission': float(channel_val or 0)
            }

        def _get_storage_return_detail(start_str, end_str):
            sql = f"""
                SELECT
                    ISNULL(SUM(CASE WHEN xiangmu = '入库费' THEN feiyonge ELSE 0 END), 0) AS inbound_fee,
                    ISNULL(SUM(CASE WHEN xiangmu = '仓储费' THEN feiyonge ELSE 0 END), 0) AS storage_fee,
                    ISNULL(SUM(CASE WHEN xiangmu = '退货费' THEN feiyonge ELSE 0 END), 0) AS return_fee
                FROM v_TK_FeiYong WITH (NOLOCK)
                WHERE riqi >= '{start_str}' AND riqi <= '{end_str}' AND dian IN ({in_clause})
            """
            rows = bjc.sf_db(sql, single=False) or []
            r = rows[0] if rows else [0, 0, 0]
            return {
                'inbound_fee': float(r[0] or 0),
                'storage_fee': float(r[1] or 0),
                'return_fee': float(r[2] or 0)
            }

        def _get_product_cost_detail(start_str, end_str):
            sql_platform = f"""
                SELECT ISNULL(SUM(d.xiaoliang * zd.caigoujia), 0) / 6.5
                FROM v_TK_JieSuan AS j WITH (NOLOCK)
                INNER JOIN TK_DingDan AS d WITH (NOLOCK) ON d.danhao = j.单号
                INNER JOIN zidian AS zd WITH (NOLOCK) ON zd.sku = d.sku
                WHERE j.结算日期 >= '{start_str}'
                  AND j.结算日期 <= '{end_str}'
                  AND j.店 IN ({in_clause})
                  AND j.销量 > 0
                  AND d.sku IS NOT NULL
            """
            sql_sample = f"""
                SELECT ISNULL(SUM(dd.xiaoliang * zd.caigoujia), 0) / 6.5
                FROM TK_DingDan AS dd WITH (NOLOCK)
                INNER JOIN zidian AS zd WITH (NOLOCK) ON zd.sku = dd.sku
                WHERE dd.shifouyangpin = '是'
                  AND zd.dian IN ({in_clause})
                  AND dd.fahuoshijian >= '{start_str}'
                  AND dd.fahuoshijian <= '{end_str}'
            """
            sql_self_sample = f"""
                SELECT ISNULL(SUM(caigouchengben), 0)
                FROM TK_DingDan_ShouHou WITH (NOLOCK)
                WHERE dingdanleixing = '自发样品'
                  AND baoguozhuangtai <> '已作废'
                  AND dian IN ({in_clause})
                  AND fahuoshijian >= '{start_str}'
                  AND fahuoshijian <= '{end_str}'
            """
            sql_aftersales = f"""
                SELECT ISNULL(SUM(caigouchengben), 0)
                FROM TK_DingDan_ShouHou WITH (NOLOCK)
                WHERE dingdanleixing = '售后'
                  AND baoguozhuangtai <> '已作废'
                  AND dian IN ({in_clause})
                  AND fahuoshijian >= '{start_str}'
                  AND fahuoshijian <= '{end_str}'
            """
            platform_val = bjc.sf_db(sql_platform, single=True) or 0
            sample_val = bjc.sf_db(sql_sample, single=True) or 0
            self_sample_val = bjc.sf_db(sql_self_sample, single=True) or 0
            aftersales_val = bjc.sf_db(sql_aftersales, single=True) or 0
            return {
                'platform_product_cost': float(platform_val or 0),
                'sample_cost': float(sample_val or 0),
                'self_sample_cost': float(self_sample_val or 0),
                'aftersales_cost': float(aftersales_val or 0)
            }

        prev_vals_sum = [0.0]*24
        for s in shops:
            s_lit = "N'" + str(s).replace("'", "''") + "'"
            sql_prev_sp = (
                f"EXEC sp_TK_Dashboard_GetMetrics "
                f"'{prev_start_str}','{prev_end_str}', {s_lit}, {prev_year}, {prev_month}"
            )
            prev_list = bjc.sf_db(sql_prev_sp, single=False)
            prev_raw = prev_list[0] if prev_list else [0]*24
            if len(prev_raw) < 24:
                curr_vals = list(prev_raw) + [0]*(24 - len(prev_raw))
            else:
                curr_vals = list(prev_raw[:24])
            prev_vals_sum = [float(prev_vals_sum[i]) + float(curr_vals[i] or 0) for i in range(24)]
        prev_vals = prev_vals_sum
        (platform_commission, vat_tax, adjustment_fee, other_platform_fee,
         monthly_sales_prev, wei_cheng_cost, influencer_commission, activity_service_fee,
         tax_fee_prev, storage_return_cost, influencer_video_fee, ad_fee,
         qingdao_wage, shenzhen_wage, qingdao_rent, shenzhen_rent,
         product_cost, tou_cheng_cost,
         order_count, influencer_count, video_count,
         op_mgmt_qd, op_mgmt_sz, rijun_total) = (
            float(prev_vals[0] or 0), float(prev_vals[1] or 0), float(prev_vals[2] or 0), float(prev_vals[3] or 0),
            float(prev_vals[4] or 0), float(prev_vals[5] or 0), float(prev_vals[6] or 0), float(prev_vals[7] or 0),
            float(prev_vals[8] or 0), float(prev_vals[9] or 0), float(prev_vals[10] or 0), float(prev_vals[11] or 0),
            float(prev_vals[12] or 0), float(prev_vals[13] or 0), float(prev_vals[14] or 0), float(prev_vals[15] or 0),
            float(prev_vals[16] or 0), float(prev_vals[17] or 0),
            int(prev_vals[18] or 0), int(prev_vals[19] or 0), int(prev_vals[20] or 0),
            float(prev_vals[21] or 0), float(prev_vals[22] or 0), float(prev_vals[23] or 0)
        )
        vat_fee = (vat_tax or 0) + (tax_fee_prev or 0)

        # Construct result dictionaries
        fixed_costs = {
            'period': {'start': prev_start_str, 'end': prev_end_str},
            'qingdao_wage': qingdao_wage,
            'shenzhen_wage': shenzhen_wage,
            'qingdao_rent': qingdao_rent,
            'shenzhen_rent': shenzhen_rent
        }

        prod_cost_detail_prev = _get_product_cost_detail(prev_start_str, prev_end_str)
        prod_platform_prev = float((prod_cost_detail_prev.get('platform_product_cost') or 0) or 0)
        prod_sample_prev = float((prod_cost_detail_prev.get('sample_cost') or 0) or 0)
        prod_self_sample_prev = float((prod_cost_detail_prev.get('self_sample_cost') or 0) or 0)
        prod_aftersales_prev = float((prod_cost_detail_prev.get('aftersales_cost') or 0) or 0)
        product_cost = (
            prod_platform_prev
            + prod_sample_prev
            + prod_self_sample_prev
            + prod_aftersales_prev
        )

        product_logistics_costs = {
            'period': {'start': prev_start_str, 'end': prev_end_str},
            'product_cost': product_cost,
            'product_cost_detail': prod_cost_detail_prev,
            'tou_cheng_cost': tou_cheng_cost,
            'wei_cheng_cost': wei_cheng_cost,
            'storage_return_cost': storage_return_cost,
            'storage_return_cost_detail': _get_storage_return_detail(prev_start_str, prev_end_str)
        }

        prev_comm_detail = _get_influencer_commission_detail(prev_start_str, prev_end_str)
        prev_channel_commission = float((prev_comm_detail.get('channel_commission') or 0) or 0)
        base_influencer_commission_cost = abs(influencer_commission or 0)
        channel_commission_cost = abs(prev_channel_commission or 0)
        influencer_commission_total = base_influencer_commission_cost + channel_commission_cost
        prev_video_detail = _get_influencer_video_fee_detail(prev_start_str, prev_end_str)
        influencer_video_fee = float((influencer_video_fee or 0) + float((prev_video_detail.get('influencer_gift_fee') or 0) or 0))

        promotional_costs = {
            'period': {'start': prev_start_str, 'end': prev_end_str},
            'influencer_commission': influencer_commission_total,
            'influencer_commission_detail': prev_comm_detail,
            'influencer_count': influencer_count,
            'influencer_video_fee': influencer_video_fee,
            'influencer_video_fee_detail': prev_video_detail,
            'video_count': video_count,
            'activity_service_fee': activity_service_fee,
            'ad_fee': ad_fee
        }

        variable_costs = {
            'period': {'start': prev_start_str, 'end': prev_end_str},
            'platform_commission': platform_commission,
            'vat_fee': vat_fee,
            'adjustment_fee': adjustment_fee,
            'other_platform_fee': other_platform_fee,
            'op_mgmt_qd': op_mgmt_qd,
            'op_mgmt_sz': op_mgmt_sz
        }

        gross_profit = (
            (monthly_sales_prev or 0)
            - abs(influencer_commission_total or 0)
            - abs(influencer_video_fee or 0)
            - abs(ad_fee or 0)
            - abs(activity_service_fee or 0)
            - abs(platform_commission or 0)
            - abs(vat_fee or 0)
            - abs(adjustment_fee or 0)
            - abs(product_cost or 0)
            - abs(tou_cheng_cost or 0)
            - abs(wei_cheng_cost or 0)
            - abs(storage_return_cost or 0)
            - abs(other_platform_fee or 0)
        )

        fixed_total = (
            (op_mgmt_qd or 0) + (op_mgmt_sz or 0)
            + (qingdao_wage or 0) + (shenzhen_wage or 0)
            + (qingdao_rent or 0) + (shenzhen_rent or 0)
        )

        net_profit = gross_profit - fixed_total
        gross_margin_raw = 0.0 if monthly_sales_prev == 0 else (gross_profit / monthly_sales_prev)
        gross_margin = round(gross_margin_raw, 4) if gross_margin_raw != 0 else 0.0

        fixed_total_rounded = (
            round(op_mgmt_qd or 0, 2) + round(op_mgmt_sz or 0, 2)
            + round(qingdao_wage or 0, 2) + round(shenzhen_wage or 0, 2)
            + round(qingdao_rent or 0, 2) + round(shenzhen_rent or 0, 2)
        )
        break_even_revenue = 0.0 if gross_margin == 0 else (fixed_total_rounded / gross_margin)
        profit_target_revenue = 0.0  # 将在获取本月目标净利后重新计算

        business_results = {
            'period': {'start': prev_start_str, 'end': prev_end_str},
            'break_even_revenue': break_even_revenue,
            'order_count': order_count,
            'profit_target_revenue': profit_target_revenue,
            'monthly_sales': monthly_sales_prev,
            'net_profit': net_profit,
            'gross_profit': gross_profit,
            'gross_margin': gross_margin
        }

        shop_list_literal = "N'" + in_clause.replace("'", "''") + "'"
        sql_targets_sp = f"EXEC sp_TK_Dashboard_GetTargets {curr_year}, {curr_month}, {shop_list_literal}"
        targets_list = bjc.sf_db(sql_targets_sp, single=False)
        tr = list(targets_list[0]) if targets_list else []
        expected_len = 37
        if len(tr) < expected_len:
            tr = tr + [0] * (expected_len - len(tr))
        (t_break_even, t_order_count, t_monthly_sales, t_net_profit, t_gross_profit,
         t_infl_comm, t_infl_count, t_infl_video, t_video_count,
         t_act_service, t_ad_fee, t_plat_comm, t_vat, t_adjust, t_other,
         t_op_qd, t_op_sz, t_prod_cost, t_tou_cheng, t_wei_cheng, t_storage,
         t_wage_qd, t_wage_sz, t_rent_qd, t_rent_sz,
         t_creator_commission, t_partner_commission, t_ad_order_commission, t_channel_commission,
         t_shuadan_fee, t_shouhou_fee, t_kengwei_fee, t_buy_product_fee, t_gift_fee,
         t_inbound_fee, t_storage_fee, t_return_fee) = (
            float(tr[0] or 0), int(tr[1] or 0), float(tr[2] or 0), float(tr[3] or 0), float(tr[4] or 0),
            float(tr[5] or 0), int(tr[6] or 0), float(tr[7] or 0), int(tr[8] or 0),
            float(tr[9] or 0), float(tr[10] or 0), float(tr[11] or 0), float(tr[12] or 0), float(tr[13] or 0), float(tr[14] or 0),
            float(tr[15] or 0), float(tr[16] or 0), float(tr[17] or 0), float(tr[18] or 0), float(tr[19] or 0), float(tr[20] or 0),
            float(tr[21] or 0), float(tr[22] or 0), float(tr[23] or 0), float(tr[24] or 0),
            float(tr[25] or 0), float(tr[26] or 0), float(tr[27] or 0), float(tr[28] or 0),
            float(tr[29] or 0), float(tr[30] or 0), float(tr[31] or 0), float(tr[32] or 0), float(tr[33] or 0),
            float(tr[34] or 0), float(tr[35] or 0), float(tr[36] or 0)
        )

        monthly_targets = {
            'break_even_revenue': float(t_break_even),
            'order_count': int(t_order_count),
            'monthly_sales': float(t_monthly_sales),
            'net_profit': float(t_net_profit),
            'gross_profit': float(t_gross_profit),
            'influencer_commission': float(t_infl_comm),
            'influencer_count': int(t_infl_count),
            'influencer_video_fee': float(t_infl_video),
            'video_count': int(t_video_count),
            'activity_service_fee': float(t_act_service),
            'ad_fee': float(t_ad_fee),
            'platform_commission': float(t_plat_comm),
            'vat_fee': float(t_vat),
            'adjustment_fee': float(t_adjust),
            'other_platform_fee': float(t_other),
            'op_mgmt_qd': float(t_op_qd),
            'op_mgmt_sz': float(t_op_sz),
            'product_cost': float(t_prod_cost),
            'tou_cheng_cost': float(t_tou_cheng),
            'wei_cheng_cost': float(t_wei_cheng),
            'storage_return_cost': float(t_storage),
            'qingdao_wage': float(t_wage_qd),
            'shenzhen_wage': float(t_wage_sz),
            'qingdao_rent': float(t_rent_qd),
            'shenzhen_rent': float(t_rent_sz),
            'influencer_commission_detail': {
                'creator_commission': float(t_creator_commission),
                'partner_commission': float(t_partner_commission),
                'ad_order_commission': float(t_ad_order_commission),
                'channel_commission': float(t_channel_commission)
            },
            'influencer_video_fee_detail': {
                'shuadan_fee': float(t_shuadan_fee),
                'shouhou_fee': float(t_shouhou_fee),
                'wanghong_kengwei_fee': float(t_kengwei_fee),
                'buy_product_for_influencer_fee': float(t_buy_product_fee),
                'influencer_gift_fee': float(t_gift_fee)
            },
            'storage_return_cost_detail': {
                'inbound_fee': float(t_inbound_fee),
                'storage_fee': float(t_storage_fee),
                'return_fee': float(t_return_fee)
            }
        }

        # 使用“本月目标净利”重新计算实时保利额（本期和选定区间）
        target_net_profit = float(t_net_profit or 0)
        profit_target_revenue = 0.0 if gross_margin == 0 else ((fixed_total_rounded + target_net_profit) / gross_margin)
        business_results['profit_target_revenue'] = profit_target_revenue

        # -------------------------------------------------------------------------
        # 3. Selected Period Metrics
        # -------------------------------------------------------------------------
        sel_start_str = start_dt.strftime('%Y-%m-%d')
        sel_end_str = end_dt.strftime('%Y-%m-%d')
        sel_year = end_dt.year
        sel_month = end_dt.month

        sel_vals_sum = [0.0]*24
        yesterday_total_sum = 0.0
        for s in shops:
            s_lit = "N'" + str(s).replace("'", "''") + "'"
            sql_sel_sp = (
                f"EXEC sp_TK_Dashboard_GetMetrics "
                f"'{sel_start_str}','{sel_end_str}', {s_lit}, {sel_year}, {sel_month}"
            )
            sel_list = bjc.sf_db(sql_sel_sp, single=False)
            sel_raw = sel_list[0] if sel_list else [0]*24
            if len(sel_raw) < 24:
                curr_vals = list(sel_raw) + [0]*(24 - len(sel_raw))
            else:
                curr_vals = list(sel_raw[:24])
            yday = float(sel_raw[24] or 0) if len(sel_raw) > 24 else 0.0
            sel_vals_sum = [float(sel_vals_sum[i]) + float(curr_vals[i] or 0) for i in range(24)]
            yesterday_total_sum += yday
        sel_vals = sel_vals_sum
        yesterday_total = yesterday_total_sum
        (plat_comm_sel, vat_tax_sel, adjust_sel, other_fee_sel,
         monthly_sales_sel, wei_cheng_sel, infl_comm_sel, act_service_sel,
         tax_sel, storage_return_sel, infl_video_sel, ad_fee_sel,
         qd_wage_sel, sz_wage_sel, qd_rent_sel, sz_rent_sel,
         prod_cost_sel, tou_cheng_sel,
         order_count_sel, infl_count_sel, video_count_sel,
         op_qd_sel, op_sz_sel, rijun_total_sel) = (
            float(sel_vals[0] or 0), float(sel_vals[1] or 0), float(sel_vals[2] or 0), float(sel_vals[3] or 0),
            float(sel_vals[4] or 0), float(sel_vals[5] or 0), float(sel_vals[6] or 0), float(sel_vals[7] or 0),
            float(sel_vals[8] or 0), float(sel_vals[9] or 0), float(sel_vals[10] or 0), float(sel_vals[11] or 0),
            float(sel_vals[12] or 0), float(sel_vals[13] or 0), float(sel_vals[14] or 0), float(sel_vals[15] or 0),
            float(sel_vals[16] or 0), float(sel_vals[17] or 0),
            int(sel_vals[18] or 0), int(sel_vals[19] or 0), int(sel_vals[20] or 0),
            float(sel_vals[21] or 0), float(sel_vals[22] or 0), float(sel_vals[23] or 0)
        )
        vat_sel_total = (vat_tax_sel or 0) + (tax_sel or 0)

        sel_comm_detail = _get_influencer_commission_detail(sel_start_str, sel_end_str)
        sel_channel_commission = float((sel_comm_detail.get('channel_commission') or 0) or 0)
        base_influencer_commission_cost_sel = abs(infl_comm_sel or 0)
        channel_commission_cost_sel = abs(sel_channel_commission or 0)
        infl_comm_total_sel = base_influencer_commission_cost_sel + channel_commission_cost_sel
        sel_video_detail = _get_influencer_video_fee_detail(sel_start_str, sel_end_str)
        infl_video_sel = float((infl_video_sel or 0) + float((sel_video_detail.get('influencer_gift_fee') or 0) or 0))

        prod_cost_detail_sel = _get_product_cost_detail(sel_start_str, sel_end_str)
        prod_platform_sel = float((prod_cost_detail_sel.get('platform_product_cost') or 0) or 0)
        prod_sample_sel = float((prod_cost_detail_sel.get('sample_cost') or 0) or 0)
        prod_self_sample_sel = float((prod_cost_detail_sel.get('self_sample_cost') or 0) or 0)
        prod_aftersales_sel = float((prod_cost_detail_sel.get('aftersales_cost') or 0) or 0)
        prod_cost_sel = (
            prod_platform_sel
            + prod_sample_sel
            + prod_self_sample_sel
            + prod_aftersales_sel
        )

        gross_profit_sel = (
            (monthly_sales_sel or 0)
            - abs(infl_comm_total_sel or 0)
            - abs(infl_video_sel or 0)
            - abs(ad_fee_sel or 0)
            - abs(act_service_sel or 0)
            - abs(plat_comm_sel or 0)
            - abs(vat_sel_total or 0)
            - abs(adjust_sel or 0)
            - abs(prod_cost_sel or 0)
            - abs(tou_cheng_sel or 0)
            - abs(wei_cheng_sel or 0)
            - abs(storage_return_sel or 0)
            - abs(other_fee_sel or 0)
        )

        fixed_total_sel = (
            (op_qd_sel or 0) + (op_sz_sel or 0)
            + (qd_wage_sel or 0) + (sz_wage_sel or 0)
            + (qd_rent_sel or 0) + (sz_rent_sel or 0)
        )

        net_profit_sel = gross_profit_sel - fixed_total_sel
        gross_margin_sel_raw = 0.0 if monthly_sales_sel == 0 else (gross_profit_sel / monthly_sales_sel)
        gross_margin_sel = round(gross_margin_sel_raw, 4) if gross_margin_sel_raw != 0 else 0.0
        fixed_total_sel_rounded = (
            round(op_qd_sel or 0, 2) + round(op_sz_sel or 0, 2)
            + round(qd_wage_sel or 0, 2) + round(sz_wage_sel or 0, 2)
            + round(qd_rent_sel or 0, 2) + round(sz_rent_sel or 0, 2)
        )
        break_even_sel = 0.0 if gross_margin_sel == 0 else (fixed_total_sel_rounded / gross_margin_sel)
        profit_target_sel = 0.0 if gross_margin_sel == 0 else ((fixed_total_sel_rounded + target_net_profit) / gross_margin_sel)

        actuals = {
            'break_even_revenue': break_even_sel,
            'order_count': order_count_sel,
            'monthly_sales': monthly_sales_sel,
            'net_profit': net_profit_sel,
            'gross_profit': gross_profit_sel,
            'influencer_commission': infl_comm_total_sel,
            'influencer_commission_detail': sel_comm_detail,
            'influencer_count': infl_count_sel,
            'influencer_video_fee': infl_video_sel,
            'influencer_video_fee_detail': sel_video_detail,
            'video_count': video_count_sel,
            'activity_service_fee': act_service_sel,
            'ad_fee': ad_fee_sel,
            'platform_commission': plat_comm_sel,
            'vat_fee': vat_sel_total,
            'adjustment_fee': adjust_sel,
            'other_platform_fee': other_fee_sel,
            'op_mgmt_qd': op_qd_sel,
            'op_mgmt_sz': op_sz_sel,
            'product_cost': prod_cost_sel,
            'product_cost_detail': prod_cost_detail_sel,
            'tou_cheng_cost': tou_cheng_sel,
            'wei_cheng_cost': wei_cheng_sel,
            'storage_return_cost': storage_return_sel,
            'qingdao_wage': qd_wage_sel,
            'shenzhen_wage': sz_wage_sel,
            'qingdao_rent': qd_rent_sel,
            'shenzhen_rent': sz_rent_sel,
            'profit_target_revenue': profit_target_sel
        }
        total_val = yesterday_total

        payload = {
            'success': True,
            'total_sales': total_val,
            'yesterday': yday_str,
            'progress_pct': progress_pct,
            'period_days': period_days,
            'progress_day': progress_day,
            'month_total_days': month_total_days,
            'total_days': month_total_days,
            'today_day': progress_day,
            'fixed_costs': fixed_costs,
            'product_logistics_costs': product_logistics_costs,
            'promotional_costs': promotional_costs,
            'variable_costs': variable_costs,
            'business_results': business_results,
            'monthly_targets': monthly_targets,
            'actuals': actuals
        }
        _metrics_cache[cache_key] = (now_ts + METRICS_CACHE_TTL, payload)
        return jsonify(payload)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
