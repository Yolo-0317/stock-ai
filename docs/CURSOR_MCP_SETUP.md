## 在 Cursor 里接入 `tushare_mcp.py`（MCP Server）

本项目的 `tushare_mcp.py` 内置了 MCP Server（`FastMCP("TushareStockAdvisor")`），可以作为 Cursor 的 MCP 工具接入使用。

### 方式：stdio（推荐）

Cursor 会启动一个本地进程，并通过 stdio 与其通信。

### 1) 准备环境变量（建议）

至少需要（按你的使用场景）：
- **`MYSQL_URL`**：读取 MySQL 数据（如 `mysql+pymysql://user:pass@localhost:3306/stock_data`）
- **`DEEPSEEK_API_KEY`**：启用 AI 分析（可选）
- **`TUSHARE_TOKEN`**：启用 Tushare pro 数据源（可选）

你可以在 Cursor 的 MCP server 配置里填写 `env`，或依赖你系统已配置的环境变量。
  
**安全提示**：不要把真实的 `DEEPSEEK_API_KEY` / `TUSHARE_TOKEN` 写进仓库文件（包括示例 JSON）。建议只填在 Cursor 的本地 MCP 配置里，或放在系统环境变量中。

### 2) 在 Cursor 配置 MCP Server（推荐用 .venv）

在 Cursor 的 MCP 设置里新增一个 server（名称随意），**直接用项目的 `.venv/bin/python`**（这样项目的所有依赖 `mcp`、`tushare`、`pandas` 等都能正常加载）：

```json
{
  "mcpServers": {
    "tushare-stock-advisor": {
      "command": "/Users/yolo/dev/yolo/stock-ai/.venv/bin/python",
      "args": [
        "/Users/yolo/dev/yolo/stock-ai/tushare_mcp.py"
      ],
      "env": {
        "MYSQL_URL": "mysql+pymysql://user:pass@localhost:3306/stock_data",
        "DEEPSEEK_API_KEY": "YOUR_KEY",
        "TUSHARE_TOKEN": "YOUR_TOKEN",
        "TOTAL_CAPITAL_CNY": "10000"
      }
    }
  }
}
```

注意：
- `command` 和 `args` 里的路径建议用 **绝对路径**（避免 Cursor 启动时 cwd 不同导致找不到文件）。
- `env` 里的敏感信息请用你自己的值；如果不想写在配置里，也可以不填，改成系统环境变量。

### 3) 备选：用 uv run

如果你更习惯用 `uv`，可以改成：

```json
{
  "mcpServers": {
    "tushare-stock-advisor": {
      "command": "/opt/anaconda3/bin/uv",
      "args": [
        "run",
        "python",
        "/Users/yolo/dev/yolo/stock-ai/tushare_mcp.py"
      ],
      "env": {
        "MYSQL_URL": "mysql+pymysql://user:pass@localhost:3306/stock_data"
      }
    }
  }
}
```

注意：`uv` 需要用绝对路径（Cursor 启动时 PATH 可能不包含它）。

### 4) 验证

配置完成后，Cursor 的 MCP 工具列表中应出现该 server 的工具（来自 `tushare_mcp.py` 里 `@mcp.tool()` 注册的方法）。
