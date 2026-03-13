import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

from dotenv import load_dotenv
load_dotenv()

from scripts.sync_tushare_daily_to_mysql import sync_daily_data

if __name__ == "__main__":
    # 强制同步 000516.SZ 的历史数据
    from scripts.sync_tushare_daily_to_mysql import init_tushare, get_mysql_engine, fetch_daily_data, save_daily_data_to_db
    pro = init_tushare()
    engine = get_mysql_engine()
    df, _ = fetch_daily_data(pro, "000516.SZ", "20240101")
    if not df.empty:
        count = save_daily_data_to_db(engine, df, "000516.SZ")
        print(f"成功入库 {count} 条记录")
    else:
        print("未获取到数据")
