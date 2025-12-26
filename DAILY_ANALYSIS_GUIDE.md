# 📊 盘前/盘后 AI 分析指南

## 🎯 功能概述

新增了**盘前分析**和**盘后分析**功能，帮助你在关键时刻做出更好的决策：

### 🌅 盘前分析（开盘前）
- **运行时间**：每个交易日 8:30 - 9:00
- **目的**：基于昨日收盘数据，制定今日交易计划
- **输出方式**：控制台 + 日志文件（不推送飞书）
- **内容**：
  - 趋势判断（上升/下降/震荡）
  - 关键价位（支撑位/压力位）
  - 今日策略（开盘时应该做什么）
  - 详细分析（趋势、技术位置、动能）

### 🌙 盘后分析（收盘后）
- **运行时间**：每个交易日 15:30 - 16:00
- **目的**：复盘今日走势，展望明日机会
- **输出方式**：控制台 + 日志文件（不推送飞书）
- **内容**：
  - 今日总结（走势特点、量价关系）
  - 技术形态（收盘后的技术状态）
  - 明日展望（预期方向、关键价位）
  - 操作建议（持仓者/空仓者应对策略）

---

## 🚀 快速使用

### 1. 手动运行

#### 盘前分析
```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp

# 运行盘前分析
uv run python run_premarket_analysis.py
```

#### 盘后分析
```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp

# 运行盘后分析
uv run python run_aftermarket_analysis.py
```

### 2. 自动运行（定时任务）

#### macOS (使用 launchd)

创建盘前分析定时任务：
```bash
cat > ~/Library/LaunchAgents/com.stock.premarket.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stock.premarket</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/huan.yu/.local/bin/uv</string>
        <string>run</string>
        <string>python</string>
        <string>run_premarket_analysis.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/huan.yu/dev/demo/stock/tushare-mcp</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>45</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/huan.yu/dev/demo/stock/tushare-mcp/logs/premarket.out.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/huan.yu/dev/demo/stock/tushare-mcp/logs/premarket.err.log</string>
</dict>
</plist>
EOF

# 加载任务
launchctl load ~/Library/LaunchAgents/com.stock.premarket.plist
```

创建盘后分析定时任务：
```bash
cat > ~/Library/LaunchAgents/com.stock.aftermarket.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stock.aftermarket</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/huan.yu/.local/bin/uv</string>
        <string>run</string>
        <string>python</string>
        <string>run_aftermarket_analysis.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/huan.yu/dev/demo/stock/tushare-mcp</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>15</integer>
        <key>Minute</key>
        <integer>45</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/huan.yu/dev/demo/stock/tushare-mcp/logs/aftermarket.out.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/huan.yu/dev/demo/stock/tushare-mcp/logs/aftermarket.err.log</string>
</dict>
</plist>
EOF

# 加载任务
launchctl load ~/Library/LaunchAgents/com.stock.aftermarket.plist
```

#### 管理定时任务
```bash
# 查看任务列表
launchctl list | grep stock

# 卸载任务
launchctl unload ~/Library/LaunchAgents/com.stock.premarket.plist
launchctl unload ~/Library/LaunchAgents/com.stock.aftermarket.plist

# 重新加载任务
launchctl load ~/Library/LaunchAgents/com.stock.premarket.plist
launchctl load ~/Library/LaunchAgents/com.stock.aftermarket.plist
```

---

## ⚙️ 配置说明

### 修改关注股票和持仓信息

编辑 `run_premarket_analysis.py` 或 `run_aftermarket_analysis.py`：

```python
# 配置
CODES = ["159218", "159840"]  # 关注的股票
POSITION_COSTS = {
    "159218": 1.197,  # 持仓成本
    "159840": 0.869,
}
POSITION_RATIOS = {
    "159218": 0.2374,  # 仓位比例（0.0 - 1.0）
    "159840": 0.1058,
}

# 是否发送飞书通知
ENABLE_FEISHU = True
```

### 修改运行时间

编辑对应的 `.plist` 文件中的时间：

```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>8</integer>     <!-- 小时 (0-23) -->
    <key>Minute</key>
    <integer>45</integer>    <!-- 分钟 (0-59) -->
</dict>
```

---

## 📋 输出示例

### 🌅 盘前分析输出

```
### 🌅 盘前分析: 159218
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **昨日收盘** (20251225)
   收盘价: 1.625  |  涨跌: 3.64%
   日内区间: 1.555 ~ 1.637
   技术指标: MA5=1.5114, MA20=1.3730

**持仓信息**:
   成本价: 1.197  |  仓位: 23.7%
   浮动盈亏: +35.75%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **AI 盘前分析**：

**趋势判断**: 上升趋势

**关键价位**:
- 支撑位: 1.510（MA5 附近）
- 压力位: 1.640（昨日高点）

**今日策略**:
- 开盘建议: 观望为主，等待回调
- 买入价位: 如果回落至 1.55-1.57 区间，可考虑加仓
- 卖出价位: 如果冲高至 1.64 以上，可考虑减仓
- 风险提示: 短期涨幅较大，注意回调风险

**详细分析**:
1. 价格已连续上涨，短期涨幅较大，有回调需求
2. MA5 和 MA20 呈多头排列，中期趋势向好
3. 昨日放量上涨，显示多头力量强劲
4. 建议等待回调至支撑位再考虑加仓
5. 持仓者可继续持有，设置止盈位在 1.64

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 🌙 盘后分析输出

```
### 🌙 盘后分析: 159218
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **今日收盘** (20251226)
   收盘价: 1.610  |  涨跌: -0.92%
   日内区间: 1.585 ~ 1.635
   技术指标: MA5=1.5285, MA20=1.3845
   日内数据: （已采集 75 条分钟数据）

**持仓信息**:
   成本价: 1.197  |  仓位: 23.7%
   浮动盈亏: +34.50%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **AI 盘后复盘**：

**今日总结**: 冲高回落，高位震荡整固

**技术形态**: 价格仍位于 MA5 和 MA20 之上，上升趋势未变，但短期有调整需求

**明日展望**:
- 预期方向: 震荡整理，可能继续回调
- 关键支撑: 1.585（今日低点）、1.528（MA5）
- 关键压力: 1.635（今日高点）、1.650

**操作建议**:
- 持仓者: 继续持有，但注意止盈，若跌破 1.585 可考虑减仓
- 空仓者: 等待回调至 1.55-1.57 区间再考虑介入
- 风险提示: 短期连续上涨后有回调需求，注意控制仓位

**详细分析**:
1. 今日冲高至 1.635 后回落，显示上方压力较大
2. 收盘小幅下跌，但仍站稳在 MA5 之上，趋势未破
3. 分钟线显示日内多次冲高回落，多空分歧加大
4. 建议短线可考虑减仓，中线继续持有
5. 关注明日能否守住 1.585 支撑，若跌破需警惕调整加深

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 📂 查看历史分析

### 查看盘前分析日志
```bash
# 查看今天的盘前分析
cat logs/premarket_$(date +%Y%m%d).log

# 查看最近的盘前分析
ls -lt logs/premarket_*.log | head -5
```

### 查看盘后分析日志
```bash
# 查看今天的盘后分析
cat logs/aftermarket_$(date +%Y%m%d).log

# 查看最近的盘后分析
ls -lt logs/aftermarket_*.log | head -5
```

---

## 🔧 故障排查

### 问题 1：定时任务没有执行

```bash
# 检查任务是否加载
launchctl list | grep stock

# 查看错误日志
cat logs/premarket.err.log
cat logs/aftermarket.err.log

# 手动执行测试
uv run python run_premarket_analysis.py
```

### 问题 2：API 调用失败

```bash
# 检查环境变量
env | grep DEEPSEEK_API_KEY
env | grep MYSQL_URL

# 确保 .env 文件存在
cat .env
```

### 问题 3：飞书通知失败

```bash
# 检查飞书 webhook
env | grep LARK_BOT_URL

# 测试飞书通知
python -c "from feishu_notice import send_to_lark; send_to_lark('测试消息')"
```

---

## 💡 使用建议

### 盘前分析
1. **每日必看**：开盘前 15 分钟查看盘前分析
2. **制定计划**：根据分析结果制定今日操作计划
3. **设置提醒**：在关键价位设置价格提醒

### 盘后分析
1. **每日复盘**：收盘后查看盘后分析，总结今日得失
2. **调整策略**：根据分析结果调整明日策略
3. **记录感悟**：记录今日的操作和心得，不断改进

### 结合使用
- **盘前** + **盘中** + **盘后** = 完整的交易系统
- 盘前看方向，盘中抓时机，盘后做复盘
- 三位一体，提高交易胜率

---

## 📚 相关文档

- [QUICKSTART.md](./QUICKSTART.md) - 快速开始指南
- [T_TRADING_GUIDE.md](./T_TRADING_GUIDE.md) - T+0 交易指南
- [AI_SIGNAL_GUIDE.md](./AI_SIGNAL_GUIDE.md) - AI 信号说明
- [CONFIG_GUIDE.md](./CONFIG_GUIDE.md) - 配置指南
- [LOG_AI_DETAIL.md](./LOG_AI_DETAIL.md) - AI 详细日志说明

---

**每日坚持盘前盘后分析，让 AI 成为你的交易助手！** 📊✨

