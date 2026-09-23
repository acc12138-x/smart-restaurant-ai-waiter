-- ============================================
-- 同盛祥 · SQLite Schema v3.0
-- ============================================

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uid             TEXT UNIQUE NOT NULL,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    nickname        TEXT,
    points          INTEGER DEFAULT 0,
    level           TEXT DEFAULT '新客',
    disabled        INTEGER DEFAULT 0,
    created_at      TEXT,
    last_points_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_uid ON users(uid);

-- 订单表
CREATE TABLE IF NOT EXISTS orders (
    id          TEXT PRIMARY KEY,
    uid         TEXT,
    table_no    TEXT,
    items       TEXT NOT NULL,
    total       REAL NOT NULL,
    status      TEXT DEFAULT 'pending',
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_uid ON orders(uid);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);

-- 留言表
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT,
    content     TEXT NOT NULL,
    read        INTEGER DEFAULT 0,
    created_at  TEXT
);

-- AI 对话记录
CREATE TABLE IF NOT EXISTS chat_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT,
    question    TEXT,
    answer      TEXT,
    intent      TEXT,
    elapsed_ms  REAL,
    is_hit      INTEGER DEFAULT 1,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_chat_uid ON chat_logs(uid);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_logs(created_at);

-- 埋点事件
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event       TEXT,
    payload     TEXT,
    uid         TEXT,
    ip          TEXT,
    ua          TEXT,
    date        TEXT,
    time        TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_event ON events(event);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);

-- 后台管理员
CREATE TABLE IF NOT EXISTS admin_users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT DEFAULT 'owner',
    created_at      TEXT
);

-- 后台操作日志
CREATE TABLE IF NOT EXISTS admin_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id    INTEGER,
    action      TEXT,
    target      TEXT,
    detail      TEXT,
    ip          TEXT,
    created_at  TEXT
);

-- 桌码
CREATE TABLE IF NOT EXISTS tables (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_no    TEXT UNIQUE NOT NULL,
    scan_count  INTEGER DEFAULT 0,
    created_at  TEXT
);

-- 知识库版本历史
CREATE TABLE IF NOT EXISTS kb_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL,
    content     TEXT,
    version     INTEGER,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_kb_filename ON kb_history(filename);

-- 积分流水
CREATE TABLE IF NOT EXISTS points_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT,
    change      INTEGER,
    reason      TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_points_uid ON points_log(uid);
-- 系统设置（v3.7）
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT
);

-- 对话历史（v3.8，跨会话持久化）
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT,
    ts          REAL
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_uid ON chat_sessions(uid, id);

-- 应用日志（v3.8）
CREATE TABLE IF NOT EXISTS app_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT,
    logger      TEXT,
    message     TEXT,
    traceback   TEXT,
    elapsed_ms  REAL,
    url         TEXT,
    method      TEXT,
    ip          TEXT,
    uid         TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_app_logs_level ON app_logs(level);
CREATE INDEX IF NOT EXISTS idx_app_logs_created ON app_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_app_logs_elapsed ON app_logs(elapsed_ms);
