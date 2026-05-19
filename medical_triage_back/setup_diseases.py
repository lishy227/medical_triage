"""
数据库疾病表初始化脚本 — 将 medical.json 导入 MySQL

功能：
  1. 自动创建 diseases 表
  2. 流式导入 8,808 条疾病数据（逐行读取，不占内存）
  3. 支持断点续导（跳过已存在的记录）

用法：
  python setup_diseases.py                  # 默认：上传文件中的默认值
  python setup_diseases.py --force          # 删除旧表重建
  python setup_diseases.py --status         # 仅查看当前状态

环境要求：
  .env 中已配置 DATABASE_URL（MySQL）
  pip install pymysql（已包含在 requirements.txt）
"""
import argparse
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

# ---- 表结构 SQL ----------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS diseases (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    cause TEXT,
    symptoms TEXT,
    cure_department TEXT,
    cure_way TEXT,
    cure_lasttime VARCHAR(100),
    cured_prob VARCHAR(100),
    common_drug TEXT,
    do_eat TEXT,
    not_eat TEXT,
    prevent TEXT,
    get_prob VARCHAR(100),
    easy_get VARCHAR(200),
    get_way VARCHAR(200),
    complications TEXT,
    cost_money VARCHAR(100),
    category TEXT,
    check_items TEXT,
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

# ---- 连接到数据库 ---------------------------------------------------------


def get_connection():
    """从 .env / config 读取 DATABASE_URL 并建立 pymysql 连接"""
    from config import get_config

    config = get_config()
    url = config.database_url

    # 解析 mysql+pymysql://user:pass@host/dbname
    if url.startswith("mysql+pymysql://"):
        url = url[len("mysql+pymysql://"):]
    elif url.startswith("mysql://"):
        url = url[len("mysql://"):]
    else:
        print(f"错误: DATABASE_URL 不是 MySQL 格式: {url}")
        print("提示: 请修改 .env 为 mysql+pymysql://user:pass@host/dbname")
        sys.exit(1)

    user_pass, host_db = url.split("@", 1)
    if ":" in user_pass:
        user, password = user_pass.split(":", 1)
    else:
        user, password = user_pass, ""

    host_port, _, database = host_db.partition("/")
    if ":" in host_port:
        host, port = host_port.split(":", 1)
    else:
        host, port = host_port, "3306"

    import pymysql

    return pymysql.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
    )


# ---- 导入数据 ------------------------------------------------------------


def get_disease_fields():
    """字段名 → JSON 键映射"""
    return [
        ("name", "name", str, ""),
        ("description", "desc", str, ""),
        ("cause", "cause", str, ""),
        ("symptoms", "symptom", list, []),
        ("cure_department", "cure_department", list, []),
        ("cure_way", "cure_way", list, []),
        ("cure_lasttime", "cure_lasttime", str, ""),
        ("cured_prob", "cured_prob", str, ""),
        ("common_drug", "common_drug", list, []),
        ("do_eat", "do_eat", list, []),
        ("not_eat", "not_eat", list, []),
        ("prevent", "prevent", str, ""),
        ("get_prob", "get_prob", str, ""),
        ("easy_get", "easy_get", str, ""),
        ("get_way", "get_way", str, ""),
        ("complications", "acompany", list, []),
        ("cost_money", "cost_money", str, ""),
        ("category", "category", list, []),
        ("check_items", "check", list, []),
    ]


def import_diseases(conn, force: bool = False):
    """将 medical.json 流式导入 MySQL"""
    cursor = conn.cursor()

    # 建表
    if force:
        cursor.execute("DROP TABLE IF EXISTS diseases")
        print("已删除旧表")
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    print("表已就绪: diseases")

    # 检查已有数量
    cursor.execute("SELECT COUNT(*) FROM diseases")
    existing = cursor.fetchone()[0]
    if existing > 0:
        print(f"表中已有 {existing} 条记录，将跳过已存在的记录")
    else:
        print("表为空，开始导入...")

    # JSONL 文件路径
    json_file = BASE_DIR / "knowledge_base" / "medical.json"
    if not json_file.exists():
        print(f"错误: 数据文件不存在 {json_file}")
        sys.exit(1)

    fields = get_disease_fields()
    columns = [f[0] for f in fields]
    placeholders = ", ".join(["%s"] * len(fields))
    insert_sql = f"INSERT INTO diseases ({', '.join(columns)}) VALUES ({placeholders})"

    # 先拿到已有名称集合（用于跳重复）
    cursor.execute("SELECT name FROM diseases")
    existing_names = {row[0] for row in cursor.fetchall()}

    total, imported, skipped = 0, 0, 0
    batch_values = []

    with open(json_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                print(f"  跳过无效行 #{total}")
                continue

            name = d.get("name", "")
            if name in existing_names:
                skipped += 1
                continue

            values = []
            for col_name, json_key, typ, default in fields:
                val = d.get(json_key, default)
                if typ is list:
                    val = json.dumps(val, ensure_ascii=False)
                elif typ is str and val is None:
                    val = ""
                values.append(val)

            batch_values.append(values)

            if len(batch_values) >= 200:
                cursor.executemany(insert_sql, batch_values)
                conn.commit()
                imported += len(batch_values)
                print(f"  已导入 {imported} 条...")
                batch_values = []

    # 最后一批
    if batch_values:
        cursor.executemany(insert_sql, batch_values)
        conn.commit()
        imported += len(batch_values)

    print(f"\n导入完成: 共 {total} 条, 新导入 {imported} 条, 跳过 {skipped} 条, 总计 {imported + existing} 条")


def show_status(conn):
    """显示当前疾病表状态"""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM diseases")
        count = cursor.fetchone()[0]
        print(f"疾病表记录数: {count}")
        if count > 0:
            cursor.execute("SELECT name FROM diseases LIMIT 3")
            print("示例疾病: " + ", ".join(row[0] for row in cursor.fetchall()))
    except Exception as e:
        print(f"表不存在或无法访问: {e}")


# ---- 入口 ----------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="初始化 medical.json → MySQL diseases 表")
    parser.add_argument("--force", action="store_true", help="删除旧表并重建")
    parser.add_argument("--status", action="store_true", help="仅查看表状态，不导入")
    args = parser.parse_args()

    print("=" * 50)
    print("医疗知识库 — 疾病表初始化")
    print("=" * 50)

    try:
        conn = get_connection()
    except Exception as e:
        print(f"数据库连接失败: {e}")
        sys.exit(1)

    try:
        if args.status:
            show_status(conn)
        else:
            import_diseases(conn, force=args.force)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
