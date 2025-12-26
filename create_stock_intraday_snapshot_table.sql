-- ============================================
-- 盘中快照表建表语句（方案 A）
-- 用途：
-- - 每分钟落一次“盘中快照”，保留盘中轨迹，避免 stock_daily 被反复覆盖后丢失路径
-- - 适合日线策略的盘中辅助、盘中回放、盘中风控触发点记录等
--
-- 数据来源：
-- - 东方财富日线级 K 线接口的“最新一根”（盘中动态变化）
--
-- 设计说明：
-- - bar_time：按分钟对齐（秒置 0），同一分钟写多次会覆盖（ON DUPLICATE KEY UPDATE）
-- - trade_date：对应东财返回的日期（YYYY-MM-DD）
-- - close 字段代表“盘中最新价”（东财该接口第 2 位为收盘/当前）
-- ============================================

CREATE TABLE IF NOT EXISTS stock_intraday_snapshot (
    -- 证券代码（6 位纯数字，如 159840）
    ts_code VARCHAR(10) NOT NULL COMMENT '证券代码（6 位）',

    -- 快照时间（北京时间，按分钟对齐）
    bar_time DATETIME NOT NULL COMMENT '快照时间（北京时间，分钟级）',

    -- 对应的交易日期（来自东财最新一根日线的日期字段）
    trade_date DATE NOT NULL COMMENT '交易日期（来自东财）',

    -- 当日价格/成交相关（来自东财“最新一根日线”，盘中会动态变化）
    open DECIMAL(10, 4) COMMENT '今开',
    high DECIMAL(10, 4) COMMENT '当日最高（盘中动态）',
    low DECIMAL(10, 4) COMMENT '当日最低（盘中动态）',
    close DECIMAL(10, 4) COMMENT '盘中最新价（东财 close/当前）',
    vol BIGINT COMMENT '成交量（手，盘中累计）',
    amount DECIMAL(20, 4) COMMENT '成交额（千元，盘中累计）',
    pct_chg DECIMAL(8, 4) COMMENT '涨跌幅（%）',

    -- 元数据
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    -- 主键：同一标的 + 同一分钟唯一
    PRIMARY KEY (ts_code, bar_time),

    -- 常用索引
    INDEX idx_trade_date (trade_date),
    INDEX idx_bar_time (bar_time),
    INDEX idx_code_date (ts_code, trade_date)
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci
COMMENT='盘中分钟快照表（方案A）';


