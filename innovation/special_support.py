"""创新专项的数据存储初始化和公共 SQL 辅助。"""

from __future__ import annotations

import threading

from bjc import dui_db
from department_permissions import permission_manager
from flask import has_request_context, session


_STORAGE_READY = False
_STORAGE_LOCK = threading.Lock()


def ensure_special_storage() -> None:
    """幂等创建专项表，并为现有提案和流转表补齐专项字段。"""
    global _STORAGE_READY
    if _STORAGE_READY:
        return

    with _STORAGE_LOCK:
        if _STORAGE_READY:
            return

        dui_db("""
            IF OBJECT_ID(N'dbo.chuangxin_zhuanxiang', N'U') IS NULL
            BEGIN
                CREATE TABLE dbo.chuangxin_zhuanxiang (
                    zhuanxiang_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    zhuanxiang_bianhao NVARCHAR(50) NOT NULL,
                    biaoti NVARCHAR(200) NOT NULL,
                    nanti_miaoshu NVARCHAR(MAX) NOT NULL,
                    fabu_user_id NVARCHAR(100) NOT NULL,
                    fabu_user_name NVARCHAR(100) NOT NULL,
                    fabu_bumen NVARCHAR(100) NULL,
                    chengjie_bumen NVARCHAR(100) NULL,
                    zhuangtai VARCHAR(20) NOT NULL CONSTRAINT DF_chuangxin_zhuanxiang_zhuangtai DEFAULT 'caogao',
                    jiangli_jifen INT NOT NULL CONSTRAINT DF_chuangxin_zhuanxiang_jiangli DEFAULT 0,
                    jiangli_mingxi NVARCHAR(MAX) NULL,
                    fabu_shijian DATETIME2 NULL,
                    chuangjian_shijian DATETIME2 NOT NULL CONSTRAINT DF_chuangxin_zhuanxiang_created DEFAULT SYSDATETIME(),
                    gengxin_shijian DATETIME2 NOT NULL CONSTRAINT DF_chuangxin_zhuanxiang_updated DEFAULT SYSDATETIME()
                );
            END
        """)
        dui_db("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE object_id = OBJECT_ID(N'dbo.chuangxin_zhuanxiang')
                  AND name = N'UX_chuangxin_zhuanxiang_bianhao'
            )
                CREATE UNIQUE INDEX UX_chuangxin_zhuanxiang_bianhao
                ON dbo.chuangxin_zhuanxiang(zhuanxiang_bianhao);
        """)
        dui_db("""
            IF COL_LENGTH('dbo.chuangxin_zhuanxiang', 'tupian_lujing') IS NULL
                ALTER TABLE dbo.chuangxin_zhuanxiang ADD tupian_lujing NVARCHAR(MAX) NULL;
            IF COL_LENGTH('dbo.chuangxin_zhuanxiang', 'shipin_lujing') IS NULL
                ALTER TABLE dbo.chuangxin_zhuanxiang ADD shipin_lujing NVARCHAR(MAX) NULL;
            IF COL_LENGTH('dbo.chuangxin_tibao1', N'图片详情') IS NULL
                ALTER TABLE dbo.chuangxin_tibao1 ADD 图片详情 NVARCHAR(MAX) NULL;
            IF COL_LENGTH('dbo.chuangxin_tibao1', N'视频详情') IS NULL
                ALTER TABLE dbo.chuangxin_tibao1 ADD 视频详情 NVARCHAR(MAX) NULL;
        """)
        dui_db("""
            IF COL_LENGTH('dbo.chuangxin_liuzhuan1', N'流转备注') IS NULL
                ALTER TABLE dbo.chuangxin_liuzhuan1 ADD 流转备注 NVARCHAR(MAX) NULL;
        """)
        # 将旧版 ZX 前缀编号转换为三位数字，保留现有专项的排序关系。
        dui_db("""
            IF EXISTS (
                SELECT 1
                FROM dbo.chuangxin_zhuanxiang
                WHERE zhuanxiang_bianhao LIKE N'%[^0-9]%'
            )
            BEGIN
                UPDATE dbo.chuangxin_zhuanxiang
                SET zhuanxiang_bianhao = N'LEGACY-' + CONVERT(NVARCHAR(20), zhuanxiang_id)
                WHERE zhuanxiang_bianhao LIKE N'%[^0-9]%';

                DECLARE @next_special_no INT = ISNULL((
                    SELECT MAX(CASE WHEN zhuanxiang_bianhao NOT LIKE N'%[^0-9]%'
                                    THEN CONVERT(INT, zhuanxiang_bianhao) END)
                    FROM dbo.chuangxin_zhuanxiang
                ), 0) + 1;

                ;WITH legacy_rows AS (
                    SELECT zhuanxiang_id,
                           ROW_NUMBER() OVER (ORDER BY zhuanxiang_id) AS row_no
                    FROM dbo.chuangxin_zhuanxiang
                    WHERE zhuanxiang_bianhao LIKE N'LEGACY-%'
                )
                UPDATE z
                SET zhuanxiang_bianhao = RIGHT(N'000' + CONVERT(NVARCHAR(20), @next_special_no + legacy_rows.row_no - 1), 3)
                FROM dbo.chuangxin_zhuanxiang z
                INNER JOIN legacy_rows ON legacy_rows.zhuanxiang_id = z.zhuanxiang_id;
            END
        """)
        dui_db("""
            IF COL_LENGTH(N'dbo.chuangxin_zhuanxiang', N'fabu_shijian') IS NULL
                ALTER TABLE dbo.chuangxin_zhuanxiang ADD fabu_shijian DATETIME2 NULL;
        """)
        dui_db("""
            IF COL_LENGTH(N'dbo.chuangxin_zhuanxiang', N'chengjie_bumen') IS NULL
                ALTER TABLE dbo.chuangxin_zhuanxiang ADD chengjie_bumen NVARCHAR(100) NULL;
        """)

        proposal_columns = {
            'zhuanxiang_id': 'BIGINT NULL',
            'tijiao_user_id': 'NVARCHAR(100) NULL',
            'tijiao_user_avatar': 'NVARCHAR(500) NULL',
            'xiangfa_zhuangtai': "VARCHAR(20) NULL",
            'zhuanxiang_pingfen': 'DECIMAL(5,2) NULL',
            'zhuanxiang_pingyu': 'NVARCHAR(MAX) NULL',
            'caina_user_id': 'NVARCHAR(100) NULL',
            'caina_shijian': 'DATETIME2 NULL',
            'zhuanxiang_fafang_jifen': 'INT NULL',
            'zhuanxiang_fafang_biaoshi': 'BIT NOT NULL DEFAULT 0',
            'zhuanxiang_tongzhi_zhuangtai': 'VARCHAR(20) NULL',
            'zhuanxiang_tongzhi_shijian': 'DATETIME2 NULL',
        }
        for column_name, column_definition in proposal_columns.items():
            dui_db(f"""
                IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'{column_name}') IS NULL
                    ALTER TABLE dbo.chuangxin_tibao1
                    ADD [{column_name}] {column_definition};
            """)

        flow_columns = {
            'zhuanxiang_id': 'BIGINT NULL',
            'liuzhuan_leixing': 'VARCHAR(20) NULL',
            'caozuo_user_id': 'NVARCHAR(100) NULL',
        }
        for column_name, column_definition in flow_columns.items():
            dui_db(f"""
                IF COL_LENGTH(N'dbo.chuangxin_liuzhuan1', N'{column_name}') IS NULL
                    ALTER TABLE dbo.chuangxin_liuzhuan1
                    ADD [{column_name}] {column_definition};
            """)

        dui_db("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE object_id = OBJECT_ID(N'dbo.chuangxin_tibao1')
                  AND name = N'IX_chuangxin_tibao1_zhuanxiang'
            )
                CREATE INDEX IX_chuangxin_tibao1_zhuanxiang
                ON dbo.chuangxin_tibao1(zhuanxiang_id, xiangfa_zhuangtai, 发起时间);
        """)
        dui_db("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE object_id = OBJECT_ID(N'dbo.chuangxin_liuzhuan1')
                  AND name = N'IX_chuangxin_liuzhuan1_zhuanxiang'
            )
                CREATE INDEX IX_chuangxin_liuzhuan1_zhuanxiang
                ON dbo.chuangxin_liuzhuan1(zhuanxiang_id, 项目编号, 流转时间);
        """)
        # 权限种子同时写入数据库，保证首次打开专项页面即可识别人力资源与行政部和流程与AI部管理员。
        dui_db("""
            IF OBJECT_ID(N'dbo.quanxian', N'U') IS NOT NULL
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM dbo.quanxian
                    WHERE LTRIM(RTRIM(GongNeng)) = N'innovation_special_manage'
                )
                    UPDATE dbo.quanxian
                    SET YongHu = N'',
                        BuMen = N'人力资源与行政部；流程与AI部',
                        FuJiGongNeng = N'innovation_proposals',
                        MingCheng = N'创新专项管理',
                        MiaoShu = N'人力资源与行政部和流程与AI部创建、发布、关闭创新专项。',
                        QiYong = 1,
                        GengXinShiJian = SYSDATETIME()
                    WHERE LTRIM(RTRIM(GongNeng)) = N'innovation_special_manage';
                ELSE
                    INSERT INTO dbo.quanxian
                        (GongNeng, YongHu, BuMen, FuJiGongNeng, MingCheng, MiaoShu, QiYong, GengXinShiJian)
                    VALUES
                        (N'innovation_special_manage', N'', N'人力资源与行政部；流程与AI部',
                         N'innovation_proposals', N'创新专项管理',
                         N'人力资源与行政部和流程与AI部创建、发布、关闭创新专项。', 1, SYSDATETIME());
            END
        """)
        try:
            permission_manager.clear_cache()
        except Exception:
            pass
        _STORAGE_READY = True


def sql_text(value: object) -> str:
    """将文本安全转换成 SQL Server Unicode 字面量。"""
    if value is None:
        return 'NULL'
    text = str(value).replace("'", "''")
    return f"N'{text}'"


def sql_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _department_names_from_session() -> set[str]:
    if not has_request_context():
        return set()
    names: set[str] = set()
    raw = session.get('user_department')
    if isinstance(raw, (list, tuple, set)):
        names.update(str(item or '').strip() for item in raw if str(item or '').strip())
    else:
        value = str(raw or '').strip()
        if value:
            names.add(value)

    # 权限调试页的“模拟部门/模拟用户”只写入调试字段，不会改动真实登录部门。
    # 专项承接部门判定也要读取同一份模拟身份，否则页面能进入但评价按钮仍会被隐藏。
    debug_departments = session.get('permission_debug_departments')
    if isinstance(debug_departments, str):
        debug_departments = [debug_departments]
    if isinstance(debug_departments, (list, tuple, set)):
        names.update(str(item or '').strip() for item in debug_departments if str(item or '').strip())

    debug_user_id = str(session.get('permission_debug_user_open_id') or '').strip()
    if debug_user_id:
        try:
            for item in permission_manager.get_user_departments(debug_user_id) or []:
                name = item.get('name') if isinstance(item, dict) else item
                name = str(name or '').strip()
                if name:
                    names.add(name)
        except Exception:
            pass
    return names


def _same_department(actual: str, target: str) -> bool:
    """匹配飞书部门名称及省略末尾“部”字的简称。"""
    actual_name = str(actual or '').strip()
    target_name = str(target or '').strip()
    if not actual_name or not target_name:
        return False
    if actual_name == target_name:
        return True
    if target_name.endswith('部') and actual_name == target_name[:-1]:
        return True
    if actual_name.endswith('部') and actual_name[:-1] == target_name:
        return True
    return False


def user_in_receiver_department(receiver_department: str, user_id: str) -> bool:
    """判断当前用户是否属于专项指定的承接部门。"""
    target = str(receiver_department or '').strip()
    if not target:
        return False

    departments = _department_names_from_session()
    debug_active = bool(session.get('permission_debug_departments') or session.get('permission_debug_user_open_id'))
    if user_id and not debug_active:
        try:
            for item in permission_manager.get_user_departments(user_id) or []:
                if isinstance(item, dict):
                    name = str(item.get('name') or '').strip()
                else:
                    name = str(item or '').strip()
                if name:
                    departments.add(name)
        except Exception:
            pass
    return any(_same_department(name, target) for name in departments)

