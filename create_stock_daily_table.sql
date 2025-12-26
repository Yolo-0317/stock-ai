-- ============================================
-- 股票日线行情表建表语句
-- 用途：存储 A 股日线行情数据，支持股票策略分析
-- 数据来源：Tushare API daily 接口
-- ============================================

-- 如果表已存在，先删除（谨慎使用，生产环境建议改为 ALTER TABLE）
-- DROP TABLE IF EXISTS stock_daily;

CREATE TABLE IF NOT EXISTS stock_daily (
    -- 股票代码（拆分后的纯代码，如：000001）
    ts_code VARCHAR(10) NOT NULL COMMENT '股票代码',
    
    -- 交易所代码（如：SZ, SH, BJ）
    exch_code VARCHAR(10) COMMENT '交易所代码',
    
    -- 交易日期
    trade_date DATE NOT NULL COMMENT '交易日期',
    
    -- 价格字段（使用 DECIMAL 保证精度，支持到分）
    -- 价格字段保留 4 位小数，便于 ETF/基金等小数精度更高的场景
    open DECIMAL(10, 4) COMMENT '开盘价',
    high DECIMAL(10, 4) COMMENT '最高价',
    low DECIMAL(10, 4) COMMENT '最低价',
    close DECIMAL(10, 4) COMMENT '收盘价',
    pre_close DECIMAL(10, 4) COMMENT '昨收价（除权价）',
    
    -- 涨跌相关字段
    change_amount DECIMAL(10, 4) COMMENT '涨跌额',
    pct_chg DECIMAL(8, 4) COMMENT '涨跌幅（%）',
    
    -- 成交相关字段（使用 BIGINT 或 DOUBLE，成交量可能很大）
    vol BIGINT COMMENT '成交量（手）',
    amount DECIMAL(20, 4) COMMENT '成交额（千元）',
    
    -- 元数据字段
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    -- 联合主键：股票代码 + 交易日期，确保唯一性
    PRIMARY KEY (ts_code, trade_date),
    
    -- 索引优化：用于常见查询场景
    -- 1. 按交易日期查询（用于获取某一天所有股票数据）
    INDEX idx_trade_date (trade_date),
    
    -- 2. 按股票代码查询（用于获取某只股票的历史数据）
    INDEX idx_ts_code (ts_code),
    
    -- 3. 按交易所和日期查询（用于筛选特定交易所的数据）
    INDEX idx_exch_date (exch_code, trade_date),
    
    -- 4. 按日期范围查询（用于策略分析中的时间范围筛选）
    INDEX idx_date_code (trade_date, ts_code)
    
) ENGINE=InnoDB 
  DEFAULT CHARSET=utf8mb4 
  COLLATE=utf8mb4_unicode_ci
  COMMENT='股票日线行情表';

-- ============================================
-- 索引说明：
-- 1. PRIMARY KEY (ts_code, trade_date): 联合主键，自动创建唯一索引
-- 2. idx_trade_date: 用于按日期查询所有股票（如：获取某一天的所有股票数据）
-- 3. idx_ts_code: 用于按股票代码查询历史数据（如：获取某只股票的所有历史数据）
-- 4. idx_exch_date: 用于按交易所和日期查询（如：获取上交所某一天的数据）
-- 5. idx_date_code: 用于按日期范围查询（如：获取某个时间段的数据，策略分析常用）
-- ============================================

-- ============================================
-- 使用说明：
-- 
-- 1. 每日更新：使用 INSERT ... ON DUPLICATE KEY UPDATE 实现有则更新，无则插入
-- 2. 历史数据更新：支持按单个日期或日期范围更新历史数据
-- 3. 查询优化：根据查询场景选择合适的索引
-- 
-- 示例查询：
-- - 获取某只股票的历史数据：SELECT * FROM stock_daily WHERE ts_code = '000001' ORDER BY trade_date DESC;
-- - 获取某一天所有股票：SELECT * FROM stock_daily WHERE trade_date = '2025-08-22';
-- - 获取日期范围数据：SELECT * FROM stock_daily WHERE trade_date BETWEEN '2025-08-01' AND '2025-08-22';
-- - 获取某只股票在日期范围的数据：SELECT * FROM stock_daily WHERE ts_code = '000001' AND trade_date BETWEEN '2025-08-01' AND '2025-08-22';
-- ============================================

