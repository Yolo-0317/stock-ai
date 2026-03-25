import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_akshare_data import get_stock_fundamental

if __name__ == "__main__":
    code = "600873"
    print(f"Testing fundamental for {code}...")
    res = get_stock_fundamental(code)
    print(f"Result: {res}")
