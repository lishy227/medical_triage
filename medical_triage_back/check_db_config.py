"""
数据库配置检查脚本

用于检查 .env 文件配置是否正确加载

使用方法:
    python check_db_config.py
"""
import os
import sys

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import _load_env_file, load_config

print("=" * 60)
print("数据库配置检查")
print("=" * 60)

# 1. 检查原始环境变量
print("\n1. 检查原始环境变量:")
db_url_before = os.getenv('DATABASE_URL', '未设置')
print(f"   DATABASE_URL (加载前): {db_url_before}")

# 2. 加载 .env 文件
print("\n2. 加载 .env 文件:")
_load_env_file()

# 3. 检查加载后的环境变量
print("\n3. 检查加载后的环境变量:")
db_url_after = os.getenv('DATABASE_URL', '未设置')
print(f"   DATABASE_URL (加载后): {db_url_after}")

if db_url_before == db_url_after:
    print("   注意: 环境变量未发生变化，可能 .env 文件不存在或配置相同")
else:
    print("   ✓ 环境变量已从 .env 文件加载")

# 4. 检查 .env 文件内容
print("\n4. 检查 .env 文件内容:")
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    print(f"   .env 文件存在: {env_path}")
    with open(env_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        db_lines = [l.strip() for l in lines if l.strip().startswith('DATABASE_URL')]
        if db_lines:
            print(f"   找到配置: {db_lines[0]}")
        else:
            print("   未找到 DATABASE_URL 配置")
else:
    print(f"   ✗ .env 文件不存在: {env_path}")

# 5. 测试数据库连接
print("\n5. 测试数据库连接:")
from database import init_database, get_database_url
db_url = get_database_url()
print(f"   实际使用的数据库URL: {db_url}")

try:
    engine = init_database()
    print(f"   数据库类型: {engine.dialect.name}")
    print(f"   数据库驱动: {engine.dialect.driver}")
    if engine.dialect.name == 'sqlite':
        print(f"   SQLite 文件: {engine.url.database}")
    else:
        print(f"   数据库名: {engine.url.database}")
        print(f"   主机: {engine.url.host}")
        print(f"   端口: {engine.url.port}")
    print("   ✓ 数据库连接成功")
except Exception as e:
    print(f"   ✗ 数据库连接失败: {e}")

print("\n" + "=" * 60)
print("检查完成")
print("=" * 60)

# 给出建议
print("\n建议:")
if 'sqlite' in db_url.lower():
    print("- 当前使用的是 SQLite，如需使用 MySQL，请在 .env 文件中设置:")
    print("  DATABASE_URL=mysql+pymysql://用户名:密码@主机地址/数据库名")
else:
    print("- 当前使用的是 MySQL 数据库")
