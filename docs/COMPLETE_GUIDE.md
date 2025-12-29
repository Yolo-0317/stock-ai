# 📈 完整交易系统使用指南

## 🎯 系统概览

本系统提供**三位一体**的股票交易辅助功能，帮助你在交易的各个阶段做出明智决策：

| 功能 | 时间 | 用途 | 脚本 | 通知 |
|------|------|------|------|------|
| **盘前分析** 🌅 | 8:30-9:00 | 制定今日交易计划 | `run_premarket_analysis.py` | 仅日志 |
| **盘中监控** 📊 | 9:30-15:00 | 实时把握交易时机 | `monitor_intraday_signals.py` | 飞书推送 |
| **盘后复盘** 🌙 | 15:30-16:00 | 总结经验，展望明日 | `run_aftermarket_analysis.py` | 仅日志 |

---

## 🚀 快速开始

### 1. 环境配置

确保 `.env` 文件已配置：

```bash
# MySQL 数据库连接
MYSQL_URL=mysql+pymysql://user:password@host:port/database

# DeepSeek API Key
DEEPSEEK_API_KEY=your_deepseek_api_key

# 飞书机器人 Webhook (可选)
LARK_BOT_URL=your_feishu_webhook_url
```

### 2. 安装依赖

```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp
uv sync
```

### 3. 配置关注股票

编辑对应的脚本文件，修改配置：

```python
CODES = ["159218", "159840"]  # 关注的股票
POSITION_COSTS = {
    "159218": 1.197,  # 持仓成本
    "159840": 0.869,
}
POSITION_RATIOS = {
    "159218": 0.2374,  # 仓位比例
    "159840": 0.1058,
}
```

---

## 📅 每日使用流程

### 🌅 早上 8:45 - 盘前准备

**手动运行：**
```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp
uv run python scripts/run_premarket_analysis.py
```

**查看内容：**
- ✅ 昨日走势回顾
- ✅ 当前趋势判断（上升/下降/震荡）
- ✅ 今日关键价位（支撑/压力）
- ✅ 今日操作策略

**输出示例：**
```
### 🌅 盘前分析: 159218
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **昨日收盘** (2025-12-26)
   收盘价: 1.625  |  涨跌: 3.64%
   
**趋势判断**: 上升趋势

**关键价位**:
- 支撑位: 1.555, 1.511 (MA5)
- 压力位: 1.637, 1.650

**今日策略**:
- 开盘建议: 观望为主，等待回调
- 买入价位: 1.55-1.57 区间
- 卖出价位: 1.64 以上
```

---

### 📊 盘中 9:30-15:00 - 实时监控

**启动监控：**
```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp
uv run python scripts/monitor_intraday_signals.py
```

**监控内容：**
- ⏱️ 每分钟刷新一次
- 📈 实时价格和技术指标
- 🤖 AI 给出具体操作指令（买入/卖出/暂不操作）
- 📱 重要信号自动推送飞书

**输出示例：**
```
==================================================
⏰ 10:15:30  |  159218
==================================================
🔴 卖出  【立即卖出】
──────────────────────────────────────────────────
💰 执行价格: 1.625
📊 建议数量: 50.0%
🛡️ 止损价格: 1.640
🎯 目标价格: 1.510
──────────────────────────────────────────────────
💡 原因: 价格已大幅偏离均线，日内冲高后高位滞涨
==================================================
```

**配置说明：**
```python
use_t_signal = True          # 使用 T+0 做T信号
print_all_signals = True     # 打印所有信号（包括"暂不操作"）
log_ai_detail = True         # 日志记录完整AI分析
enable_feishu = True         # 启用飞书通知（盘中实时推送）
```

> **💡 通知策略**：
> - **盘中监控**：重要信号实时推送飞书，方便及时把握交易机会
> - **盘前/盘后**：仅记录日志，不推送通知（避免信息过载）

---

### 🌙 下午 15:45 - 盘后复盘

**手动运行：**
```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp
uv run python scripts/run_aftermarket_analysis.py
```

**查看内容：**
- ✅ 今日走势复盘
- ✅ 技术形态变化
- ✅ 明日走势展望
- ✅ 操作建议（持仓者/空仓者）

**输出示例：**
```
### 🌙 盘后分析: 159218
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **今日收盘** (2025-12-26)
   收盘价: 1.610  |  涨跌: -0.92%

**今日总结**: 冲高回落，高位震荡整固

**明日展望**:
- 预期方向: 震荡整理，可能继续回调
- 关键支撑: 1.585, 1.528 (MA5)
- 关键压力: 1.635, 1.650

**操作建议**:
- 持仓者: 继续持有，设置止盈1.64
- 空仓者: 等待回调至 1.55-1.57 区间
```

---

## ⚙️ 自动化设置（定时任务）

### macOS (launchd)

#### 盘前分析（每日 8:45 自动运行）

创建配置文件：
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
        <string>scripts/run_premarket_analysis.py</string>
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

#### 盘后分析（每日 15:45 自动运行）

创建配置文件：
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
        <string>scripts/run_aftermarket_analysis.py</string>
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
# 查看任务状态
launchctl list | grep stock

# 停止任务
launchctl unload ~/Library/LaunchAgents/com.stock.premarket.plist
launchctl unload ~/Library/LaunchAgents/com.stock.aftermarket.plist

# 重新加载
launchctl load ~/Library/LaunchAgents/com.stock.premarket.plist
launchctl load ~/Library/LaunchAgents/com.stock.aftermarket.plist
```

---

## 📂 日志管理

### 查看日志

```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp

# 盘前分析日志
cat logs/premarket_$(date +%Y%m%d).log

# 盘中监控日志（包含完整AI分析）
cat logs/monitor_$(date +%Y%m%d).log

# 盘后分析日志
cat logs/aftermarket_$(date +%Y%m%d).log

# 实时查看
tail -f logs/monitor_$(date +%Y%m%d).log
```

### 日志清理

```bash
# 删除 30 天前的日志
find logs/ -name "*.log" -mtime +30 -delete

# 压缩旧日志
gzip logs/*_202512*.log
```

---

## 💡 使用建议

### 交易纪律

1. **盘前必做**
   - ✅ 查看盘前分析，制定交易计划
   - ✅ 在关键价位设置价格提醒
   - ✅ 明确今日的止盈止损位

2. **盘中执行**
   - ✅ 严格按照计划执行
   - ✅ 关注 AI 信号，但不盲目跟随
   - ✅ 保持纪律，不追涨杀跌

3. **盘后复盘**
   - ✅ 总结今日操作得失
   - ✅ 记录心得和教训
   - ✅ 为明日做准备

### AI 信号使用原则

1. **参考，不盲从**
   - AI 是辅助工具，最终决策权在你
   - 结合自己的判断和市场经验

2. **关注趋势，不抓短线**
   - 中长期趋势比短期波动更重要
   - 不要频繁交易

3. **风险第一**
   - 严格止损，保护本金
   - 合理控制仓位
   - 不满仓操作

---

## 🔧 故障排查

### 1. API 调用失败

```bash
# 检查环境变量
cat .env | grep DEEPSEEK_API_KEY

# 测试 API
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('DEEPSEEK_API_KEY'))"
```

### 2. 数据库连接失败

```bash
# 检查 MySQL 连接
python -c "
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv
load_dotenv()
engine = create_engine(os.getenv('MYSQL_URL'))
print('MySQL 连接成功')
"
```

### 3. 飞书通知失败

```bash
# 测试飞书 webhook
python -c "
from feishu_notice import send_to_lark
send_to_lark('测试消息')
"
```

### 4. 定时任务未执行

```bash
# 查看定时任务日志
cat logs/premarket.err.log
cat logs/aftermarket.err.log

# 手动测试
uv run python scripts/run_premarket_analysis.py
```

---

## 📚 文档索引

- [QUICKSTART.md](./QUICKSTART.md) - 快速开始
- [DAILY_ANALYSIS_GUIDE.md](./DAILY_ANALYSIS_GUIDE.md) - 盘前/盘后分析详解
- [T_TRADING_GUIDE.md](./T_TRADING_GUIDE.md) - T+0 交易指南
- [AI_SIGNAL_GUIDE.md](./AI_SIGNAL_GUIDE.md) - AI 信号说明
- [CONFIG_GUIDE.md](./CONFIG_GUIDE.md) - 配置指南
- [LOG_AI_DETAIL.md](./LOG_AI_DETAIL.md) - AI 详细日志
- [LOGGING_GUIDE.md](./LOGGING_GUIDE.md) - 日志系统说明

---

## 📊 系统架构

```
┌─────────────────────────────────────────────────┐
│              数据采集层                          │
├─────────────────────────────────────────────────┤
│  • Eastmoney 实时数据                            │
│  • MySQL 历史日线/分钟线数据                     │
│  • Tushare 数据接口（可选）                      │
└────────────┬────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────┐
│              分析层                              │
├─────────────────────────────────────────────────┤
│  • 技术指标计算 (MA5/MA20)                       │
│  • DeepSeek AI 分析                              │
│  • 信号生成逻辑                                  │
└────────────┬────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────┐
│              应用层                              │
├─────────────────────────────────────────────────┤
│  🌅 盘前分析  │  📊 盘中监控  │  🌙 盘后复盘   │
└────────────┬────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────┐
│              输出层                              │
├─────────────────────────────────────────────────┤
│  • 控制台输出（简洁）                            │
│  • 日志文件（详细）                              │
│  • 飞书通知（关键信号）                          │
└─────────────────────────────────────────────────┘
```

---

## 🎓 进阶使用

### 自定义持仓配置

根据实际持仓修改配置：

```python
POSITION_COSTS = {
    "159218": 1.197,    # 你的实际成本价
    "159840": 0.869,
}

POSITION_RATIOS = {
    "159218": 0.2374,   # 当前仓位比例（总资金的 23.74%）
    "159840": 0.1058,   # 当前仓位比例（总资金的 10.58%）
}
```

### 调整监控间隔

修改 `monitor_intraday_signals.py`：

```python
interval = 60.0  # 秒，60=每分钟检查一次
```

### 自定义交易时间

修改 `monitor_intraday_signals.py`：

```python
all_day = False  # False：只在交易时段运行
```

---

**完整的交易系统已就绪，祝你交易顺利！** 🚀📈

