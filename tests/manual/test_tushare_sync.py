"""
测试 Tushare 日线数据同步功能

使用前确保设置环境变量：
- TUSHARE_TOKEN: Tushare API Token
- MYSQL_URL: MySQL 连接串

示例：
export TUSHARE_TOKEN="your_token"
export MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data"
uv run python tests/manual/test_tushare_sync.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

import os
from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)


def test_config():
    """测试配置是否正确"""
    print("=" * 80)
    print("测试 1：检查环境变量配置")
    print("=" * 80)

    tushare_token = os.getenv("TUSHARE_TOKEN")
    mysql_url = os.getenv("MYSQL_URL")

    if not tushare_token:
        print("❌ 未设置 TUSHARE_TOKEN 环境变量")
        return False

    if not mysql_url:
        print("❌ 未设置 MYSQL_URL 环境变量")
        return False

    print(f"✓ TUSHARE_TOKEN: {'*' * 10}{tushare_token[-6:]}")
    print(f"✓ MYSQL_URL: {mysql_url.split('@')[0]}@...")

    return True


def test_tushare_connection():
    """测试 Tushare API 连接"""
    print("\n" + "=" * 80)
    print("测试 2：测试 Tushare API 连接")
    print("=" * 80)

    try:
        import tushare as ts

        token = os.getenv("TUSHARE_TOKEN")
        ts.set_token(token)
        pro = ts.pro_api()

        # 测试获取股票列表（只取 5 条）
        df = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")

        if df is None or df.empty:
            print("❌ 获取股票列表失败")
            return False

        print(f"✓ Tushare API 连接正常")
        print(f"✓ 股票总数: {len(df)}")
        print(f"\n示例股票（前 5 只）：")
        for _, row in df.head(5).iterrows():
            print(f"  - {row['ts_code']}: {row['name']}")

        return True

    except Exception as e:
        print(f"❌ Tushare API 连接失败: {e}")
        return False


def test_mysql_connection():
    """测试 MySQL 数据库连接"""
    print("\n" + "=" * 80)
    print("测试 3：测试 MySQL 数据库连接")
    print("=" * 80)

    try:
        from sqlalchemy import create_engine, text

        mysql_url = os.getenv("MYSQL_URL")
        engine = create_engine(mysql_url, pool_pre_ping=True)

        with engine.connect() as conn:
            # 测试连接
            result = conn.execute(text("SELECT VERSION()")).fetchone()
            print(f"✓ MySQL 连接正常")
            print(f"✓ MySQL 版本: {result[0]}")

            # 检查表是否存在
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*) as cnt 
                    FROM information_schema.tables 
                    WHERE table_name = 'stock_daily'
                    """
                )
            ).fetchone()

            if result[0] > 0:
                print(f"✓ stock_daily 表已存在")

                # 查询表中的记录数
                result = conn.execute(text("SELECT COUNT(*) FROM stock_daily")).fetchone()
                print(f"✓ 当前记录数: {result[0]:,}")

                # 查询股票数量
                result = conn.execute(
                    text("SELECT COUNT(DISTINCT ts_code) FROM stock_daily")
                ).fetchone()
                print(f"✓ 股票数量: {result[0]:,}")

                # 查询最新日期
                result = conn.execute(
                    text("SELECT MAX(trade_date) FROM stock_daily")
                ).fetchone()
                if result[0]:
                    print(f"✓ 最新日期: {result[0]}")
            else:
                print("⚠️  stock_daily 表不存在，请先执行建表 SQL")
                print("   sql/create_stock_daily_table.sql")

        return True

    except Exception as e:
        print(f"❌ MySQL 连接失败: {e}")
        return False


def test_sync_sample():
    """测试同步单只股票"""
    print("\n" + "=" * 80)
    print("测试 4：测试同步单只股票（000001.SZ）")
    print("=" * 80)

    try:
        import subprocess

        # 运行同步脚本（只同步一只股票）
        cmd = [
            "uv",
            "run",
            "python",
            "scripts/sync_tushare_daily_to_mysql.py",
            "--codes",
            "000001.SZ",
            "--mode",
            "incremental",
        ]

        print(f"执行命令: {' '.join(cmd)}")
        print("-" * 80)

        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2]
        )

        print(result.stdout)

        if result.returncode == 0:
            print("✓ 同步测试成功")
            return True
        else:
            print(f"❌ 同步测试失败")
            print(result.stderr)
            return False

    except Exception as e:
        print(f"❌ 同步测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n")
    print("🧪 Tushare 日线数据同步功能测试")
    print("=" * 80)

    tests = [
        ("配置检查", test_config),
        ("Tushare API", test_tushare_connection),
        ("MySQL 数据库", test_mysql_connection),
        ("同步功能", test_sync_sample),
    ]

    results = []

    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            results.append((name, False))

    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 测试结果汇总")
    print("=" * 80)

    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status} - {name}")

    all_passed = all(success for _, success in results)

    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 所有测试通过！可以开始使用同步功能了")
        print("\n建议下一步：")
        print("1. 全量初始化：")
        print("   uv run python scripts/sync_tushare_daily_to_mysql.py --mode full")
        print("\n2. 设置定时任务：")
        print("   参考 docs/TUSHARE_SYNC_GUIDE.md")
    else:
        print("⚠️  部分测试失败，请检查配置和环境")

    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

