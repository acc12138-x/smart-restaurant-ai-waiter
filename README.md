# 同盛祥西安泡馍老店 · v3.9

> 面向中小餐饮的 **H5 点餐 + LLM 语义客服 + 后台运营** 一体化系统。从扫码点单到后厨接单的完整闭环，支持本地大模型零 API 成本运行。

[![Tests](https://github.com/acc12138-x/smart-restaurant-ai-waiter/actions/workflows/test.yml/badge.svg)](https://github.com/acc12138-x/smart-restaurant-ai-waiter/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-blue.svg)](https://www.sqlite.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 一句话介绍

一套面向中小餐馆的 **H5 点餐 + AI 客服 + 后台管理** 系统。顾客扫桌码进入点单、和 AI 客服对话下单；店家通过后台实时接单、管菜单、看数据。

支持**全本地大模型部署**（Ollama + Qwen），零 API 成本也能跑通；也能一键切换到阿里云 Qwen / DeepSeek / Kimi 等 OpenAI 兼容 API。

---

## v3.9 新增功能

| 模块 | 亮点 |
|---|---|
| ⚙️ **后台设置系统** | 数据库 key-value 配置，**模型热切换**（本地 Ollama ↔ 远程 OpenAI 兼容 API），改完立即生效不用重启 |
| 🤖 **AI 店长** | 从"小助手"升级为"金牌店长小同"人设，主动推荐、追加销售、接受"就这个"上下文接单、集成留言 |
| 📊 **实时订单看板** | SSE 推送，新订单卡片滑入 + 提示音，店家一键"已处理" |
| 🎬 **首页 Hero v2** | 全屏视频轮播 + 品牌故事 + 底部标签 glow，后台可配置视频列表和分类跳转 |
| 📦 **库存管理** | 每道菜独立库存，售罄自动下架，下单扣减 / 取消恢复 |
| 📈 **数据趋势图** | 营业额折线 + 订单柱状 + 时段热力图（Chart.js 4.4）|
| 📥 **Excel 导出** | 订单 / 用户 / 积分 xlsx，带表头样式 + 冻结首行 + 双 sheet |
| 🔔 **企业微信通知** | 新订单 / 新留言推送到群机器人，异步发送不阻塞主流程 |
| 📝 **日志监控** | `app_logs` 表记录 WARNING + 慢请求，后台按级别筛选 + 查看堆栈 |
| ✅ **CI/CD** | GitHub Actions 每次 push 自动跑 74 个 pytest |

---

## 核心特性

### 🧠 LLM 语义理解层（双轨设计）
- **LLM 做"理解"**：一次调用返回结构化 JSON `{action, items, target, new_dish}`
- **规则做"兜底"**：LLM 超时 / 解析失败 → 无缝切规则，用户无感
- **13 类意图**：`place_order / cancel_order / cancel_all / modify_order / query_menu / query_total / query_location / query_hours / recommend / accept_recommend / reject_recommend / leave_message / chat / other`
- **白名单校验**：菜名必须在菜单里，防 4B 模型幻觉
- **上下文接单**：用户说"就这个" → 自动接受上一轮 AI 推荐下单

### 🎛️ 后台 11 个模块
数据总览 / 实时订单 / 订单管理 / AI 记录 / 用户管理 / 菜单管理 / 首页 Hero / 知识库 / 留言 / 桌码 / 日志 / 设置

### 📱 扫码点单闭环
后台生成桌码 → 手机扫码带 `?table=XX` → 存入 localStorage → 下单自动带桌号 → 扫码计数

### 🗄️ 数据层
- **12 张 SQLite 表**，WAL 模式支持多读 + 单写并发
- 解决 Gunicorn 4 worker 下并发写丢数据问题
- 抽象 BaseRepository，可平滑升级 MySQL / PostgreSQL

### 🧩 可扩展架构
- 8 个 Blueprint 路由层 → 服务层 → Repository 数据层
- 所有配置集中在 settings 表，后台热更新
- 支持本地 / 远程 LLM 一键切换

---

## 技术栈（完整清单）

### 后端
| 技术 | 用途 |
|---|---|
| **Flask 3.1** | Web 框架 |
| **Gunicorn 26** | 生产 WSGI 服务器（Linux）|
| **Waitress 3** | 生产 WSGI 服务器（Windows 友好）|
| **Flask-Compress** | Gzip 响应压缩 |
| **Jinja2** | 模板引擎 |
| **Werkzeug** | WSGI 底层 + 密码哈希 |

### 数据存储
| 技术 | 用途 |
|---|---|
| **SQLite 3** | 主数据库（WAL 模式）|
| **JSON 文件** | 菜单等读多写少场景 |
| **Chroma 1.5** | 向量数据库（RAG 检索）|
| **openpyxl** | Excel 导出 |

### LLM / AI
| 技术 | 用途 |
|---|---|
| **Ollama** | 本地大模型运行时 |
| **Qwen3-4B** | 对话 + 意图理解（本地）|
| **bge-m3** | 中文嵌入模型（RAG）|
| **LangChain 1.4** | RAG 编排 |
| **langchain-chroma** | 向量库集成 |
| **langchain-ollama** | Ollama 集成 |
| **OpenAI SDK 3** | 远程 API 兼容层（Qwen / DeepSeek / Kimi）|
| **SSE（Server-Sent Events）** | 实时订单推送 + AI 流式回复 |

### 认证 / 安全
| 技术 | 用途 |
|---|---|
| **PyJWT** | JWT 令牌（会员 + 管理员双轨）|
| **Werkzeug Security** | scrypt 密码哈希 |
| **HttpOnly Cookie** | 管理员会话 |

### 前端
| 技术 | 用途 |
|---|---|
| **原生 HTML5 / CSS3 / JavaScript** | 无框架依赖 |
| **Jinja2 模板** | 服务端渲染 |
| **Chart.js 4.4** | 数据可视化 |
| **Web Audio API** | 新订单提示音 |
| **localStorage / sessionStorage** | 客户端状态 |
| **CSS Variables** | 双主题系统（年轻版 / 大字版）|
| **IntersectionObserver** | 视频懒加载 |

### 测试 / CI/CD
| 技术 | 用途 |
|---|---|
| **pytest 9** | 单元 + 集成测试 |
| **pytest-flask** | Flask 测试夹具 |
| **GitHub Actions** | CI（每次 push 自动跑 74 个测试）|

### 部署
| 技术 | 用途 |
|---|---|
| **Docker** | 容器化打包 |
| **docker-compose** | 多服务编排 |
| **Nginx** | 反向代理 + SSL（上云后）|
| **Let's Encrypt** | 免费 HTTPS 证书 |

### 第三方服务
| 技术 | 用途 |
|---|---|
| **企业微信群机器人** | 新订单 / 留言推送 |
| **阿里云百炼** | 远程 Qwen API |
| **cpolar / frp** | 内网穿透（远程 Ollama）|

---

## 系统架构

```
┌────────────────────────────────────────────────┐
│            用户端 H5（扫码进入）                │
│  首页 │ 菜单 │ AI 店长 │ 我的 │ 订单跟踪        │
└────────────────────────┬───────────────────────┘
                         │ HTTPS
┌────────────────────────▼───────────────────────┐
│              Nginx（SSL + 反代）                │
└────────────────────────┬───────────────────────┘
                         │
┌────────────────────────▼───────────────────────┐
│           Flask 应用（Docker 容器）             │
│  路由层 → 服务层（LLM + 规则双轨）→ 数据层      │
└────────────────────────┬───────────────────────┘
                         │
        ┌────────────────┼────────────────┐
┌───────▼──────┐  ┌─────▼──────┐  ┌──────▼────────┐
│  SQLite      │  │  Chroma    │  │  Ollama       │
│  app.db      │  │  向量库     │  │  Qwen3-4B     │
│  12 张表      │  │            │  │  bge-m3       │
└──────────────┘  └────────────┘  └───────────────┘
```

---

## 快速开始

### 前置要求
- Python 3.12+
- Ollama（本地大模型）
- 6GB+ 显存（跑 Qwen3-4B）
- Docker Desktop（可选）

### 1. 拉模型

```bash
ollama pull modelscope.cn/Qwen/Qwen3-4B-GGUF:latest
ollama pull bge-m3
```

### 2. 安装依赖

```bash
python -m venv venv
venv\Scripts\activate              # Windows
source venv/bin/activate           # Linux/Mac

pip install -r requirements.txt
```

### 3. 初始化

```bash
python scripts/migrate_json_to_sqlite.py
python scripts/init_admin.py
```

### 4. 启动

```bash
# 开发
python app.py

# 生产（Windows 友好）
python server.py

# Docker
docker compose up -d
```

### 5. 访问

| 页面 | 地址 |
|---|---|
| 首页 | http://127.0.0.1:5000/ |
| 菜单 | http://127.0.0.1:5000/menu |
| AI 店长 | http://127.0.0.1:5000/chat |
| 后台 | http://127.0.0.1:5000/admin/login |
| 健康检查 | http://127.0.0.1:5000/health |

**默认管理员：`admin` / `admin888`（上线前必改）**

---

## 测试

```bash
python -m pytest tests/ -v
```

**CI 状态**：[![Tests](https://github.com/acc12138-x/smart-restaurant-ai-waiter/actions/workflows/test.yml/badge.svg)](https://github.com/acc12138-x/smart-restaurant-ai-waiter/actions/workflows/test.yml)

覆盖：菜单 / 订单 / 用户 / 留言 / 认证 / 后台 / 桌码 / AI 意图 / 状态机 / 库存 / 通知。

---

## 项目数据

| 指标 | 数值 |
|---|---|
| 代码行数 | 9000+ |
| 后台模块 | 11 |
| 数据库表 | 12 |
| API 接口 | 50+ |
| 页面数 | 6 前台 + 12 后台 |
| 单元测试 | 74 |
| LLM 意图类别 | 13 |
| Docker 镜像 | ~800MB |

---

## 目录结构

```
.
├── app.py                  # Flask 入口
├── server.py               # Waitress 生产启动
├── configs/                # 配置
├── routes/                 # 8 个 Blueprint
├── services/               # 业务逻辑（LLM / 订单 / 通知 / 导出…）
├── repositories/           # 数据访问层（SQLite + JSON）
├── templates/              # Jinja2 模板
├── static/                 # CSS / JS / 视频
├── tests/                  # 74 个 pytest
├── scripts/                # 数据迁移 / 初始化
├── .github/workflows/      # CI
└── docker-compose.yml
```

---

## 文档

- [API.md](API.md) — 接口文档
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构与踩坑记录

---

## License

MIT

---

## 作者

**acc12138-x** · [GitHub](https://github.com/acc12138-x)