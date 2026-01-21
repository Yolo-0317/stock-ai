#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比两天选股结果的差异
"""

import pandas as pd
from pathlib import Path

def compare_selections(date1: str, date2: str):
    """对比两天的选股结果"""
    
    output_dir = Path(__file__).parent.parent / "output"
    
    # 读取两天的选股结果
    file1 = output_dir / f"stock_selection_ma5_{date1}.csv"
    file2 = output_dir / f"stock_selection_ma5_{date2}.csv"
    
    df1 = pd.read_csv(file1)
    df2 = pd.read_csv(file2)
    
    # 提取股票代码
    codes1 = set(df1['代码'].astype(str))
    codes2 = set(df2['代码'].astype(str))
    
    # 计算差异
    common = codes1 & codes2
    only_in_date1 = codes1 - codes2
    only_in_date2 = codes2 - codes1
    
    print("=" * 80)
    print(f"📊 选股结果对比：{date1} vs {date2}")
    print("=" * 80)
    
    print(f"\n📈 {date1} 选出股票数：{len(codes1)}")
    print(f"📈 {date2} 选出股票数：{len(codes2)}")
    
    print(f"\n🔄 共同出现：{len(common)} 只（{len(common)/len(codes1)*100:.1f}%）")
    if common:
        common_df1 = df1[df1['代码'].astype(str).isin(common)][['排名', '代码', '名称', '收盘价', '今日涨幅%', '量比', '成交额(万)']]
        common_df2 = df2[df2['代码'].astype(str).isin(common)][['排名', '代码', '名称', '收盘价', '今日涨幅%', '量比', '成交额(万)']]
        
        print(f"\n共同股票在 {date1} 的排名：")
        for _, row in common_df1.iterrows():
            print(f"  #{int(row['排名']):2d} {row['代码']} | 价格{row['收盘价']:6.2f} | 涨幅{row['今日涨幅%']:5.2f}% | 量比{row['量比']:4.2f} | 成交额{row['成交额(万)']/10000:.1f}亿")
        
        print(f"\n共同股票在 {date2} 的排名：")
        for _, row in common_df2.iterrows():
            print(f"  #{int(row['排名']):2d} {row['代码']} | 价格{row['收盘价']:6.2f} | 涨幅{row['今日涨幅%']:5.2f}% | 量比{row['量比']:4.2f} | 成交额{row['成交额(万)']/10000:.1f}亿")
    
    print(f"\n❌ 只在 {date1} 出现：{len(only_in_date1)} 只（{len(only_in_date1)/len(codes1)*100:.1f}%）")
    if only_in_date1:
        only_df1 = df1[df1['代码'].astype(str).isin(only_in_date1)][['排名', '代码', '名称', '收盘价', '今日涨幅%', '量比', '成交额(万)']]
        print("\nTop 10:")
        for _, row in only_df1.head(10).iterrows():
            print(f"  #{int(row['排名']):2d} {row['代码']} | 价格{row['收盘价']:6.2f} | 涨幅{row['今日涨幅%']:5.2f}% | 量比{row['量比']:4.2f} | 成交额{row['成交额(万)']/10000:.1f}亿")
    
    print(f"\n✅ 只在 {date2} 出现：{len(only_in_date2)} 只（{len(only_in_date2)/len(codes2)*100:.1f}%）")
    if only_in_date2:
        only_df2 = df2[df2['代码'].astype(str).isin(only_in_date2)][['排名', '代码', '名称', '收盘价', '今日涨幅%', '量比', '成交额(万)']]
        print("\nTop 10:")
        for _, row in only_df2.head(10).iterrows():
            print(f"  #{int(row['排名']):2d} {row['代码']} | 价格{row['收盘价']:6.2f} | 涨幅{row['今日涨幅%']:5.2f}% | 量比{row['量比']:4.2f} | 成交额{row['成交额(万)']/10000:.1f}亿")
    
    # 分析差异原因
    print("\n" + "=" * 80)
    print("🔍 差异分析")
    print("=" * 80)
    
    overlap_rate = len(common) / len(codes1) * 100
    
    if overlap_rate < 20:
        print("💡 结论：差异非常大（重叠率<20%）")
        print("\n可能原因：")
        print("  1. ✅ 策略非常敏感，每天选出的都是当天最符合启动条件的股票")
        print("  2. ✅ 市场轮动快，昨天启动的今天可能已经进入加速期，不再符合'启动初期'")
        print("  3. ✅ 说明策略不是选固定的股票池，而是动态捕捉每天的启动机会")
        print("  4. ⚠️  也意味着选出的股票可能只有1-2天的最佳买点窗口期")
        print("\n💡 操作建议：")
        print("  - 每天盘后及时运行策略，当天选出的当天就要准备第二天买入")
        print("  - 不要拖延，错过当天可能就错过最佳买点")
        print("  - 持有周期建议5-10天，及时止盈")
    elif overlap_rate < 50:
        print("💡 结论：差异较大（重叠率20-50%）")
        print("\n可能原因：")
        print("  1. 部分股票持续符合条件，但也有新股票不断进入启动期")
        print("  2. 策略动态性较强，能捕捉市场轮动")
    else:
        print("💡 结论：差异较小（重叠率>50%）")
        print("\n可能原因：")
        print("  1. 市场整体走势较为一致")
        print("  2. 同一批股票持续处于启动期")
    
    print("=" * 80)


if __name__ == "__main__":
    # 对比两天的选股结果
    import sys
    if len(sys.argv) == 3:
        compare_selections(sys.argv[1], sys.argv[2])
    else:
        # 默认对比昨天和今天
        compare_selections("20260109", "20260112")
