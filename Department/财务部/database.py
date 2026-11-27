"""财务模块共享连接入口；连接配置仍由 secret_settings 统一提供。"""


def connect():
    import pytds
    from secret_settings import sql_server_config
    return pytds.connect(**sql_server_config())
