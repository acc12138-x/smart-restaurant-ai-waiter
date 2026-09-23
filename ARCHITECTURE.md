# 技术架构文档

## 一、整体架构

### 1.1 分层设计

{T3}
┌──────────────────────────────────────────┐
│  路由层（routes/）                        │
│  只负责：接收请求、调用服务、返回响应       │
│  不包含任何业务逻辑                        │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│  服务层（services/）                      │
│  业务逻辑核心：LLM、订单、库存、通知        │
│  不直接操作文件，通过 Repository 访问数据   │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│  数据层（repositories/）                  │
│  抽象接口 BaseRepository                  │
│  实现 SqliteRepository / JsonRepository  │
└──────────────────────────────────────────┘
{T3}

### 1.2 数据流示例：AI 点菜

{T3}
用户输入 "来两份牛肉泡馍"
    ↓
POST /api/chat
    ↓
routes/api_routes.py :: api_chat()
    ├── 解析 token → uid
    ├── 调用 chat_service.chat(msg, uid)
    ↓
services/chat_service.py
    ├── session_service.format_history()  → 取历史
    ├── session_service.add(user 消息)
    ├── _get_intent_result()  → LLM 或规则
    ├── 若含 items → order_service.create()
    │   ├── menu_service.find_dish()  → 匹配菜品
    │   ├── 计算总价 + 扣库存
    │   ├── order_repo.create()       → 写入 DB
    │   └── notify_service.notify_new_order() → 企微推送
    └── 返回 reply, intent, order
    ↓
前端渲染订单卡片
{T3}

---

## 二、LLM 双轨架构

### 2.1 为什么双轨

| 维度 | 纯规则 | 纯 LLM | 双轨（本项目）|
|---|---|---|---|
| 延迟 | < 5ms | 1-3s | 快路径 < 5ms，复杂 1-3s |
| 准确率（口语） | 低 | 高 | 高 |
| 幻觉 | 无 | 有 | 无（白名单校验）|
| Ollama 挂了 | 不受影响 | 全挂 | 降级规则，用户无感 |
| 成本 | 零 | 本地 GPU / API 费 | 一致 |

### 2.2 双轨流程

{T3}
用户输入
  ↓
chat_service._get_intent_result()
  ├─ 1. 规则先跑 → accept_recommend / reject_recommend / leave_message 直接返回
  ├─ 2. LLM 开启 → llm_parser.parse()
  │     ├─ 成功 → 结构化 dict + 白名单校验
  │     └─ 超时/失败 → 降级 ↓
  └─ 3. 规则 intent_service.classify_intent()
  ↓
chat_service 分发（13 类意图）
  ├─ FAQ 快路径（门店信息，< 5ms）
  ├─ 点单 / 取消 / 改单
  ├─ 推荐 / 接受推荐 / 拒绝推荐
  ├─ 留言
  └─ 兜底 → RAG（Ollama + Chroma）
{T3}

### 2.3 白名单校验

LLM 返回的菜名必须在 `menu.json` 里，否则丢弃：

{T3}python
def _normalize_items(items, menu_names):
    menu_set = set(menu_names)
    result = []
    for it in items:
        dish = it.get('dish', '').strip()
        if dish not in menu_set:
            # 尝试模糊匹配
            matched = next((m for m in menu_names if dish in m or m in dish), None)
            if not matched:
                logger.warning('[LLM] 菜名不在菜单: ' + dish)
                continue
            dish = matched
        result.append({'name': dish, 'qty': min(50, max(1, int(it.get('qty', 1))))})
    return result
{T3}

### 2.4 三层防御（防小模型胡言乱语）

| 层 | 手段 |
|---|---|
| Prompt | 明确禁止输出"用户：""助手：" |
| 模型 | `stop=["用户：", "助手："]` + `think: False` |
| 后端 | 字符串查找 + 截断 + 清理 |

---

## 三、RAG 实现

### 3.1 链路

| 步骤 | 组件 | 参数 |
|---|---|---|
| 1. 加载 | TextLoader / PyPDFLoader | encoding=utf-8 |
| 2. 切分 | RecursiveCharacterTextSplitter | chunk_size=250, overlap=30 |
| 3. 向量化 | OllamaEmbeddings | bge-m3, 1024 维 |
| 4. 存储 | Chroma | 本地持久化 |
| 5. 检索 | as_retriever | k=6 |
| 6. 生成 | ChatOllama | Qwen3-4B, temperature=0.1 |
| 7. 解析 | StrOutputParser | 纯文本 |

### 3.2 三级路由

{T3}
1. 菜单关键词 → 快路径（10ms，不加载 bge-m3）
2. 门店专属问题 → RAG 检索（bge-m3 + Chroma）
3. 通用问题 → 直接调 Qwen3（不检索）
{T3}

### 3.3 为什么选 bge-m3

| 模型 | 维度 | 语言 | 中文效果 |
|---|---|---|---|
| nomic-embed-text | 768 | 英文为主 | "查营业时间"匹配不到"10:30" |
| bge-m3 | 1024 | 中英双语 | 智源研究院，中文 RAG 标配 |

---

## 四、认证系统

### 4.1 JWT 双轨

| 类型 | 存储 | 有效期 | 用途 |
|---|---|---|---|
| 会员 | localStorage → Bearer | 24h | 用户端 |
| 管理员 | HttpOnly Cookie | 24h | 后台 |

### 4.2 密码存储

- **scrypt** 哈希（Werkzeug Security 默认算法）
- 加盐、迭代 32768 次
- 输出格式：`scrypt:32768:8:1$salt$hash`

### 4.3 限流

- 后台登录失败 **5 次 / 15 分钟** 锁定（按 IP + 用户名分别计数）

---

## 五、数据存储设计

### 5.1 SQLite 表结构（13 张表）

| 表 | 说明 | 关键字段 |
|---|---|---|
| `users` | 会员 | uid(PK)、username、points、level、disabled |
| `orders` | 订单 | id(PK)、uid、table_no、items(JSON)、total、status |
| `messages` | 留言 | id、name、content、read |
| `chat_logs` | AI 对话记录 | uid、question、answer、intent、elapsed_ms |
| `chat_sessions` | 对话历史（v3.9）| uid、role、content、ts |
| `events` | 埋点 | event、payload(JSON)、uid、ip、date |
| `admin_users` | 后台账号 | username、password_hash、role |
| `admin_logs` | 操作日志 | admin_id、action、target、detail |
| `tables` | 桌码 | table_no(UNIQUE)、scan_count |
| `kb_history` | 知识库版本 | filename、content、version |
| `points_log` | 积分流水 | uid、change、reason |
| `settings` | 系统配置（v3.9）| key(PK)、value、updated_at |
| `app_logs` | 应用日志（v3.9）| level、message、traceback、elapsed_ms |

### 5.2 为什么用 SQLite

| 维度 | SQLite | MySQL |
|---|---|---|
| 部署 | 零依赖 | 需装服务 |
| 备份 | 复制一个文件 | mysqldump |
| 并发 | WAL 模式多读 + 单写 | 支持 |
| 数据量 | < 10 万条最优 | 百万级 |
| 升级路径 | BaseRepository 抽象接口 | 平滑切换 |

### 5.3 订单状态机

{T3}
pending ──→ paid ──→ cooking ──→ done
   │         │           │
   ↓         ↓
cancelled  cancelled
{T3}

非法转换直接拦（`cooking` 不能退单，`done` 不能取消）。

---

## 六、关键设计决策

### 6.1 配置热更新

所有配置存 `settings` 表，`settings_service` 带内存缓存。改配置 → 写库 → 更新缓存 → **立即生效**，不用重启。

### 6.2 敏感字段脱敏

{T3}python
SENSITIVE_KEYS = {'api_key', 'wecom_webhook'}

def get_all(self, mask_sensitive=True):
    if mask_sensitive:
        for k in SENSITIVE_KEYS:
            if result.get(k):
                result[k + '_masked'] = _mask(result[k])  # sk-abc****xyz
                result[k] = ''
    return result
{T3}

### 6.3 异步通知

企业微信推送用 `threading.Thread` 后台发，**下单接口 100ms 内返回**，不等 webhook 响应。

### 6.4 慢请求监控

`before_request` 记开始时间，`after_request` 算耗时，> 3 秒自动写 `app_logs`。

### 6.5 多 worker 安全

`json_repo._write()` 捕获 `FileNotFoundError`（两个 worker 同时创建文件时，其中一个会失败，忽略即可）。

---

## 七、部署架构

### 7.1 本地开发

{T3}
python app.py
# 或
python server.py  (Waitress 8 线程)
{T3}

### 7.2 Docker 生产

{T3}
用户浏览器
   ↓ HTTPS
Nginx（宿主机）
   ├── SSL 证书
   └── 反代到 127.0.0.1:5000
   ↓
Docker 容器 tsx-app
   ├── Gunicorn（2 worker × 8 线程）
   └── Flask 应用
   ↓
SQLite（volume 挂载）
{T3}

### 7.3 云上 Ollama 方案

服务器内存 2GB，跑不动 Qwen3-4B。**云端走远程 API**：

| 层 | 位置 | 说明 |
|---|---|---|
| Flask | 云服务器 | 轻量，1.8GB 内存够用 |
| LLM | 阿里云百炼 Qwen API | 按量付费，千 tokens 几分钱 |
| RAG 向量库 | 云上 Chroma | 只读检索，不耗内存 |
| Embedding | 云端调用（可关）| 关掉不影响核心点单 |

**切换方式**：后台 `/admin/settings` → AI 大模型 → "使用方式" 选"远程 API"。

---

## 八、踩坑记录

| 坑 | 现象 | 解决 |
|---|---|---|
| 英文嵌入模型 | 中文检索命中率低 | 换 bge-m3 |
| 维度不匹配 | expecting 768, got 1024 | 删 vector_store 重建 |
| FAQ 格式被照抄 | 输出带"用户：""助手：" | 三层防御 + stop 参数 |
| 小模型自问自答 | 无限循环 | `stop=["用户：", "助手："]` |
| Windows Gunicorn | fcntl 模块不存在 | 换 Waitress |
| Docker 构建失败 | llama_cpp_python 不兼容 | 从 requirements 删掉 |
| apt 源超时 | deb.debian.org 连不上 | 换清华源 |
| 代码改动不生效 | restart 不管用 | 必须 build |
| **多 worker 竞争** | `FileNotFoundError: rag_logs.json.tmp` | `_write()` 捕获异常 |
| **pip 编码** | `gbk codec can't decode` | requirements 去中文注释 |
| **Dockerfile 报错** | `exclude-patterns` 非法字符 | `.dockerignore` 去中文 |
| **Ollama 容器访问** | `Connection refused 11434` | 云端切远程 API |
| **CI 缺 werkzeug** | `No module named 'werkzeug'` | requirements 显式列出 |
| **CI 缺 \_\_init\_\_.py** | `unknown location` | `.gitignore` 的 `_*.py` 改 `/_*.py` |

---

## 九、未来规划

- [ ] Nginx + HTTPS（阿里云已部署）
- [ ] CI/CD 自动部署（GitHub Actions → SSH）
- [ ] frp 反代本机 Ollama（省 API 费）
- [ ] 知识库文件上传（PDF / Word）
- [ ] pytest 覆盖率扩展到 50%+
- [ ] 多店 SaaS 化（v4.0）

---

最后更新：2026-09-23
