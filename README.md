
# 同盛祥西安泡馍老店 · v3.0 运营版

> 一套面向中小餐饮企业的 **H5 点餐 + LLM 语义客服 + 后台运营系统**，从"能演示的 Demo"升级到"能运营的准产品"。

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-blue.svg)](https://www.sqlite.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)
[![LLM](https://img.shields.io/badge/LLM-Qwen3--4B-orange.svg)](https://ollama.com/)
[![Tests](https://img.shields.io/badge/tests-22%20passed-brightgreen.svg)](#测试)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📖 项目简介

同盛祥是一家经营 30 年的西安泡馍老字号。面对 **老客群 45 岁以上、年轻人觉得土气** 的困境，本项目用**全本地部署、零 API 成本**的方式，把一家老店完整搬到了线上：

| 面向 | 提供 |
|---|---|
| **年轻人** | 动漫治愈风 H5、LLM 语义点餐、扫码点单、深夜食堂打卡 |
| **老年人** | 大字版界面（14px → 20px）、一键切换、无动画干扰 |
| **店主** | 10 个后台模块：看板 / 订单 / AI 记录 / 用户 / 知识库 / 留言 / 桌码 / 日志 / 设置 |

**6GB 显存笔记本即可完整运行，无需任何云服务。**

---

## ✨ v3.0 核心升级

### 🗄️ 存储层：JSON → SQLite
- 11 张表，WAL 模式支持多读 + 单写并发
- 解决 Gunicorn 4 worker 下**并发丢数据**问题
- JSON → SQLite 迁移脚本，带原数据备份

### 🧠 LLM 语义理解层（新增）
- **双轨设计**：LLM 做"理解"，规则做"兜底"
- 一次调用返回结构化 JSON：`{action, items, target, new_dish}`
- 支持 11 类意图：`place_order / cancel_order / cancel_all / modify_order / query_menu / query_total / query_location / query_hours / recommend / chat / other`
- **白名单校验**：菜名必须在菜单里，防 4B 模型幻觉
- **无缝降级**：LLM 超时/解析失败 → 自动切回规则系统

### 🎛️ 后台运营系统（10 个模块）
| 模块 | 功能 |
|---|---|
| 数据总览 | 7 张经营卡片 + 6 张流量卡片 + 4 个图表（Chart.js 环形/横条） |
| 订单管理 | 列表 / 状态筛选 / 日期筛选 / 改状态 / 导出 CSV |
| AI 记录 | 会话列表 / 意图分布 chips / 耗时统计 |
| 用户管理 | 列表 / 改积分 / 禁用 / 搜索 |
| 知识库 | 列表 / 编辑 / **版本历史 + 回滚** / 新建 / 删除 |
| 留言管理 | 已读未读 / 筛选 / 标记 |
| 桌码管理 | 生成 / 预览 / 下载 PNG / 扫码计数 |
| 操作日志 | 全部后台操作审计 |
| 设置 | 预留 |

### 📱 扫码点单闭环
- 后台生成桌码 → 输出 PNG 二维码
- 二维码内容：`http://<域名>/?table=A5`
- H5 自动识别桌号 → 存入 localStorage → 下单时带上
- 后台订单列表实时看到桌号

### 🎨 前端改版
- **菜单页**：卡片化 + 暖橙 emoji 底 + 红色价格 + 弹性加菜按钮
- **聊天页**：气泡渐变 + 阴影 + 入场动画 + 打字指示器
- **订单跟踪页**：4 步状态时间轴 + 脉冲动画
- **大字版**：切换按钮右上角（v3.0 S7 修复）

### 💰 积分规则升级
- 下单**不再**加积分 → **付款后**发放（每 1 元 = 1 分）
- 取消订单：付款前取消不扣分，付款后取消**自动扣回**（允许负数）

---

## 🏗 系统架构

```
┌────────────────────────────────────────────────┐
│            用户端 H5（扫码进入）                │
│  首页 │ 菜单 │ 门店 │ AI客服 │ 我的 │ 订单跟踪  │
└────────────────────────┬───────────────────────┘
                         │ HTTPS
┌────────────────────────▼───────────────────────┐
│                 cpolar 内网穿透                 │
└────────────────────────┬───────────────────────┘
                         │
┌────────────────────────▼───────────────────────┐
│              Flask 应用（Docker）               │
│  路由层 → 服务层（LLM + 规则双轨）→ 数据层       │
└────────────────────────┬───────────────────────┘
                         │
        ┌────────────────┼────────────────┐
┌───────▼──────┐  ┌─────▼──────┐  ┌──────▼────────┐
│  SQLite      │  │  Chroma    │  │  Ollama       │
│  app.db      │  │  向量库     │  │  Qwen3-4B     │
│  11 张表      │  │            │  │  bge-m3       │
└──────────────┘  └────────────┘  └───────────────┘
```

---

## 🧠 LLM + 规则双轨设计（v3.0 核心）

### 为什么不用纯规则？

老版本用正则匹配意图，遇到这些问题：

| 用户输入 | 规则系统 | LLM 语义层 |
|---|---|---|
| "来两份大份的羊肉泡馍" | 正则拼凑，易错 | ✅ 一次解析出结构化 items |
| "10份" | 从历史猜菜名，常猜错 | ✅ 结合历史精准推断 |
| "取消刚刚的羊肉泡馍" | 词序反了就挂 | ✅ 提取 target="羊肉泡馍" |
| "把牛肉泡馍改成羊肉泡馍" | 需要专门正则 | ✅ 直接识别 modify_order |
| "有推荐吗" | 没这个意图 | ✅ recommend |
| "。。。" | 走 RAG，胡回复 | ✅ other |
```

---

### 为什么不纯 LLM？

- **延迟**：模型推理 1-3 秒，纯 LLM 每个"你好"都要等
- **幻觉**：4B 模型会编造菜单里没有的菜
- **稳定性**：Ollama 挂了整个系统就停

### 双轨架构

```
用户输入
  ↓
_get_intent_result()
  ├─ USE_LLM_PARSER=1 → llm_parser.parse()
  │     ├─ 成功 → 结构化 dict（含白名单校验）
  │     └─ 超时/失败 → 降级 ↓
  └─ 规则 intent_service.classify_intent()
  ↓
chat_service 分发
  ├─ FAQ 快路径（< 5ms，覆盖 40+ 高频问题）
  ├─ place_order / cancel_order / cancel_all / modify_order
  ├─ query_menu / query_total / query_location / query_hours
  ├─ recommend（个性化推荐）
  └─ 兜底 → RAG（Ollama + Chroma 语义检索）
```

**开关**：`USE_LLM_PARSER=1`（环境变量），默认关闭。

---

## 🛠 技术栈

| 层 | 技术 |
|---|---|
| **前端** | 原生 HTML5 / CSS3 / JavaScript、Jinja2、Chart.js 4.4 |
| **后端** | Flask 3.1、Gunicorn、Waitress |
| **LLM** | Ollama + Qwen3-4B（对话 + 意图）、`format: json` 结构化输出 |
| **RAG** | LangChain、OllamaEmbeddings(bge-m3)、Chroma 向量库 |
| **数据** | SQLite（WAL）、JSON（菜单等读多写少场景） |
| **认证** | PyJWT（双轨：会员 Bearer + 管理员 Cookie） |
| **二维码** | qrcode + Pillow |
| **测试** | pytest、pytest-flask |
| **部署** | Docker、docker-compose、cpolar 内网穿透 |

---

## 🚀 快速开始

### 前置要求
- Python 3.11+
- Ollama（本地大模型）
- Docker Desktop（可选）
- 6GB+ 显存

### 1. 拉取模型

```bash
ollama pull modelscope.cn/Qwen/Qwen3-4B-GGUF:latest
ollama pull bge-m3
```

### 2. 安装依赖

```bash
python -m venv venv
venv\Scripts\activate           # Windows
source venv/bin/activate        # Linux/Mac

pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
python scripts/migrate_json_to_sqlite.py
python scripts/init_admin.py
```

### 4. 启动

```bash
# 开发模式
python app.py

# 生产模式（Windows 友好）
python server.py

# Docker
docker compose up -d
```

### 5. 访问

| 页面 | 地址 |
|---|---|
| 首页 | http://127.0.0.1:5000/ |
| 菜单 | http://127.0.0.1:5000/menu |
| AI 客服 | http://127.0.0.1:5000/chat |
| 我的 | http://127.0.0.1:5000/profile |
| **后台** | http://127.0.0.1:5000/admin/login |
| 健康检查 | http://127.0.0.1:5000/health |
| Swagger | http://127.0.0.1:5000/api/docs |

**默认管理员：`admin` / `admin888`（上线前必改）**
```

---

---

## 📡 API 一览（50+ 接口）

### 用户端

| 分类 | 接口 |
|---|---|
| 认证 | `POST /api/auth/register` `POST /api/auth/login` `GET /api/auth/me` |
| 菜单 | `GET /api/menu` |
| AI | `POST /api/chat` `POST /api/chat/stream`（SSE）`POST /api/chat/clear` |
| 订单 | `GET /api/user/orders` `POST /api/order/<id>/pay` `POST /api/order/<id>/cancel` |
| 积分 | `GET /api/points/me` `POST /api/points/exchange` |
| 留言 | `POST /api/message` |
| 埋点 | `POST /api/track` |
| 订单跟踪 | `GET /order/<id>`（公开页面） |

### 后台管理（需 JWT Cookie）

| 分类 | 接口 |
|---|---|
| 认证 | `POST /admin/login` `POST /admin/logout` |
| 看板 | `GET /admin/dashboard` `GET /admin/api/stats` |
| 订单 | `GET /admin/api/orders` `POST /admin/api/orders/<id>/status` `GET /admin/api/orders/export` |
| AI 记录 | `GET /admin/api/chat-logs` |
| 用户 | `GET /admin/api/users` `POST /admin/api/users/<uid>/points` `POST /admin/api/users/<uid>/disabled` |
| 留言 | `GET /admin/api/messages` `POST /admin/api/messages/<id>/read` |
| 日志 | `GET /admin/api/logs` |
| 知识库 | `GET /admin/api/kb/versions` `POST /admin/api/kb/rollback/<id>` |
| 桌码 | `GET /admin/api/tables` `POST /admin/api/tables` `DELETE /admin/api/tables/<id>` `GET /admin/api/tables/<no>/qrcode.png` |

---

## 🗄️ 数据库设计（11 张表）

| 表 | 说明 | 关键字段 |
|---|---|---|
| `users` | 会员 | uid(PK)、username、points、level、disabled |
| `orders` | 订单 | id(PK)、uid、table_no、items(JSON)、total、status |
| `messages` | 留言 | id、name、content、read |
| `chat_logs` | AI 对话记录 | uid、question、answer、intent、elapsed_ms |
| `events` | 埋点 | event、payload(JSON)、uid、ip、date |
| `admin_users` | 后台账号 | username、password_hash、role |
| `admin_logs` | 操作日志 | admin_id、action、target、detail |
| `tables` | 桌码 | table_no(UNIQUE)、scan_count |
| `kb_history` | 知识库版本 | filename、content、version |
| `points_log` | 积分流水 | uid、change、reason |

**订单状态机**：`pending → paid → cooking → done`（或 `cancelled`）

---

## 🐳 Docker 部署

`docker-compose.yml` **已配置源码挂载**：

```yaml
volumes:
  - ./data:/app/data
  - ./vector_store:/app/vector_store
  - ./knowledge_docs:/app/knowledge_docs
  - ./logs:/app/logs
  # 源码挂载：改代码不用 rebuild
  - ./app.py:/app/app.py
  - ./routes:/app/routes
  - ./services:/app/services
  - ./repositories:/app/repositories
  - ./utils:/app/utils
  - ./configs:/app/configs
  - ./templates:/app/templates
  - ./static:/app/static
```

### 开发流程（重点）

| 改什么 | 命令 | 耗时 |
|---|---|---|
| Python 代码 | `docker compose restart` | 2-3 秒 |
| 模板 / CSS / JS | 浏览器 Ctrl+Shift+R | 0 秒 |
| requirements.txt | `docker compose build && up -d` | 1-3 分钟 |
| Dockerfile / yml | `down && build && up -d` | 1-3 分钟 |

日常 90% 场景：改 Python → `restart`（3 秒），改模板 → 刷新（0 秒）。**再也不 rebuild。**

---

## 🌐 内网穿透（cpolar）

```bash
cpolar http 5000
# Forwarding  https://xxxxxx.r6.cpolar.cn -> http://localhost:5000
```

拿到公网域名后，到后台 `/admin/tables`：
- "扫码地址前缀" 填 `https://xxxxxx.r6.cpolar.cn`
- 重新生成桌码，手机 4G 扫码即可用

---

## 🧪 测试

```bash
python -m pytest

# 输出
==================== 22 passed in 9s ====================
```

覆盖：菜单 API / 订单创建 / 状态流转 / 留言 / 认证接口。

---

## 📊 项目数据

| 指标 | 数值 |
|---|---|
| 代码行数 | 6000+ |
| 后台模块 | 10 |
| 数据库表 | 11 |
| API 接口 | 50+ |
| 页面数 | 6 前台 + 9 后台 |
| 单元测试 | 22 |
| LLM 意图类别 | 11 |
| 订单状态 | 5 |
| Docker 镜像 | ~800MB |
| 前端加载 | ~100KB |
```

---

---

## 🔑 关键设计

### 1. LLM 双轨（语义 + 规则兜底）

```python
def _get_intent_result(self, message, history_text=''):
    try:
        from services.llm_parser import parse as llm_parse, is_enabled
        if is_enabled():
            r = llm_parse(message, history=history_text)
            if r and r.get('intent'):
                return r        # LLM 成功
    except Exception as e:
        logger.warning(f'LLM 异常，降级规则: {e}')
    return intent_service.classify_intent(message, history=history_text)
```

**LLM 关闭/失败 → 无缝切回规则，用户无感。**

### 2. FAQ 快路径（< 5ms 覆盖 40+ 高频问题）

```python
STORE_FAQ = {
    '地址': '同盛祥在西安市碑林区老巷子 88 号...',
    '营业时间': '每天 10:30 至次日 02:00...',
    '老汤': '每天凌晨四点开始吊汤，牛骨+羊肉+二十余味香料...',
    # ... 40+ 条
}
```

**覆盖 90% 高频问答，避开 3-8 秒的 RAG 生成耗时。**

### 3. RAG 三级路由

```
1. 菜单关键词 → 快路径（10ms，不加载 bge-m3）
2. 门店专属问题 → RAG 检索（bge-m3 + Chroma）
3. 通用问题 → 直接调 Qwen3（不检索）
```

### 4. 三层防御（防小模型幻觉）

| 层 | 手段 |
|---|---|
| Prompt | 明确禁止输出「用户/助手」标签 |
| 模型 | `stop=["用户：", "助手："]` + `think: False` |
| 后端 | 字符串查找 + 截断 |
| LLM Parser | 菜名白名单校验（不在菜单里直接丢弃） |

### 5. 积分规则

```
下单 → 不加积分
付款（pending → paid）→ +N 积分
付款后取消（paid → cancelled）→ -N 积分（允许负数）
付款前取消（pending → cancelled）→ 不动
```

---

## 🎯 简历亮点

- **从 Demo 到运营**：v1.0 → v3.0，从"能演示"到"能上线"
- **LLM 工程化**：LLM + 规则双轨 + 降级 + 白名单校验的完整方案
- **本地 RAG**：LangChain + Ollama + Chroma，中文语义检索
- **10 个后台模块**：完整运营系统
- **SQLite 存储升级**：WAL 模式支持多 worker
- **扫码点单闭环**：qrcode 生成 + 桌号自动识别 + 订单绑定
- **双主题系统**：CSS 变量 + 类名切换
- **工程化**：Docker 源码挂载、22 个 pytest 用例、Gzip 压缩
- **零成本**：本地模型 + 免费内网穿透

---

## 📝 TODO

- [ ] 接入真实微信支付
- [ ] 知识库文件上传（PDF/Word → markdown）
- [ ] pytest 覆盖扩展（22 → 50+）
- [ ] 云服务器部署 + Nginx + HTTPS
- [ ] CI/CD（GitHub Actions）
- [ ] 多店 SaaS 化（v4.0）

---

## 📄 License

MIT

---

## 👨‍💻 作者

**你的名字** · [GitHub](https://github.com/yourname)
