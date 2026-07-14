#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入Flask应用
from web_app import app

print("=== Flask应用路由调试 ===")
print(f"Flask应用名称: {app.name}")
print(f"调试模式: {app.debug}")
print()

print("=== 所有注册的路由 ===")
for rule in app.url_map.iter_rules():
    print(f"路由: {rule.rule}")
    print(f"  方法: {list(rule.methods)}")
    print(f"  端点: {rule.endpoint}")
    print()

print("=== 查找特定路由 ===")
target_routes = ['/api/test_simple', '/api/get_dashboard_data']
for target in target_routes:
    found = False
    for rule in app.url_map.iter_rules():
        if rule.rule == target:
            print(f"✅ 找到路由: {target}")
            print(f"   方法: {list(rule.methods)}")
            print(f"   端点: {rule.endpoint}")
            found = True
            break
    if not found:
        print(f"❌ 未找到路由: {target}")
    print()

print("=== 测试路由函数 ===")
try:
    with app.test_client() as client:
        print("测试 /api/test_simple:")
        response = client.get('/api/test_simple')
        print(f"  状态码: {response.status_code}")
        print(f"  响应: {response.get_json()}")
        print()
        
        print("测试 /:")
        response = client.get('/')
        print(f"  状态码: {response.status_code}")
        print(f"  响应长度: {len(response.data)} bytes")
        print()
except Exception as e:
    print(f"❌ 测试路由函数时出错: {e}")

print("=== 调试完成 ===")