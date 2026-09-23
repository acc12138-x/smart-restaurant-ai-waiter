# 同盛祥西安泡馍老店 · v3.9

> 面向中小餐饮企业的 **H5 扫码点餐 + LLM 语义客服 + 后台运营** 一体化解决方案。顾客扫码进入、和 AI 对话点单；店家通过后台实时接单、管理菜单、查看经营数据。全本地大模型部署，零 API 成本也能完整跑通。

[![Tests](https://github.com/acc12138-x/smart-restaurant-ai-waiter/actions/workflows/test.yml/badge.svg)](https://github.com/acc12138-x/smart-restaurant-ai-waiter/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-blue.svg)](https://www.sqlite.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📖 项目简介

这是一套面向**中小餐馆、面馆、快餐店、私房菜**等场景的轻量级数字化解决方案。它把传统餐馆的线下点单、人工客服、纸质菜单管理搬到线上，让**小成本餐饮商家**也能用上 AI 技术。

### 解决什么问题

| 商家痛点 | 本项目的方案 |
|---|---|
| 高峰期人工点单忙不过来 | H5 扫码点单，顾客自助下单 |
| 客服回答重复问题累 | AI 店长自动回答菜单、营业时间、位置 |
| 顾客不会用小程序 | 扫码直接用，无需下载 App |
| 上 SaaS 每月付费贵 | 全本地部署，一次搞定零订阅 |
| 数据散落各处 | 后台统一管理订单、用户、积分、留言 |

### 谁适合用

- **小餐馆老板**：不想花钱买 SaaS，想自己部署
- **开发者学习**：想学 Flask + LLM 工程化的完整案例
- **课程作业 / 毕业设计**：需要一套真实可用的全栈项目

---

## ✨ v3.9 新增功能

本版本在 v3.0 基础上新增 10 大模块，把项目从"能演示"升级到"能运营"：

### ⚙️ 1. 后台设置系统（基础设施）
- **数据库 key-value 配置**：所有配置项存在 `settings` 表，改完立即生效
- **模型热切换**：本地 Ollama ↔ 远程 OpenAI 兼容 API（Qwen / DeepSeek / Kimi），**不用重启 Flask**
- **5 组配置**：AI 大模型 / 门店信息 / 积分规则 / 功能开关 / 消息通知
- **敏感字段脱敏**：API key 后台显示 `sk-abcd****xyz`，不暴露完整值

### 🤖 2. AI 店长（人格化 LLM）
- 从机械的"小助手"升级为**"金牌店长小同"**人设，连续三年销售冠军
- **主动推荐**：用户说"随便" → 具体推荐菜品 + 搭配 + 价格
- **追加销售**：下单后主动问"要不要加个凉皮解腻？"
- **上下文接单**：AI 推荐了菜 → 用户说"就这个" → **直接下单**
- **留言集成**：说"我要留言" → AI 收集内容 → 写入后台
- **避开重复**：连续推荐不会每次推同一道菜

### 📊 3. 实时订单看板（SSE）
- **Server-Sent Events** 长连接，服务器主动推送新订单
- **自动弹窗提醒**：新订单卡片从右侧滑入 + Web Audio 提示音
- **状态分 tab**：待处理 / 制作中 / 已完成 / 全部
- **一键处理**：店家点"已处理" → 订单转"制作中"，无需刷新

### 🎬 4. 首页 Hero v2（视觉升级）
- **全屏视频轮播**：每段视频对应一道菜
- **后台可配置**：视频列表、分类标签、播放时长全部可改
- **左上角品牌**："同盛祥 · 欢迎您" 中式风格
- **底部标签 glow 效果**：细金边 + 发光字，点击跳转菜单分类

### 📦 5. 库存管理
- **每道菜独立库存**：`menu.json` 加 `stock` 字段
- **售罄自动下架**：前台显示"售罄"标签，按钮禁用
- **下单扣减**：库存不足直接拦单，提示"肉蒜（剩 0）"
- **取消恢复**：订单取消后库存自动加回

### 📈 6. 数据趋势图
- **营业额折线**：近 7 天 / 30 天切换
- **订单量柱状**：按小时分布
- **时段热力图**：周一至周日 × 24 小时，看哪个时段最忙
- 使用 **Chart.js 4.4** 双 Y 轴复合图

### 📥 7. Excel 导出
- **三种导出**：订单明细 / 用户列表 / 积分流水
- **带格式**：表头加粗灰底 + 冻结首行 + 列宽自适应 + 金额格式化
- **多 sheet**：订单导出分"订单明细"+"订单汇总"两页
- 使用 **openpyxl** 生成真 xlsx（不是 CSV）

### 🔔 8. 企业微信通知
- **新订单推送**：用户下单 → 店家手机 2 秒内收到
- **新留言推送**：顾客留言 → 实时通知
- **异步发送**：`threading.Thread` 后台发，不阻塞下单主流程
- **一键配置**：后台填 webhook 地址，点"测试通知"验证

### 📝 9. 日志监控
- **自动记录**：WARNING 及以上日志 + 慢请求（> 3 秒）
- **异常堆栈**：Flask 未捕获异常完整 traceback 存 `app_logs` 表
- **后台筛选**：按级别（WARNING / ERROR / CRITICAL）过滤
- **慢请求 TOP 10**：按耗时排序，找出性能瓶颈

### ✅ 10. CI/CD 自动化
- **GitHub Actions**：每次 push 自动跑 74 个 pytest
- **阿里云 pip 镜像**：CI 装依赖从 5 分钟缩到 1 分钟
- **绿色徽章**：README 顶部展示测试状态
- **防回归**：改代码第一时间知道有没有搞坏功能

---

## 🧠 核心特性（累积能力）

### LLM 语义理解层（双轨设计）

**为什么不用纯规则？**
- 正则匹配意图遇到口语化表达就挂："来两份大份的羊肉泡馍"、"把牛肉泡馍改成羊肉泡馍"
- 4B 模型能理解任意说法，但推理慢、可能幻觉

**为什么不纯 LLM？**
- 延迟：模型推理 1-3 秒，每个"你好"都要等
- 幻觉：4B 模型会编造菜单里没有的菜
- 稳定性：Ollama 挂了整个系统停

**双轨架构**：
```
用户输入
  ↓
_get_intent_result()
  ├─ LLM 开启 → llm_parser.parse()
  │     ├─ 成功 → 结构化 dict（含白名单校验）
  │     └─ 超时/失败 → 降级 ↓
  └─ 规则 intent_service.classify_intent()
  ↓
chat_service 分发
  ├─ FAQ 快路径（< 5ms，覆盖 40+ 高频问题）
  ├─ place_order / cancel_order / modify_order
  ├─ recommend / accept_recommend / leave_message
  └─ 兜底 → RAG（Ollama + Chroma 语义检索）
```

**13 类意图支持**：
| 意图 | 触发示例 | 处理 |
|---|---|---|
| `place_order` | "来一份牛肉泡馍" | 下单 |
| `cancel_order` | "取消订单" | 取消最近一单 |
| `cancel_all` | "全部取消" | 取消本会话所有 |
| `modify_order` | "把 A 改成 B" | 取消 A 下单 B |
| `query_menu` | "牛肉泡馍多少钱" | 菜单快路径 |
| `query_total` | "一共多少钱" | 会话订单合计 |
| `query_location` | "门店在哪里" | FAQ 快路径 |
| `query_hours` | "营业到几点" | FAQ 快路径 |
| `recommend` | "有什么推荐" | LLM 动态推荐 |
| `accept_recommend` | "就这个" | 接受上一轮推荐下单 |
| `reject_recommend` | "换一个" | 重新推荐 |
| `leave_message` | "我要留言" | 写入后台留言 |
| `chat` / `other` | "你好" / "。。。" | 闲聊 / 兜底 |

**白名单校验**：LLM 返回的菜名必须能在 `menu.json` 里找到，否则丢弃（防 4B 模型编造"佛跳墙"这种不存在的菜）。

### 🎛️ 后台 11 个模块

| 模块 | 功能 |
|---|---|
| 📊 数据总览 | 7 张经营卡片 + 6 张流量卡片 + 4 个图表 |
| 🔔 实时订单 | SSE 推送新订单 + 提示音 + 一键处理 |
| 🧾 订单管理 | 列表 / 状态筛选 / 日期筛选 / 改状态 / Excel 导出 |
| 🤖 AI 记录 | 会话列表 / 意图分布 chips / 耗时统计 |
| 👤 用户管理 | 列表 / 改积分 / 禁用 / 搜索 / Excel 导出 |
| 📖 菜单管理 | 增删改菜品 / 分类管理 / 库存设置 |
| 🎬 首页 Hero | 视频上传 / 拖拽排序 / 标签配置 / 停留时长 |
| 📚 知识库 | 列表 / 在线编辑 / 版本历史 / 回滚 |
| 💬 留言管理 | 已读未读 / 筛选 / 标记 / 删除 |
| 🔳 桌码管理 | 生成 / 预览 / 下载 PNG / 扫码计数 |
| 📝 日志监控 | 操作日志 + 应用日志（异常 + 慢请求） |
| ⚙️ 系统设置 | AI / 门店 / 积分 / 开关 / 通知五组配置 |

### 📱 扫码点单闭环

1. 后台 `/admin/tables` → 输入桌号"05" → 点"生成桌码"
2. 系统生成二维码 PNG，内容：`http://<域名>/?table=05`
3. 顾客手机扫码 → 打开首页 → `?table=05` 自动存 localStorage
4. 下单时自动带桌号 → 后台订单列表显示"05 桌"
5. 每扫一次码 → 后台"扫码次数" +1（sessionStorage 防重复）

### 🗄️ 数据存储设计

**12 张 SQLite 表**：
| 表 | 用途 |
|---|---|
| `users` | 会员账号（含 scrypt 密码哈希）|
| `orders` | 订单（items 存 JSON）|
| `messages` | 留言 |
| `chat_logs` | AI 对话日志 |
| `chat_sessions` | 对话历史（跨会话持久化）|
| `events` | 埋点事件 |
| `admin_users` | 管理员 |
| `admin_logs` | 操作日志 |
| `tables` | 桌码 |
| `kb_history` | 知识库版本 |
| `points_log` | 积分流水 |
| `settings` | 系统配置（v3.9）|
| `app_logs` | 应用日志（v3.9）|

**为什么用 SQLite 不用 MySQL**：
- 零依赖部署，Docker 镜像小
- WAL 模式支持多读 + 单写并发，够用
- 数据量 < 10 万条时性能超越 MySQL
- `BaseRepository` 抽象接口，未来可平滑升级

---

## 🛠 完整技术栈

### 后端框架
| 技术 | 版本 | 用途 |
|---|---|---|
| Flask | 3.1.3 | Web 框架 |
| Gunicorn | 26.2 | 生产 WSGI（Linux）|
| Waitress | 3.0 | 生产 WSGI（Windows）|
| Werkzeug | 3.1.8 | WSGI + 密码哈希 |
| Jinja2 | 3.1.6 | 模板引擎 |
| Flask-Compress | 1.24 | Gzip 响应压缩 |

### 数据存储
| 技术 | 版本 | 用途 |
|---|---|---|
| SQLite | 3 | 主数据库（WAL）|
| JSON | - | 菜单等读多写少数据 |
| Chroma | 1.5.9 | 向量数据库 |
| openpyxl | 3.1.5 | Excel 导出 |

### LLM / RAG
| 技术 | 版本 | 用途 |
|---|---|---|
| Ollama | - | 本地大模型运行时 |
| Qwen3-4B | - | 对话 + 意图理解 |
| bge-m3 | - | 中文嵌入（RAG）|
| LangChain | 1.4.0 | RAG 编排 |
| langchain-core | 1.6.3 | 核心抽象 |
| langchain-community | 0.4.2 | 社区集成 |
| langchain-chroma | 1.1.0 | 向量库集成 |
| langchain-ollama | 1.1.0 | Ollama 集成 |
| langchain-text-splitters | 1.1.2 | 文档切分 |
| OpenAI SDK | 3.16.2 | 远程 API 兼容层 |
| SSE | - | 实时推送 |

### 认证 / 安全
| 技术 | 版本 | 用途 |
|---|---|---|
| PyJWT | 2.14.0 | JWT 令牌 |
| Werkzeug Security | - | scrypt 密码哈希 |
| HttpOnly Cookie | - | 管理员会话 |

### 前端
| 技术 | 用途 |
|---|---|
| HTML5 / CSS3 | 页面结构与样式 |
| 原生 JavaScript | 无框架依赖 |
| Chart.js 4.4 | 数据可视化 |
| Web Audio API | 新订单提示音 |
| EventSource | SSE 客户端 |
| localStorage | 客户端状态持久化 |
| sessionStorage | 会话级防重 |
| CSS Variables | 双主题切换 |
| IntersectionObserver | 视频懒加载 |
| Fetch API | 异步请求 |

### 测试 / CI/CD
| 技术 | 版本 | 用途 |
|---|---|---|
| pytest | 9.1.1 | 单元 + 集成测试 |
| pytest-flask | 1.3.0 | Flask 测试夹具 |
| GitHub Actions | - | 自动化 CI |

### 部署
| 技术 | 用途 |
|---|---|
| Docker | 容器化 |
| docker-compose | 服务编排 |
| Nginx | 反向代理 + SSL |
| Let's Encrypt | 免费 HTTPS |
| cpolar / frp | 内网穿透（远程 Ollama）|

### 第三方服务
| 服务 | 用途 |
|---|---|
| 企业微信群机器人 | 订单 / 留言推送 |
| 阿里云百炼 | Qwen API |
| 阿里云轻量服务器 | 云端部署 |

---

## 🏗 系统架构

```
┌────────────────────────────────────────────────────┐
│              用户端 H5（扫码进入）                  │
│  首页 │ 菜单 │ AI 店长 │ 我的 │ 订单跟踪            │
│  · 原生 JS + SSE 流式回复                          │
│  · 双主题（年轻版 / 大字版）                        │
└─────────────────────┬──────────────────────────────┘
                      │ HTTPS
┌─────────────────────▼──────────────────────────────┐
│                  Nginx（宿主机）                    │
│  · SSL 证书（Let's Encrypt）                       │
│  · 静态文件直返                                    │
│  · 反代到 Flask 容器                               │
└─────────────────────┬──────────────────────────────┘
                      │ HTTP (127.0.0.1:5000)
┌─────────────────────▼──────────────────────────────┐
│           Flask 应用（Docker 容器）                 │
│  ┌──────────────────────────────────────────────┐  │
│  │ 路由层 routes/  （8 个 Blueprint）            │  │
│  └─────────────┬────────────────────────────────┘  │
│  ┌─────────────▼────────────────────────────────┐  │
│  │ 服务层 services/                              │  │
│  │  · chat_service（LLM 双轨）                   │  │
│  │  · order_service（状态机）                    │  │
│  │  · settings_service（配置热更新）             │  │
│  │  · notify_service（企微推送）                 │  │
│  │  · export_service（Excel 导出）               │  │
│  └─────────────┬────────────────────────────────┘  │
│  ┌─────────────▼────────────────────────────────┐  │
│  │ 数据层 repositories/                          │  │
│  │  · BaseRepository（抽象接口）                 │  │
│  │  · SqliteRepository / JsonRepository          │  │
│  └──────────────────────────────────────────────┘  │
└──┬──────────────────┬──────────────────┬───────────┘
   │                  │                  │
┌──▼──────┐  ┌────────▼───────┐  ┌───────▼──────────┐
│ SQLite  │  │  Chroma        │  │  Ollama          │
│ app.db  │  │  向量库         │  │  Qwen3-4B        │
│ 13 表    │  │  bge-m3 嵌入    │  │  bge-m3          │
└─────────┘  └────────────────┘  └──────────────────┘
```

---

## 🚀 快速开始

### 前置要求
- **Python 3.12+**
- **Ollama**（本地大模型运行时）
- **6GB+ 显存**（跑 Qwen3-4B）
- **Docker Desktop**（可选，用于容器化部署）

### 1. 拉取模型

```bash
# 对话 + 意图理解模型
ollama pull modelscope.cn/Qwen/Qwen3-4B-GGUF:latest

# 中文嵌入模型（RAG 用）
ollama pull bge-m3
```

### 2. 安装依赖

```bash
python -m venv venv
venv\Scripts\activate              # Windows
source venv/bin/activate           # Linux / Mac

pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
# 迁移旧 JSON 数据到 SQLite（首次运行必跑）
python scripts/migrate_json_to_sqlite.py

# 创建默认管理员账号
python scripts/init_admin.py
```

### 4. 启动服务

```bash
# 开发模式（Flask 内置服务器）
python app.py

# 生产模式（Windows 友好，8 线程 Waitress）
python server.py

# Docker 部署（推荐）
docker compose up -d
```

### 5. 访问

| 页面 | 地址 |
|---|---|
| 🏠 首页 | http://127.0.0.1:5000/ |
| 📖 菜单 | http://127.0.0.1:5000/menu |
| 🤖 AI 店长 | http://127.0.0.1:5000/chat |
| 👤 我的 | http://127.0.0.1:5000/profile |
| 🔧 后台 | http://127.0.0.1:5000/admin/login |
| 💚 健康检查 | http://127.0.0.1:5000/health |
| 📚 API 文档 | http://127.0.0.1:5000/api/docs |

**默认管理员**：`admin` / `admin888`（⚠️ 上线前必改）

---

## 🧪 测试

```bash
# 跑全部测试
python -m pytest tests/ -v

# 只看失败
python -m pytest tests/ -x --tb=short

# 覆盖率（需装 pytest-cov）
python -m pytest tests/ --cov=services --cov=routes
```

**CI 状态**：
[![Tests](https://github.com/acc12138-x/smart-restaurant-ai-waiter/actions/workflows/test.yml/badge.svg)](https://github.com/acc12138-x/smart-restaurant-ai-waiter/actions/workflows/test.yml)

**测试覆盖**：
- 菜单服务（6 个）
- 订单状态机（6 个）
- 留言服务（4 个）
- 认证接口（6 个）
- 后台服务（15 个）
- API 集成（25 个）
- AI 意图 + LLM（12 个）

**74 个用例，全部通过。**

---

## 📊 项目数据

| 指标 | 数值 |
|---|---|
| 代码行数 | 9000+ |
| 后台模块 | 11 |
| 数据库表 | 13 |
| API 接口 | 50+ |
| 页面数 | 6 前台 + 13 后台 |
| 单元测试 | 74 |
| LLM 意图类别 | 13 |
| Docker 镜像 | ~800MB |
| 首次部署时间 | ~5 分钟 |

---

## 📂 目录结构

```
smart-restaurant-ai-waiter/
├── app.py                  # Flask 应用入口
├── server.py               # Waitress 生产启动
├── wsgi.py                 # Gunicorn 入口
├── configs/                # 配置类
│   └── config.py
├── routes/                 # 路由层（8 个 Blueprint）
│   ├── page_routes.py      # 前台页面
│   ├── api_routes.py       # 前台 API
│   ├── auth_routes.py      # 认证
│   ├── points_routes.py    # 积分
│   ├── track_routes.py     # 埋点
│   ├── docs_routes.py      # Swagger
│   ├── admin_routes.py     # 知识库 API
│   └── admin_page_routes.py # 后台页面
├── services/               # 业务逻辑层
│   ├── chat_service.py     # AI 对话
│   ├── llm_parser.py       # LLM 意图解析
│   ├── intent_service.py   # 规则意图
│   ├── rag_service.py      # RAG 检索
│   ├── order_service.py    # 订单
│   ├── menu_service.py     # 菜单
│   ├── settings_service.py # 系统设置
│   ├── notify_service.py   # 企微通知
│   ├── export_service.py   # Excel 导出
│   └── ...
├── repositories/           # 数据访问层
│   ├── base.py             # 抽象接口
│   ├── sqlite_repo.py      # SQLite 实现
│   ├── json_repo.py        # JSON 实现
│   ├── instances.py        # 单例集合
│   └── schema.sql          # 建表语句
├── templates/              # Jinja2 模板
│   ├── base.html
│   ├── index.html / menu.html / chat.html / ...
│   └── admin/              # 后台页面（13 个）
├── static/                 # 静态资源
│   ├── css/                # style.css + admin.css
│   ├── js/                 # common / hero / cart / track
│   └── video/hero/         # 首页视频
├── tests/                  # 74 个 pytest
├── scripts/                # 迁移 / 初始化脚本
├── knowledge_docs/         # RAG 知识库（Markdown）
├── vector_store/           # Chroma 向量库（自动生成）
├── .github/workflows/      # CI 配置
├── docker-compose.yml      # 容器编排
├── Dockerfile              # 镜像构建
└── requirements.txt
```

---

## 🔑 关键设计

### 1. LLM 双轨（语义 + 规则兜底）
LLM 挂掉不影响核心点单，规则兜底保证可用性。

### 2. 白名单校验
LLM 返回的菜名必须在 `menu.json` 里，防止 4B 模型幻觉编造菜品。

### 3. 三层防御（防小模型胡言乱语）
- **Prompt 层**：明确禁止输出"用户：""助手："
- **模型层**：`stop=["用户：", "助手："]`
- **后端层**：字符串查找 + 截断清洗

### 4. 状态机订单流转
```
pending ──→ paid ──→ cooking ──→ done
   │         │           │
   ↓         ↓
cancelled  cancelled
```
非法转换直接拦（`cooking` 不能退单，`done` 不能取消）。

### 5. 积分规则
- 下单：**不加**积分
- 付款：**+N 分**（1 元 = 1 分）
- 付款前取消：**不动积分**
- 付款后取消：**-N 分**（允许负数）

### 6. 敏感字段脱敏
后台读取配置时，`api_key` / `wecom_webhook` 返回打码版本（`sk-abc****xyz`），写操作时空串表示"不修改"。

### 7. 异步通知
企业微信推送用 `threading.Thread` 后台发，**下单接口 100ms 内返回**，不等 webhook。

### 8. 慢请求监控
`before_request` + `after_request` 埋点，> 3 秒的请求自动写 `app_logs`，后台 TOP 10 一看就知道哪个接口慢。

---

## 📄 License

MIT © 2026 acc12138-x

---

## 👨‍💻 作者

**acc12138-x** · [GitHub](https://github.com/acc12138-x)

如果这个项目对你有帮助，欢迎 ⭐ Star 支持一下！