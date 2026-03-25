import asyncio
from playwright.async_api import async_playwright
import sys
import os

async def get_stock_data_playwright(code):
    """
    使用 Playwright 模拟浏览器访问东方财富获取深度基本面数据
    """
    async with async_playwright() as p:
        # 启动 Chromium 浏览器 (headless=True 表示后台运行)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()
        
        # 统一 6 位代码格式
        code_6 = "".join(filter(str.isdigit, str(code)))[:6]
        # 东方财富 F10 页面前缀：SH/SZ
        prefix = "SH" if code_6.startswith(('60', '688')) else "SZ"
        code_full = f"{prefix}{code_6}"
        
        # 1. 获取基本面 (F10 财务分析)
        f10_url = f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index?type=web&code={code_full}"
        print(f"🌐 正在抓取基本面: {f10_url}")
        
        try:
            await page.goto(f10_url, wait_until="networkidle", timeout=30000)
            # 等待主要指标表格加载
            await page.wait_for_selector("#zyzb_table", timeout=10000)
            
            # 提取数据
            # 东方财富的表格结构比较复杂，我们通过 text 匹配行，然后取第一列（最新报表）
            roe = await page.eval_on_selector("#zyzb_table tr:has-text('净资产收益率') td:nth-child(2)", "el => el.innerText")
            net_profit_growth = await page.eval_on_selector("#zyzb_table tr:has-text('净利润同比增长率') td:nth-child(2)", "el => el.innerText")
            debt_ratio = await page.eval_on_selector("#zyzb_table tr:has-text('资产负债率') td:nth-child(2)", "el => el.innerText")
            
            # 2. 获取资金面 (行情详情页)
            quote_url = f"https://quote.eastmoney.com/{prefix.lower()}{code_6}.html"
            print(f"🌐 正在抓取行情与资金面: {quote_url}")
            await page.goto(quote_url, wait_until="domcontentloaded")
            
            # 等待行情数据加载
            await page.wait_for_selector(".quote-price", timeout=10000)
            
            name = await page.locator(".quote-name").inner_text()
            price = await page.locator(".quote-price").inner_text()
            change_pct = await page.locator(".quote-change").inner_text()
            turnover = await page.locator("td:has-text('换手') + td").inner_text()
            pe_ttm = await page.locator("td:has-text('市盈(动)') + td").inner_text()

            result = {
                "代码": code_6,
                "名称": name.strip(),
                "最新价": price.strip(),
                "涨跌幅": change_pct.strip(),
                "换手率": turnover.strip(),
                "市盈率(动)": pe_ttm.strip(),
                "ROE(最新)": roe.strip(),
                "净利润增长率": net_profit_growth.strip(),
                "资产负债率": debt_ratio.strip()
            }
            
            print("\n" + "="*30)
            print(f"📊 {name} ({code_6}) 深度分析数据")
            print("="*30)
            for k, v in result.items():
                print(f"{k}: {v}")
            print("="*30)
            
            await browser.close()
            return result

        except Exception as e:
            print(f"❌ 抓取失败: {e}")
            await browser.close()
            return None

if __name__ == "__main__":
    # 默认分析梅花生物
    target_code = sys.argv[1] if len(sys.argv) > 1 else "600873"
    asyncio.run(get_stock_data_playwright(target_code))
