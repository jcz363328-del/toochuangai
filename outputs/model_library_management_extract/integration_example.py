"""将提取出来的蓝图接回 Flask 应用的最小示例。

运行前需要把宿主项目根目录加入 PYTHONPATH，并提供 bjc、department_permissions、
innovation.message_service、secret_settings 等依赖。
"""
from flask import Flask
from model_management import model_management_bp

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "replace-with-host-secret"
app.register_blueprint(model_management_bp)

# 宿主登录流程需要设置：
# session["feishu_user_name"] = 当前登录人的姓名

if __name__ == "__main__":
    app.run(debug=True)
