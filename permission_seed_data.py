"""`dbo.quanxian` 的可重复执行种子数据。

运行时权限判断只读取数据库。本模块仅供数据库迁移/初始化脚本使用，
避免把部门和个人白名单继续散落在路由代码里。
"""

from __future__ import annotations


SEP = "；"


def _joined(values):
    if values == "all":
        return "all"
    return SEP.join(str(value or "").strip() for value in (values or []) if str(value or "").strip())


CORE_PARENT_MAP = {
    "tk_email_register": "tk_project_group",
    "tk_video_realtime": "tk_project_group",
    "tk_dashboard": "tk_project_group",
    "tk_total_dashboard": "tk_project_group",
    "script_generator": "tk_project_group",
    "influencer_management": "tk_project_group",
}


CORE_USER_OVERRIDES = {
    "operation_dept_1": "孙洁；侯梁",
    "operation_dept_2": "孙洁；侯梁",
    "operation_dept_3": "孙洁；侯梁",
    "operation_dept_6": "孙洁；侯梁",
    "operation_dept_7": "孙洁；侯梁；赵瑜",
}


CONTENT_FACTORY_DEPARTMENTS = (
    "内容生产工厂；TK部门；TK直播部；BD部；短视频部；客服；"
    "产品&店铺运营；新人组；AI部；总经办；财务部；亚马逊"
)


CONTENT_FACTORY_CHILD_DEPARTMENTS = (
    "内容生产工厂；TK部门；TK直播部；BD部；短视频部；客服；"
    "产品&店铺运营；AI部；总经办；财务部；深圳团队"
)


ADMIN_USERS = "周俊成；毕景春；陶晓飞；李昌翰；孙军；李春；宋亚倩；王丰慧；陈梦昭"
PARTIAL_ADMIN_USERS = "张莉；周俊成；毕景春；陶晓飞；李昌翰；孙军；李春；宋亚倩；王丰慧；陈梦昭"


EXTRA_PERMISSION_ROWS = [
    {
        "gongneng": "seedance_video",
        "mingcheng": "Seedance 视频生成",
        "yonghu": "",
        "bumen": "all",
        "fujigongneng": "",
        "miaoshu": "Seedance 独立模块，当前向全体已登录用户开放。",
    },
    {
        "gongneng": "*",
        "mingcheng": "全部功能（开发者）",
        "yonghu": "ou_developer_id；dev_admin_user_001",
        "bumen": "",
        "fujigongneng": "",
        "miaoshu": "仅用于配置开发者和本地总经办调试账号的全功能权限。",
    },
    {
        "gongneng": "tk_invite_monitor",
        "mingcheng": "邀请ID实时监控",
        "yonghu": "",
        "bumen": CONTENT_FACTORY_DEPARTMENTS,
        "fujigongneng": "tk_project_group",
        "miaoshu": "邀请ID上传、列表、12小时未检查及达人登记。",
    },
    {
        "gongneng": "tk_monthly_target_import",
        "mingcheng": "月度目标导入",
        "yonghu": "",
        "bumen": CONTENT_FACTORY_DEPARTMENTS,
        "fujigongneng": "tk_project_group",
        "miaoshu": "月度目标导入、模板下载。",
    },
    {
        "gongneng": "tk_bd_metrics",
        "mingcheng": "BD指标",
        "yonghu": "",
        "bumen": CONTENT_FACTORY_DEPARTMENTS,
        "fujigongneng": "tk_project_group",
        "miaoshu": "BD指标页面和数据查询。",
    },
    {
        "gongneng": "tk_bd_metrics_import",
        "mingcheng": "BD指标导入",
        "yonghu": "",
        "bumen": CONTENT_FACTORY_DEPARTMENTS,
        "fujigongneng": "tk_project_group",
        "miaoshu": "BD指标模板和导入。",
    },
    {
        "gongneng": "tk_gmv_ratio",
        "mingcheng": "视频、商品卡、达人GMV占比",
        "yonghu": "",
        "bumen": CONTENT_FACTORY_DEPARTMENTS,
        "fujigongneng": "tk_project_group",
        "miaoshu": "GMV占比页面和数据。",
    },
    {
        "gongneng": "tk_gmv_authorization",
        "mingcheng": "GMV未授权提醒",
        "yonghu": "",
        "bumen": CONTENT_FACTORY_DEPARTMENTS,
        "fujigongneng": "tk_project_group",
        "miaoshu": "批量检查并通知GMV未授权视频。",
    },
    {
        "gongneng": "tk_project_seedance",
        "mingcheng": "Seedance视频生成（内容生产工厂）",
        "yonghu": "",
        "bumen": CONTENT_FACTORY_DEPARTMENTS,
        "fujigongneng": "tk_project_group",
        "miaoshu": "内容生产工厂内的Seedance入口。",
    },
    {
        "gongneng": "tk_dashboard_legacy",
        "mingcheng": "旧版TK数据看板",
        "yonghu": "",
        "bumen": CONTENT_FACTORY_DEPARTMENTS,
        "fujigongneng": "tk_project_group",
        "miaoshu": "普通用户按BD、组长或区域过滤。",
    },
    {
        "gongneng": "tk_dashboard_legacy_all",
        "mingcheng": "旧版TK数据看板（全组数据）",
        "yonghu": ADMIN_USERS,
        "bumen": "",
        "fujigongneng": "tk_dashboard_legacy",
        "miaoshu": "允许查看旧版TK看板全部组数据。",
    },
    {
        "gongneng": "tk_dashboard_full",
        "mingcheng": "TK汇总看板（全量）",
        "yonghu": ADMIN_USERS,
        "bumen": "",
        "fujigongneng": "tk_total_dashboard",
        "miaoshu": "完整汇总看板白名单。",
    },
    {
        "gongneng": "tk_joint_dashboard_all",
        "mingcheng": "TK联营看板（全部店铺）",
        "yonghu": PARTIAL_ADMIN_USERS,
        "bumen": "",
        "fujigongneng": "tk_project_group",
        "miaoshu": "允许查看全部已配置联营店铺。",
    },
    {
        "gongneng": "tk_dashboard_82",
        "mingcheng": "TK 82看板",
        "yonghu": "张莉；周俊成；毕景春；陶晓飞；李昌翰；孙军；李春；宋亚倩；王丰慧；陈梦昭；朱晓禹；侯梁",
        "bumen": "",
        "fujigongneng": "operation_dept_6；tk_project_group",
        "miaoshu": "82号店独立看板和指标接口。",
    },
    {
        "gongneng": "tk_dashboard_88",
        "mingcheng": "TK 88看板",
        "yonghu": "张莉；周俊成；毕景春；陶晓飞；李昌翰；孙军；李春；宋亚倩；王丰慧；陈梦昭；朱晓禹；侯梁；刘俊霞；李晓明",
        "bumen": "",
        "fujigongneng": "operation_dept_6；newcomer_group",
        "miaoshu": "88号店独立看板和指标接口。",
    },
    {
        "gongneng": "tk_dashboard_90",
        "mingcheng": "TK 90看板",
        "yonghu": "张莉；周俊成；毕景春；陶晓飞；李昌翰；孙军；李春；宋亚倩；王丰慧；陈梦昭；朱晓禹；侯梁；孙洁",
        "bumen": "",
        "fujigongneng": "operation_dept_1",
        "miaoshu": "90号店独立看板和指标接口。",
    },
    {
        "gongneng": "xiaotu_report_history_all",
        "mingcheng": "小图报告历史（全量上传记录）",
        "yonghu": "陶晓飞；周俊成；毕景春",
        "bumen": "",
        "fujigongneng": "xiaotu_qa",
        "miaoshu": "可查看所有上传人的报告。",
    },
    {
        "gongneng": "xiaotu_report_history_operation_scope",
        "mingcheng": "小图报告历史（运营部门范围）",
        "yonghu": "刘蓉蓉；孙洁；侯梁",
        "bumen": "",
        "fujigongneng": "xiaotu_qa",
        "miaoshu": "数据范围：运营一、二、三、六、七部。",
    },
    {
        "gongneng": "xiaotu_report_history_operation_3_scope",
        "mingcheng": "小图报告历史（运营三部范围）",
        "yonghu": "大张雯",
        "bumen": "",
        "fujigongneng": "xiaotu_qa",
        "miaoshu": "数据范围：运营三部。",
    },
    {
        "gongneng": "xiaotu_report_history_department_leader",
        "mingcheng": "小图报告历史（部门负责人范围）",
        "yonghu": "@department_leader",
        "bumen": "",
        "fujigongneng": "xiaotu_qa",
        "miaoshu": "动态规则：飞书部门负责人可查看所负责部门成员报告。",
    },
    {
        "gongneng": "xiaotu_report_history_debug",
        "mingcheng": "小图报告历史（权限调试视角）",
        "yonghu": "周俊成",
        "bumen": "",
        "fujigongneng": "xiaotu_qa",
        "miaoshu": "可切换本人、全量、运营受限视角。",
    },
    {
        "gongneng": "innovation_committee_score",
        "mingcheng": "创新委员会打分",
        "yonghu": "周俊成；陶晓飞；孙军；毕景春；李昌瀚；蔡晶；韩雅俊；孙洁；陈子烨",
        "bumen": "",
        "fujigongneng": "innovation_proposals",
        "miaoshu": "创新委员会评分权限。",
    },
    {
        "gongneng": "innovation_star_manage",
        "mingcheng": "创新之星内容管理",
        "yonghu": "韩雅俊",
        "bumen": "AI部",
        "fujigongneng": "innovation_proposals",
        "miaoshu": "创新之星内容新增、编辑和删除。",
    },
    {
        "gongneng": "image_history_all",
        "mingcheng": "图片工具生成历史（全部账号）",
        "yonghu": "周俊成",
        "bumen": "",
        "fujigongneng": "visual_design_dept",
        "miaoshu": "查看图片工具全部账号的生成历史。",
    },
    {
        "gongneng": "operation_fba_shipping",
        "mingcheng": "FBA货件运输方式",
        "yonghu": "",
        "bumen": "运营一部；运营二部；运营三部；运营六部；运营七部；新人组；AI部；总经办",
        "fujigongneng": "",
        "miaoshu": "运营部门和新人组共用的FBA货件运输方式。",
    },
]


JOINT_SHOP_USERS = {
    "82": "侯梁",
    "88": "刘俊霞",
    "90": "孙洁",
    "87": "刘蓉蓉",
    "89": "柳琳",
    "91": "叶雨菲",
    "92": "刘星辰",
    "93": "赵璐华",
    "95": "杨明月",
    "96": "周雪",
    "106": "李娜",
    "97": "郭婷",
    "101": "侯瑞昕",
    "84": "大张雯",
    "107": "郭鑫",
    "108": "张彦微",
    "109": "王钰媛",
}


for shop, user_name in JOINT_SHOP_USERS.items():
    EXTRA_PERMISSION_ROWS.append(
        {
            "gongneng": f"tk_joint_shop_{shop}",
            "mingcheng": f"TK联营看板（店铺{shop}）",
            "yonghu": user_name,
            "bumen": "",
            "fujigongneng": "tk_project_group",
            "miaoshu": f"联营店铺{shop}的数据权限。",
        }
    )


def build_permission_seed_rows(permission_config):
    rows = []
    for function_name, config in permission_config.items():
        rows.append(
            {
                "gongneng": function_name,
                "mingcheng": str(config.get("name") or function_name),
                "yonghu": CORE_USER_OVERRIDES.get(function_name, ""),
                "bumen": _joined(config.get("allowed_departments")),
                "fujigongneng": CORE_PARENT_MAP.get(function_name, ""),
                "miaoshu": str(config.get("description") or ""),
            }
        )
    rows.extend(dict(row) for row in EXTRA_PERMISSION_ROWS)
    return rows
