# Stock Analysis 个股分析系统

这是一个基于现有量化分析脚本的前后端分离项目。

## 项目结构

- `backend/`: Python FastAPI 后端，封装了 `tushare_mcp.py` 中的分析逻辑。
- `frontend/`: Vue 3 + Vant UI 前端，提供 H5 移动端适配的交互界面。

## Docker 部署

确保已安装 Docker 和 Docker Compose。

### 1. 启动服务

在 `stock_analysis` 目录下运行：

```bash
docker-compose up --build -d
```

### 2. 访问系统

- **前端 H5 界面**: [http://localhost:3301](http://localhost:3301)
- **后端 API**: [http://localhost:3302](http://localhost:3302)

### 3. 注意事项

- Docker 容器会自动挂载根目录下的 `.env` 文件。
- 后端容器挂载了必要的脚本文件以复用现有逻辑。

## 功能说明

- **AI 深度分析**: 调用 DeepSeek API 结合历史与盘中数据进行深度研判。
- **盘中信号**: 结合 MySQL 历史数据与东财实时行情，给出 MA5/MA20 均线信号。
- **实时均线**: 纯实时行情分析，快速给出当前买卖建议。

## 注意事项

- 后端运行时需要读取根目录下的 `.env` 文件，请确保 `TUSHARE_TOKEN`、`MYSQL_URL` 和 `DEEPSEEK_API_KEY` 已正确配置。
- 前端通过 Axios 访问 `http://localhost:8000`，请确保后端服务已启动。
