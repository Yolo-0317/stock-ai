from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
import logging
import time
import redis
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("stock-analysis-api")

# 将项目根目录添加到 sys.path 以便导入现有脚本
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tushare_mcp import deepseek_trade_signal, intraday_trade_signal, realtime_trade_signal

app = FastAPI(title="Stock Analysis API")

# 配置 Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    logger.info(f"📡 已连接到 Redis: {REDIS_URL}")
except Exception as e:
    logger.error(f"❌ Redis 连接失败: {e}")
    r = None

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求中间件，用于记录所有请求的耗时
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    logger.info(f"{request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.2f}ms")
    return response

@app.get("/api/analyze/{code}")
async def analyze_stock(code: str, type: str = "deepseek"):
    """
    分析个股
    :param code: 股票代码, 如 000001
    :param type: 分析类型: deepseek, intraday, realtime
    """
    cache_key = f"stock_analysis:{code}:{type}"
    
    # 1. 尝试从 Redis 获取缓存
    if r:
        try:
            cached_report = r.get(cache_key)
            if cached_report:
                logger.info(f"🎯 命中 Redis 缓存: {cache_key}")
                return {"code": code, "type": type, "report": cached_report, "cached": True}
        except Exception as e:
            logger.warning(f"⚠️ 读取 Redis 缓存出错: {e}")

    logger.info(f"🚀 开始分析股票: {code}, 类型: {type}")
    try:
        start_time = time.time()
        if type == "deepseek":
            report = deepseek_trade_signal(code)
            expire_seconds = 3600 * 4  # AI 深度分析缓存 4 小时
        elif type == "intraday":
            report = intraday_trade_signal(code)
            expire_seconds = 3600  # 盘中信号缓存 1 小时
        elif type == "realtime":
            report = realtime_trade_signal(code)
            expire_seconds = 300   # 实时均线缓存 5 分钟
        else:
            logger.warning(f"❌ 无效的分析类型: {type}")
            raise HTTPException(status_code=400, detail="Invalid analysis type")
        
        duration = time.time() - start_time
        logger.info(f"✅ 分析完成: {code}, 耗时: {duration:.2f}s")

        # 2. 存入 Redis 缓存
        if r and report and "出错" not in report:
            try:
                r.setex(cache_key, expire_seconds, report)
                logger.info(f"💾 已存入 Redis 缓存: {cache_key}, 过期时间: {expire_seconds}s")
            except Exception as e:
                logger.warning(f"⚠️ 写入 Redis 缓存出错: {e}")

        return {"code": code, "type": type, "report": report, "cached": False}
    except Exception as e:
        logger.error(f"💥 分析出错: {code}, 错误详情: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    health = {"status": "ok", "redis": False}
    if r:
        try:
            r.ping()
            health["redis"] = True
        except:
            pass
    return health

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
