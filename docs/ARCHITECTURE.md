# 技术架构文档

## 一、整体架构

### 1.1 分层设计

```
┌──────────────────────────────────────────┐
│  路由层（routes/）                        │
│  只负责：接收请求、调用服务、返回响应      │
│  不包含任何业务逻辑                        │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│  服务层（services/）                      │
│  业务逻辑核心：菜单、订单、AI、积分        │
│  不直接操作文件，通过 Repository 访问数据  │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│  数据层（repositories/）                  │
│  抽象接口 BaseRepository                  │
│  当前实现 JsonRepository，可平滑升级 MySQL│
└──────────────────────────────────────────┘
```

### 1.2 数据流示例：AI 点菜

```
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
    ├── 追问检测（省略句拼接）
    ├── intent_service.classify_intent()  → 意图 = place_order
    ├── 若含 items → order_service.create()
    │   ├── menu_service.find_dish()  → 匹配菜品
    │   ├── 计算总价
    │   ├── order_repo.create()       → 写入 JSON
    │   └── points_service.add_points() → 加积分
    └── 返回 reply, intent, order
    ↓
前端渲染订单卡片
```

---

## 二、RAG 实现细节

### 2.1 完整链路

| 步骤 | 组件 | 参数 |
|---|---|---|
| 1. 加载 | TextLoader | encoding=utf-8 |
| 2. 切分 | RecursiveCharacterTextSplitter | chunk_size=80, overlap=10 |
| 3. 向量化 | OllamaEmbeddings | bge-m3, 1024维 |
| 4. 存储 | Chroma | 本地持久化 |
| 5. 检索 | as_retriever | k=6 |
| 6. 生成 | ChatOllama | Qwen3-4B, temperature=0.1 |
| 7. 解析 | StrOutputParser | 纯文本输出 |

### 2.2 为什么选 bge-m3

| 模型 | 维度 | 语言 | 中文效果 |
|---|---|---|---|
| nomic-embed-text | 768 | 英文为主 | 查营业时间匹配不到 10:30 |
| bge-m3 | 1024 | 中英双语 | 智源研究院，中文 RAG 标配 |

踩坑记录：换嵌入模型必须删 vector_store 重建，否则报维度不匹配。

### 2.3 三层防御体系

问题：4B 模型会模仿 FAQ 格式，输出用户/助手标签，甚至自问自答。

解决：

```python
# 第一层：Prompt 禁止
prompt = "...不要在回答里出现用户/助手这类字样..."

# 第二层：模型 stop 参数
ChatOllama(stop=["用户：", "助手：", "问题：", "回答："])

# 第三层：后端清洗
for marker in ["用户：", "助手："]:
    idx = answer.find(marker)
    if idx > 0:
        answer = answer[:idx].strip()
```

工程价值：不依赖模型听话，任何模型接入都能稳定工作。

### 2.4 追问检测

问题：用户说「羊肉呢」「我要一份」，省略了关键信息。

解决：

```python
def _is_followup(self, message):
    if len(message) > 12: return False
    return any(w in message for w in ['呢', '那个', '一份'])

if self._is_followup(message):
    last_q = self._find_last_user_msg(uid)
    full_message = f"{last_q} {message}"
```

效果：

| 用户输入 | 拼后发给 RAG |
|---|---|
| 羊肉呢 | 牛肉泡馍多少钱 羊肉呢 |
| 我要一份 | 牛肉泡馍多少钱 我要一份 |

---

## 三、双主题系统

### 3.1 实现原理

CSS 变量 + body 类名切换。

```css
:root {
  --bg: #FFFFFF;
  --font-base: 14px;
  --radius: 20px;
}

body.mode-elder {
  --bg: #FFF6E6;
  --font-base: 20px;
  --radius: 10px;
}

body.mode-elder * {
  animation-duration: .01ms !important;
  transition-duration: .01ms !important;
}
```

### 3.2 防闪屏

```html
<script>
(function(){
  var m = localStorage.getItem('tsx-mode');
  if (m === 'elder') document.documentElement.classList.add('pre-elder');
})();
</script>
<style>
  html.pre-elder body { visibility: hidden; }
</style>
```

common.js 加载后移除 pre-elder，避免主题切换时闪屏。

---

## 四、认证系统

### 4.1 JWT 流程

```
注册/登录
    ↓
bcrypt 哈希密码 → 存入 members.json
    ↓
PyJWT 生成 token（含 uid、username、exp）
    ↓
前端存 localStorage
    ↓
后续请求带 Authorization: Bearer <token>
    ↓
@login_required 装饰器验证 → g.uid
```

### 4.2 装饰器实现

```python
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            raise AuthError('缺少登录凭证')
        payload = auth_service.verify_token(auth[7:])
        g.uid = payload['uid']
        return f(*args, **kwargs)
    return wrapper
```

---

## 五、数据存储设计

### 5.1 为什么用 JSON

| 维度 | JSON | MySQL |
|---|---|---|
| 部署 | 零依赖 | 需装服务 |
| 演示 | 打开即懂 | 需工具 |
| 版本控制 | git diff 友好 | 二进制 |
| 并发 | 不支持 | 支持 |
| 数据量 | < 1万条 | 百万级 |

结论：沙盘演示场景，JSON 是最优解。

### 5.2 升级路径

BaseRepository 抽象接口，未来加 MySQLRepository 业务代码零改动。

---

## 六、性能优化

| 优化 | 手段 | 效果 |
|---|---|---|
| Gzip 压缩 | after_request 钩子 | 文本减 70% |
| 视频压缩 | ffmpeg -crf 28 | 570KB → 200KB |
| 静态缓存 | Flask 自动 ETag | 二次访问 304 |
| 单例模式 | 全局变量缓存 | 避免重复加载模型 |
| 启动预热 | warmup() | 首次请求不等 |
| 向量库持久化 | Chroma 本地文件 | 重启秒加载 |

---

## 七、部署方案

### 7.1 本地开发

```bash
python server.py    # Waitress，8 线程
```

### 7.2 Docker 生产

```yaml
services:
  app:
    build: .
    ports: ["5000:5000"]
    environment:
      - OLLAMA_HOST=http://host.docker.internal:11434
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

Gunicorn 配置：4 worker，120s 超时。

### 7.3 内网穿透

```bash
cpolar http 5000
```

---

## 八、踩坑记录

| 坑 | 现象 | 解决 |
|---|---|---|
| 英文嵌入模型 | 中文检索命中率低 | 换 bge-m3 |
| 维度不匹配 | expecting 768, got 1024 | 删 vector_store |
| FAQ 格式被照抄 | 输出带用户/助手标签 | 三层防御 |
| 小模型自问自答 | 无限循环 | stop 参数 |
| Windows Gunicorn | fcntl 模块不存在 | 换 Waitress |
| Docker 构建失败 | llama_cpp_python 不兼容 | 从 requirements 删掉 |
| apt 源超时 | deb.debian.org 连不上 | 换清华源 |
| 代码改动不生效 | restart 不管用 | 必须 build |

---

## 九、未来规划

- [ ] Function Calling：标准化的工具调用
- [ ] 流式输出：SSE 逐字返回
- [ ] 知识库热更新：管理页在线编辑
- [ ] 云服务器部署：阿里云 + Nginx + HTTPS
- [ ] CI/CD：GitHub Actions 自动测试
- [ ] 接入真实支付

---

最后更新：2026-09-19
