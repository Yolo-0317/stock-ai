import pandas as pd
from bs4 import BeautifulSoup
import os

def html_to_csv(html_path, csv_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Wrap in a table structure if it's just a tbody fragment
    if '<tbody>' in html_content and '<table>' not in html_content:
        html_content = f"<table>{html_content}</table>"
        
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table')
    
    data = []
    rows = table.find_all('tr')
    
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 9:
            # Extracting relevant fields based on the HTML structure
            stock_code = cols[0].get_text(strip=True)
            stock_name = cols[1].get_text(strip=True)
            total_amount = cols[2].get_text(strip=True)
            available_amount = cols[3].get_text(strip=True)
            cost_price = cols[4].get_text(strip=True)
            current_price = cols[5].get_text(strip=True)
            market_value = cols[6].get_text(strip=True)
            profit_loss = cols[7].get_text(strip=True)
            profit_loss_ratio = cols[8].get_text(strip=True)
            
            data.append({
                '证券代码': stock_code,
                '证券名称': stock_name,
                '证券数量': total_amount,
                '可卖数量': available_amount,
                '成本价': cost_price,
                '当前价': current_price,
                '市值': market_value,
                '盈亏': profit_loss,
                '盈亏比例': profit_loss_ratio
            })
            
    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"Successfully saved {len(df)} stocks to {csv_path}")

if __name__ == "__main__":
    input_file = "/Users/yolo/dev/yolo/stock-ai/output/hold.html"
    output_file = "/Users/yolo/dev/yolo/stock-ai/output/holdings.csv"
    html_to_csv(input_file, output_file)
