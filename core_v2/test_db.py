import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def test_db():
    mysql_url = os.getenv("MYSQL_URL")
    print(f"Testing DB connection to {mysql_url}...")
    engine = create_engine(mysql_url)
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1")).scalar()
            print(f"Connection successful! Result: {res}")
            
            trade_date = conn.execute(text("SELECT MAX(trade_date) FROM stock_daily")).scalar()
            print(f"Latest trade date: {trade_date}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_db()
