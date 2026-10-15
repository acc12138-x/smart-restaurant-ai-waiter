# 同盛祥 · 智能点餐与经营系统

> 面向中小餐饮门店的「扫码点餐 + AI 语义客服 + 经营分析」一体化系统。顾客扫码进店、用自然语言点单；店家在后台实时接单、管理菜单与知识库、查看经营周报。支持**全本地大模型部署（零 API 成本）**与**远程 API** 两种模式，改配置无需重启。

> **EN** — A self-hosted ordering & operations system for small restaurants: QR-code ordering, an LLM-powered waiter with rule-based fallback, RAG over store knowledge, and a weekly business report with AI commentary. Runs fully on-premise with Ollama, or against any OpenAI-compatible API.

[![Tests](https://github.com/acc12138-x/smart-restaurant-ai-waiter/actions/workflows/test.yml/badge.svg)](https://github.com/acc12138-x/smart-restaurant-ai-waiter/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-blue.svg)](https://www.sqlite.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 目录

- [一、项目简介](#一项目简介)
- [二、功能总览](#二功能总览)
- [三、技术架构](#三技术架构)
- [四、关键设计决策](#四关键设计决策)
- [五、数据模型](#五数据模型)
- [六、快速开始](#六快速开始)
- [七、生产部署](#七生产部署)
- [八、运维手册](#八运维手册)
- [九、测试与 CI](#九测试与-ci)
- [十、接口文档](#十接口文档)
- [十一、目录结构](#十一目录结构)
- [十二、更新记录](#十二更新记录)

---

## 一、项目简介

### 1.1 项目定位

一套可私有化部署的餐饮门店数字化系统，把**扫码点餐、AI 客服、经营看板**收敛到一个 Flask 应用里。

### 1.2 解决什么问题

| 门店痛点 | 本系统的做法 |
|---|---|
| 高峰期人工点单忙不过来 | H5 扫码点单，顾客自助下单，桌号自动带入 |
| 客服反复回答同样的菜价／营业时间 | FAQ 快路径 + 知识库检索，高频问题毫秒级响应 |
| 顾客不愿装小程序 | 扫码即用，纯 H5，无 App 依赖 |
| SaaS 按年订阅成本高 | 完全本地部署，零订阅；也可切远程 API |
| 数据散落各处 | 订单、会员、积分、留言、对话、埋点统一入库 |
| 经营决策没有依据 | 实时看板 + 经营周报 + AI 分析师点评 |

### 1.3 适用对象

- 中小餐饮门店：面馆、快餐、泡馍馆、私房菜等单店场景
- 需要私有化部署、不愿数据出内网的商家
- 学习 Flask + LLM 工程化的完整参考实现

### 1.4 项目规模

| 指标 | 数值 |
|---|---|
| 应用代码 | 约 6,700 行（路由 / 服务 / 数据访问 / 工具 / 配置） |
| 测试代码 | 约 1,100 行，**105 个 pytest 用例** |
| 脚本 | 约 250 行（数据迁移、初始化、时间戳修正） |
| HTTP 接口 | **92 个** |
| 数据库表 | **13 张**（SQLite，WAL 模式） |
| 页面 | 前台 6 个 + 后台 13 个 |
| 服务模块 | 17 个 |

---

## 二、功能总览

### 2.1 顾客端（6 个页面）

| 页面 | 说明 |
|---|---|
| 首页 | 全屏视频 Hero 轮播，后台可配置视频、分类标签与停留时长 |
| 菜单 | 分类浏览、库存售罄标记、加入购物车 |
| AI 店长 | 流式对话点单，自然语言下单 / 改单 / 取消 / 推荐 / 留言 |
| 我的 | 会员信息、积分、等级、历史订单 |
| 订单跟踪 | 按订单号查状态（pending → paid → cooking → done） |
| 门店位置 | 地址、营业时间、联系方式 |

### 2.2 商家后台（13 个页面）

| 模块 | 能力 |
|---|---|
| 数据总览 | 经营概览（今日营业额主数字 + 近 7 天迷你柱）、流量条形图、营业趋势、时段分布、周时段热力图、事件与意图分布；**本周经营周报**（环比、逐日明细、销量 Top5、高峰时段、规则洞察）与**金牌分析师**（大模型按「总评 / 关键发现 / 风险提示 / 下周行动」四段点评，按需生成并带缓存）也在此页 |
| 实时订单 | SSE 推送新订单，提示音 + 一键接单 |
| 订单管理 | 列表 / 状态筛选 / 日期筛选 / 状态流转 / Excel 导出 |
| AI 记录 | 会话列表、意图分布、耗时统计 |
| 用户管理 | 列表、积分调整、禁用、搜索、Excel 导出 |
| 菜单管理 | 菜品增删改、分类管理、库存设置 |
| 首页 Hero | 视频上传、拖拽排序、标签配置 |
| 知识库 | 在线编辑、版本历史、回滚，保存后自动重建向量库 |
| 留言管理 | 已读未读、筛选、标记、删除 |
| 桌码管理 | 生成二维码、预览、下载 PNG、扫码计数 |
| 日志监控 | 操作日志 + 应用日志（异常堆栈 + 慢请求 Top10） |
| 系统设置 | AI 模型、门店信息、积分规则、功能开关、消息通知五组配置 |
| 管理员登录 | 登录 / 登出，失败 5 次 / 15 分钟锁定 |

### 2.3 AI 能力

- **13 类意图**：点单 / 改单 / 取消单笔 / 取消全部 / 查菜单价 / 查合计 / 查门店 / 查营业时间 / 推荐 / 接受推荐 / 拒绝推荐 / 留言 / 闲聊
- **LLM 双轨**：大模型理解口语化表达，规则层兜底保证可用性（详见 [3.3](#33-llm-双轨为什么不是纯-llm也不是纯规则)）
- **RAG 知识库**：门店信息、品牌故事、菜单、招牌菜等 Markdown 文档，自动切分、向量化、检索
- **白名单校验**：模型返回的菜名必须在菜单内，杜绝编造菜品
- **错别字容错**：菜名写错（"羊肉跑馍"、"冰锋汽水"）也能按字符相似度落到菜单里的正确菜名
- **对话记忆**：会话历史与"最近推荐"落 SQLite（多 worker 共享），未登录顾客按设备隔离；"AI 推荐 → 用户回可以"能直接接单
- **对话里点桌号**：说"点一份羊肉泡馍送到 1 号桌"即可，桌号必须与后台「桌码管理」配过的桌一致（`1` / `01` / `A1` 等写法自动归一化），店里没有的桌会当场提醒而不会下单
- **多模型接入**：本地 Ollama（Qwen3-4B + bge-m3）或任意 OpenAI 兼容 API（阿里云百炼 / DeepSeek / Kimi），后台可热切换
- **企业微信通知**：新订单、新留言异步推送，不阻塞主流程

---

## 三、技术架构

### 3.1 分层设计

```
┌────────────────────────────────────────────────┐
│  路由层  routes/  （8 个 Blueprint / 92 个接口） │
│  只负责接收请求、调用服务、返回响应              │
└───────────────────────┬────────────────────────┘
                        │
┌───────────────────────▼────────────────────────┐
│  服务层  services/  （17 个模块）                │
│  对话、意图、检索、订单、库存、设置、通知、导出    │
│  不直接读写文件，统一走 Repository               │
└───────────────────────┬────────────────────────┘
                        │
┌───────────────────────▼────────────────────────┐
│  数据层  repositories/                          │
│  BaseRepository 抽象 + SqliteRepository 实现     │
└───────────────────────┬────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   SQLite（13 表）   Chroma（向量库）   Ollama / 远程 API
```

### 3.2 一次 AI 点单的完整链路

```
用户：「来两份牛肉泡馍」
  → POST /api/chat
  → 意图识别（LLM 优先，规则兜底）
  → FAQ 快路径 / 未知菜名校验 / 菜单关键词匹配
  → order_service.create()：匹配菜品 → 校验库存 → 扣减 → 落库
  → 异步推送企业微信
  → 返回回复 + 意图 + 订单对象
```

### 3.3 LLM 双轨：为什么不是纯 LLM，也不是纯规则

| 维度 | 纯规则 | 纯 LLM | 本系统（双轨） |
|---|---|---|---|
| 延迟 | < 5ms | 1–3s | 快路径 < 5ms，复杂请求 1–3s |
| 口语化准确率 | 低 | 高 | 高 |
| 幻觉风险 | 无 | 有 | 白名单校验兜住 |
| 模型不可用时 | 不受影响 | 全部不可用 | 自动降级为规则 |

链路：**规则先跑**（接受推荐 / 拒绝推荐 / 留言直接命中）→ **LLM 解析**（结构化意图 + 菜名白名单校验）→ **规则分类兜底** → 未命中则进 **RAG 知识库**。

### 3.4 知识库检索：白名单放行，黑名单拦截

提问要穿过四道关卡才能用到知识库，其中两道是踩过坑之后改的：

```
①  意图识别
②  未知菜名拦截 —— 只对「点单 / 询价」两个意图生效（白名单）
③  菜单关键词快路径 —— 命中菜名直接答价，不加载向量库
④  知识库检索 —— 默认开启，仅跳过「谢谢 / 好的」这类非信息输入
```

两个反直觉的结论，来自线上实测：

- **拦截要用白名单，不能用黑名单。** 意图来自大模型、天然会误判：同一句话可能被判成 `other`、也可能被判成 `query_hours`。用"排除名单"就会漏，资料型问题被回成「菜单里没有「…」哦～」。白名单保证任何误判都不会吃掉知识库问题。
- **检索要默认开启，不能靠关键词白名单放行。** 曾用 35 个门店关键词（多少钱 / 地址 / 营业时间 / …）决定是否检索，结果"羊从哪来""用什么料"这类问题永远检索不到知识库，模型只能凭自己编——知识库明写「选用宁夏滩羊」，实测却被答成「陕北现宰」。

### 3.5 配置热更新与多 worker

配置存 `settings` 表，服务层带进程内缓存。生产用 Gunicorn 多 worker，每个 worker 各有一份缓存，因此：

- 缓存带 **5 秒 TTL**，某个 worker 里保存的改动能自动传播到其它 worker
- 后台设置页强制**直读数据库**，保证管理员看到的永远是真实配置
- 敏感字段（API Key、webhook）读取时脱敏为 `sk-abcd****xyz`，写空值表示"不修改"

### 3.6 时间处理

**业务时间一律按北京时间（UTC+8）**，由 `utils/timeutil.py` 统一提供，并在进程启动时固定时区。原因：容器默认运行在 UTC，而所有时间戳都取自"进程本地时间"——不修正会让订单时间早 8 小时，且**凌晨 00:00–08:00 的订单（本店营业到次日 02:00）会被算到前一天**，进而污染营业额、时段分布与热力图。

---

## 四、关键设计决策

| 决策 | 原因 |
|---|---|
| 拦截用白名单，放行用默认开 | 意图判定来自大模型，误判不可避免；用"排除清单"迟早漏 |
| 时间用固定 +08:00 偏移，而非 `ZoneInfo` | 中国无夏令时，固定偏移永远正确，且不依赖镜像内是否安装 tzdata |
| JSON 字段存 `data/menu.json` | 菜单读多写少，改完即生效，无需迁移 |
| 订单元数据存 SQLite | 需要状态机、按时间聚合、并发写入 |
| SQLite 而非 MySQL | 单店数据量 < 10 万条，零依赖部署；`BaseRepository` 抽象保留平滑升级路径 |
| 企业微信通知走 `threading.Thread` | 下单接口 100ms 内返回，不等 webhook 响应 |
| 慢请求自动入库 | `before_request` / `after_request` 埋点，> 3 秒写 `app_logs`，后台可直接看 Top10 |
| 订单状态机 | 非法流转直接拦截（`cooking` 不能退单、`done` 不能取消） |
| 证书续期用自建镜像 + 错误日志 + 到期看门狗 | 续期是静默关键路径：失败不会有任何提示，必须让失败可见 |

---

## 五、数据模型

13 张表（`repositories/schema.sql`）：

| 表 | 用途 |
|---|---|
| `users` | 会员账号（scrypt 密码哈希） |
| `orders` | 订单（items 存 JSON，状态机流转） |
| `messages` | 顾客留言 |
| `chat_logs` | AI 对话记录（问题 / 回答 / 意图 / 耗时） |
| `chat_sessions` | 对话历史（跨会话持久化） |
| `events` | 埋点事件 |
| `admin_users` | 后台账号 |
| `admin_logs` | 后台操作日志 |
| `tables` | 桌码与扫码计数 |
| `kb_history` | 知识库版本历史 |
| `points_log` | 积分流水 |
| `settings` | 系统配置（key-value，热更新） |
| `app_logs` | 应用日志（异常堆栈 + 慢请求） |

订单状态机：

```
pending ──→ paid ──→ cooking ──→ done
   │         │           │
   ▼         ▼
cancelled  cancelled
```

积分规则：下单不加分 → 付款 +N（1 元 = 1 分）→ 付款前取消不动积分 → 付款后取消 -N（允许为负）。

---

## 六、快速开始

### 前置要求

- Python 3.12+
- Ollama（本地模型运行时）
- 6GB+ 显存（运行 Qwen3-4B）；显存不足可直接使用远程 API

### 步骤

```bash
# 1. 拉取模型（本地模式）
ollama pull modelscope.cn/Qwen/Qwen3-4B-GGUF:latest
ollama pull bge-m3

# 2. 安装依赖
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux / macOS
pip install -r requirements.txt

# 3. 初始化数据与管理员
python scripts/migrate_json_to_sqlite.py
python scripts/init_admin.py

# 4. 启动
python app.py                  # 开发模式（Flask 内置服务器）
python server.py               # 生产模式（Waitress，Windows 友好）
```

### 访问地址

| 页面 | 地址 |
|---|---|
| 首页 | http://127.0.0.1:5000/ |
| 菜单 | http://127.0.0.1:5000/menu |
| AI 店长 | http://127.0.0.1:5000/chat |
| 我的 | http://127.0.0.1:5000/profile |
| 商家后台 | http://127.0.0.1:5000/admin/login |
| 健康检查 | http://127.0.0.1:5000/health |
| 接口文档 | http://127.0.0.1:5000/api/docs |

> 默认管理员：`admin` / `admin888` —— **上线前必须修改**。

---

## 七、生产部署

完整步骤见 **[DEPLOY.md](DEPLOY.md)**（阿里云轻量服务器 + Docker + Nginx + Let's Encrypt，含实测踩坑记录）。

架构概览：

```
用户浏览器
   ↓ HTTPS
Nginx（宿主机：SSL、静态文件、SSE 免缓冲反代）
   ↓ 127.0.0.1:5000
Docker 容器 tsx-app（Gunicorn 2 worker × 8 线程）
   ├── 源码以 bind mount 挂载 → 改代码只需 restart，不必重新构建镜像
   └── data/ vector_store/ knowledge_docs/ logs/ 挂载持久化
   ↓
SQLite（13 表）+ Chroma 向量库 + 大模型
```

> 云端 2GB 内存跑不动本地模型时，在后台「设置 → AI 大模型」切到**远程 API** 即可，无需重启、无需改代码。

---

## 八、运维手册

日常运维命令与故障排查详见 **[DEPLOY.md](DEPLOY.md)**，以下为高频操作：

```bash
D=/root/apps/smart-restaurant-ai-waiter

# 更新代码（源码是 bind mount，restart 即生效）
git -C $D status --short          # 有本地改动先 git stash，勿用 reset --hard
git -C $D pull
docker compose -f $D/docker-compose.yml up -d

# 改知识库
#   后台 /admin/kb 在线编辑保存 → 自动重建向量库 → 下次问答生效
#   注意有 10 分钟答案缓存，改完想立刻验证可重启容器

# 健康与排查
curl -I http://127.0.0.1:5000/
docker compose -f $D/docker-compose.yml logs --tail=60
docker compose -f $D/docker-compose.yml logs --tail=100 | grep -E '\[RAG\]'

# 证书续期（每天 03:20 自动）
cat /var/log/certbot-renew.log    # 空 = 正常（该文件只记错误）
cat /var/log/cert-expiry.log      # 每周一记录到期时间；日期不再前移说明续期断了
```

**长期建议**：`docker image prune -a` 会删除不被运行中容器引用的镜像（例如证书续期所需的 certbot 镜像），建议只用 `docker image prune -f` 与 `docker builder prune -f`。

---

## 九、测试与 CI

```bash
python -m pytest tests/ -v                      # 全部用例
python -m pytest tests/ -x --tb=short           # 首个失败即停
python -m pytest tests/ --cov=services --cov=routes   # 覆盖率（需 pytest-cov）
```

- **105 个 pytest 用例**，覆盖菜单服务、订单状态机、留言、认证、后台服务、API 集成、AI 意图、RAG 提示词、时区处理、周报聚合
- GitHub Actions 每次 push 自动执行（[workflow](.github/workflows/test.yml)），CI 使用阿里云 pip 镜像加速
- 新增功能均配套回归测试；对踩过的坑（时区偏移、周报环比、未知菜名拦截、设置缓存）都有专门用例锁定

---

## 十、接口文档

- **在线 Swagger**：`/api/docs`（登录后可直接调试，覆盖全部 92 个接口）
- **接口清单**：[API.md](API.md)，整理了常用接口的说明与请求示例
- **统一响应格式**：

```json
{ "code": 0, "msg": "ok", "data": { } }
```

---

## 十一、目录结构

```
smart-restaurant-ai-waiter/
├── app.py                      # Flask 入口（时区固定、Gzip、慢请求监控、异常处理）
├── server.py / wsgi.py         # Waitress / Gunicorn 启动入口
├── configs/                    # 配置类
├── routes/                     # 路由层（8 个 Blueprint，92 个接口）
├── services/                   # 业务逻辑（17 个模块）
│   ├── chat_service.py         # 对话主流程与意图分发
│   ├── llm_parser.py           # LLM 意图解析 + 菜名白名单校验
│   ├── intent_service.py       # 规则意图分类（降级用）
│   ├── rag_service.py          # 知识库加载、向量检索、重建
│   ├── admin_service.py        # 后台统计、订单、用户、周报与 AI 点评
│   ├── settings_service.py     # 配置热更新（TTL 缓存）
│   └── order_service.py        # 订单状态机与库存扣减
├── repositories/               # 数据访问层（抽象接口 + SQLite 实现 + schema.sql）
├── utils/                      # 日志、响应、鉴权、时间、远程 LLM 客户端
├── templates/                  # Jinja2 模板（前台 6 + 后台 13）
├── static/                     # CSS / JS / 视频素材
├── tests/                      # 105 个 pytest 用例
├── scripts/                    # 数据迁移、初始化、时间戳修正
├── knowledge_docs/             # RAG 知识库（Markdown）
├── DEPLOY.md / API.md / ARCHITECTURE.md
└── Dockerfile / docker-compose.yml / requirements.txt
```

---

## 十二、更新记录

### v3.10

**新增**

- **本周经营周报**：自然周（周一–周日）口径，提供本周 / 上周核心指标、环比、逐日明细、销量 Top5、高峰时段与规则洞察
- **金牌分析师**：大模型按「本周总评 / 关键发现 / 风险提示 / 下周行动」四段点评经营数据，按需生成并带 30 分钟缓存与数据指纹
- **数据总览可视化改版**：13 张指标卡合并为「经营概览」（主数字 + 行内副指标 + 近 7 天迷你柱）与「流量数据」（横向条形图）

**修复**

- **时区**：容器默认 UTC 导致订单时间早 8 小时、凌晨订单被算到前一天；现统一按北京时间记录与统计，并提供历史数据修正脚本
- **知识库**：重建向量库时先释放 Chroma 句柄再清理文件，修复 `(code: 1032) attempt to write a readonly database`
- **知识库检索**：未知菜名拦截改为白名单 + 代词守卫；检索改为默认开启，修复「知识库有内容却答不出来」
- **设置项**：修复后台设置页在新 worker 中显示默认值、跨 worker 配置不刷新、测试按钮无法测试已保存 Key
- **安全**：知识库接口由硬编码 token 改为管理员 Cookie JWT；`/api/kb_rebuild` 补上鉴权

### v3.9

后台设置系统（数据库 key-value + 模型热切换）、AI 店长人格化、实时订单看板（SSE）、首页视频 Hero、库存管理、数据趋势图、Excel 导出、企业微信通知、日志监控、CI/CD。

---

## License

MIT © 2026 [acc12138-x](https://github.com/acc12138-x)
