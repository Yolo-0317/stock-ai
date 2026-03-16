# 使用轻量级 Python镜像
FROM python:3.11-slim

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 设置工作目录
WORKDIR /app

# 设置 uv 使用国内 PyPI 镜像源加速下载
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 【核心修复】直接将依赖安装到系统环境
# 这样即使 /app 目录被 docker-compose 的 volumes 挂载覆盖，依赖依然在系统路径中可用
RUN uv pip install --system --no-cache mcp fastapi uvicorn pandas sqlalchemy pymysql python-dotenv requests tushare redis

# 复制源代码
COPY . .

# 暴露后端端口
EXPOSE 8000

# 启动命令：直接使用系统 python 运行
CMD ["python", "main.py"]
