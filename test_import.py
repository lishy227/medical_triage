"""
测试数据库模块是否能正常导入
"""
import sys
import os

# 添加后端目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'medical_triage_back'))

try:
    print("测试导入 database 模块...")
    from database import init_database, get_database_url
    print("✓ 导入成功")
    
    print("\n数据库URL:", get_database_url())
    
    print("\n测试导入 web_server...")
    from web_server import app
    print("✓ web_server 导入成功")
    
    print("\n所有测试通过！")
    
except Exception as e:
    print(f"✗ 错误: {e}")
    import traceback
    traceback.print_exc()
