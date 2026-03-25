import pandas as pd
from bs4 import BeautifulSoup
import os

def extract_holdings(html_path, csv_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    
    table = soup.find('table')
    if not table:
        print("No table found in HTML")
        return

    rows = []
    tbody = soup.find('tbody', id='tabBody')
    if not tbody:
        tbody = table.find('tbody')
    
    for tr in tbody.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) < 11:
            continue
            
        # 证券代码 (第1列)
        ts_code = tds[0].get_text(strip=True)
        # 证券名称 (第2列)
        name = tds[1].get_text(strip=True)
        # 持仓数量 (第3列)
        hold_count = int(tds[2].get_text(strip=True))
        # 可用数量 (第4列)
        available_count = int(tds[3].get_text(strip=True))
        # 成本价 (第5列)
        cost_price = float(tds[4].get_text(strip=True))
        # 当前价 (第6列)
        current_price = float(tds[5].get_text(strip=True))
        # 最新市值 (第7列)
        market_value = float(tds[6].get_text(strip=True))
        # 持仓盈亏 (第8列)
        profit_loss = float(tds[7].get_text(strip=True))
        # 持仓盈亏比例 (第9列)
        profit_loss_ratio = tds[8].get_text(strip=True)
        # 当日盈亏 (第10列)
        daily_profit_loss = float(tds[9].get_text(strip=True))
        # 当日盈亏比例 (第11列)
        daily_profit_loss_ratio = tds[10].get_text(strip=True)

        if hold_count > 0:
            rows.append({
                '证券代码': ts_code,
                '证券名称': name,
                '持仓数量': hold_count,
                '可用数量': available_count,
                '成本价': cost_price,
                '当前价': current_price,
                '最新市值': market_value,
                '持仓盈亏': profit_loss,
                '持仓盈亏比例': profit_loss_ratio,
                '当日盈亏': daily_profit_loss,
                '当日盈亏比例': daily_profit_loss_ratio
            })
    
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"Successfully extracted {len(df)} holdings to {csv_path}")

if __name__ == "__main__":
    extract_holdings('output/hold.html', 'output/holdings.csv')
