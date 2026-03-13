import csv
import re
import os

def html_to_csv_simple(html_path, csv_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Simple regex-based extraction to avoid BeautifulSoup issues if any
    # Each row is between <tr> and </tr>
    rows = re.findall(r'<tr.*?>([\s\S]*?)</tr>', content)
    
    data = []
    for row in rows:
        # Each cell is between <td> and </td>
        cells = re.findall(r'<td.*?>([\s\S]*?)</td>', row)
        if len(cells) >= 9:
            # Clean HTML tags from cells
            clean_cells = [re.sub(r'<[^>]+>', '', cell).strip() for cell in cells]
            
            data.append({
                '证券代码': clean_cells[0],
                '证券名称': clean_cells[1],
                '证券数量': clean_cells[2],
                '可卖数量': clean_cells[3],
                '成本价': clean_cells[4],
                '当前价': clean_cells[5],
                '市值': clean_cells[6],
                '盈亏': clean_cells[7],
                '盈亏比例': clean_cells[8]
            })
            
    if data:
        keys = data[0].keys()
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(data)
        print(f"Successfully saved {len(data)} stocks to {csv_path}")
    else:
        print("No stock data found in the HTML file.")

if __name__ == "__main__":
    input_file = "/Users/yolo/dev/yolo/stock-ai/output/hold.html"
    output_file = "/Users/yolo/dev/yolo/stock-ai/output/holdings.csv"
    html_to_csv_simple(input_file, output_file)
