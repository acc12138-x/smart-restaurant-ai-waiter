# rag_service.py
import os
import shutil
import requests
import json as _json
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from configs.config import get_config
from utils.logger import logger

# ============ 配置 ============


_cfg = get_config()

DOCS_DIR      = _cfg.DOCS_DIR
VECTOR_DIR    = _cfg.VECTOR_DIR
EMBED_MODEL   = _cfg.EMBED_MODEL
CHAT_MODEL    = _cfg.CHAT_MODEL

# ============ 全局单例 ============
_llm         = None
_embeddings  = None
_vectorstore = None
_rag_chain   = None

# 简单内存缓存：question -> (answer, timestamp)
_QA_CACHE = {}
_CACHE_TTL = 600  # 10 分钟


import os

def _normalize_ollama_host():
    """规范化 OLLAMA_HOST：
    - 补 http:// 前缀
    - 0.0.0.0 改成 127.0.0.1（客户端访问用）
    """
    host = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')
    if not host.startswith('http://') and not host.startswith('https://'):
        host = 'http://' + host
    host = host.replace('0.0.0.0', '127.0.0.1')
    return host

OLLAMA_HOST = _normalize_ollama_host()


def get_llm():
    global _llm
    if _llm is None:
        logger.info(f"[RAG] 连接 Ollama 对话模型 {CHAT_MODEL} @ {OLLAMA_HOST} ...")
        _llm = ChatOllama(
            model=CHAT_MODEL,
            temperature=0.1,
            num_ctx=4096,
            num_predict=600,
            base_url=OLLAMA_HOST,
            model_kwargs={"think": False},  # ← 新增
        )
        logger.info("[RAG] 对话模型就绪")
    return _llm


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        logger.info(f"[RAG] 连接 Ollama 嵌入模型 {EMBED_MODEL} @ {OLLAMA_HOST} ...")
        _embeddings = OllamaEmbeddings(
            model=EMBED_MODEL,
            base_url=OLLAMA_HOST,        # ← 新增
        )
    return _embeddings


def _load_documents():
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR, exist_ok=True)
        print(f"[RAG] 已创建 {DOCS_DIR}/ ，请把文档放进去")
        return []

    docs = []
    for f in os.listdir(DOCS_DIR):
        path = os.path.join(DOCS_DIR, f)
        try:
            if f.endswith(".txt") or f.endswith(".md"):
                docs.extend(TextLoader(path, encoding="utf-8").load())
            elif f.endswith(".pdf"):
                docs.extend(PyPDFLoader(path).load())
        except Exception as e:
            print(f"[RAG] 加载 {f} 失败: {e}")
    return docs


def _build_vectorstore():
    global _vectorstore
    docs = _load_documents()
    if not docs:
        print("[RAG] 知识库为空")
        return None

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=250,      # 优化：80 → 250，减少切块数量
        chunk_overlap=30,    # 优化：10 → 30
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )
    chunks = splitter.split_documents(docs)
    print(f"[RAG] 切分为 {len(chunks)} 个文本块，开始向量化...")

    _vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        persist_directory=VECTOR_DIR,
    )
    print("[RAG] 向量库构建完成")
    return _vectorstore


def load_or_build_vectorstore():
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore

    # 判断 vector_store 目录里有没有内容
    has_content = False
    if os.path.exists(VECTOR_DIR):
        for item in os.listdir(VECTOR_DIR):
            if item != '.gitkeep':
                has_content = True
                break

    if has_content:
        try:
            print("[RAG] 加载已有向量库")
            _vectorstore = Chroma(
                persist_directory=VECTOR_DIR,
                embedding_function=get_embeddings(),
            )
        except Exception as e:
            print(f"[RAG] 加载失败，重建: {e}")
            _vectorstore = _build_vectorstore()
    else:
        _vectorstore = _build_vectorstore()
    return _vectorstore

def get_rag_chain():
    global _rag_chain
    if _rag_chain is not None:
        return _rag_chain

    vs = load_or_build_vectorstore()
    if vs is None:
        return None

    retriever = vs.as_retriever(search_kwargs={"k": 3})

    prompt = PromptTemplate.from_template(
        "你是西安同盛祥泡馍老店的客服助手。\n"
        "请根据下面的资料回答用户问题，只回答一句。\n"
        "如果资料里同时有【菜单价格】和【品牌介绍】，优先用价格回答。\n"
        "资料里完全没有的信息，才说「抱歉，我这边没有这方面的信息」。\n\n"
        "资料：\n{context}\n\n"
        "用户：{question}"
    )

    _rag_chain = (
        {"context": retriever, "question": RunnablePassthrough()}
        | prompt
        | get_llm()
        | StrOutputParser()
    )
    print("[RAG] RAG 链就绪")
    return _rag_chain


# ============ 对外接口 ============
def chat_with_rag_stream(question: str, history: str = ''):
    """流式问答
    三级路由：
    1. 菜单关键词 → 快路径（10ms）
    2. 门店专属问题 → RAG 检索
    3. 通用问题 → 直接调 Qwen3
    带内存缓存（相同问题 10 分钟内直返）
    """
    import re
    import time
    from services.menu_service import menu_service

    q = question.strip()

    # ========== 缓存命中 ==========
    now = time.time()
    cached = _QA_CACHE.get(q)
    if cached and (now - cached[1]) < _CACHE_TTL:
        yield cached[0]
        return

    # 缓存清理（超过 TTL 的）
    if len(_QA_CACHE) > 200:
        expired = [k for k, v in _QA_CACHE.items() if now - v[1] > _CACHE_TTL]
        for k in expired:
            _QA_CACHE.pop(k, None)

    # ============ 1. 菜单关键词快路径 ============
    query = re.sub(
        r'(多少钱|价格|呢|吗|几块|是啥|是什么|怎么卖|的|了|有没有|有|一份|两份|三份|我要|来一|来两|来三|点一|点两|点三|要一|要两|要三|给我|我想吃|我想|吃)',
        '', q
    )
    query = query.strip()
    query_clean = query.replace('(', '').replace(')', '').replace('（', '').replace('）', '').strip()

    # 过滤常见语气词，避免"好的" → "好" → 匹配到"糖蒜(剥好)"
    TONE_WORDS = ['好的', '好呀', '好嘞', '行吧', '可以', '嗯', 'OK', 'ok',
                  '不用', '没事', '算了', '谢谢', '多谢', '谢了',
                  '好吧', '好吧', '行', '好', '哦', '噢', '啊', '呀', '哈']
    if query_clean in TONE_WORDS:
        query_clean = ''

    matched_dishes = []
    # 最小长度 2 个字符才做匹配，避免单字误伤
    if len(query_clean) >= 2:
        for dish in menu_service.get_flat():
            name = dish['name']
            name_clean = name.replace('(', '').replace(')', '').replace('（', '').replace('）', '')
            # 只有"菜名被包含" 或 "菜名包含用户输入"才算匹配，且两边长度都≥2
            if len(name_clean) >= 2 and (
                query_clean in name_clean or name_clean in query_clean
            ):
                matched_dishes.append(dish)

    if matched_dishes:
        if len(matched_dishes) == 1:
            d = matched_dishes[0]
            reply = f"{d['name']}：{d['price']} 元。{d.get('desc', '')}"
        else:
            lines = [f"{d['name']}：{d['price']} 元" for d in matched_dishes]
            reply = "，".join(lines) + "。"
        yield reply
        return

    # ============ 2. 判断是否门店专属问题 ============
    STORE_KEYWORDS = [
        '多少钱', '价格', '几块', '贵不贵',
        '地址', '在哪', '位置', '怎么走', '怎么去', '交通', '地铁', '导航',
        '几点', '营业', '关门', '开门', '打烊', '营业时间',
        '电话', '号码', '联系',
        '什么时候开', '创立', '开业', '哪年', '什么时候成立',
        '老汤', '三十年', '1994', '历史', '故事', '翻新', '装修',
    ]
    is_store_question = any(kw in q for kw in STORE_KEYWORDS)

    # ============ 3. 组装 context ============
    context = ''
    if is_store_question:
        # 只有门店专属问题才加载 bge-m3 检索
        t0 = time.time()
        vs = load_or_build_vectorstore()
        if vs is not None:
            try:
                retriever = vs.as_retriever(search_kwargs={"k": 6})
                docs = retriever.invoke(question)
                context = '\n'.join(d.page_content for d in docs)
            except Exception:
                context = ''
        elapsed_ms = (time.time() - t0) * 1000
        print(f"[RAG] 门店问题检索耗时 {elapsed_ms:.0f}ms")

    # ============ 4. 调 Qwen3 生成 ============
    full_text = ''
    for chunk in chat_with_ollama_native(question, context, history):
        full_text += chunk
        yield chunk

    # 缓存完整回答
    if full_text.strip():
        _QA_CACHE[q] = (full_text, time.time())

def chat_plain(question: str) -> str:
    try:
        return get_llm().invoke(question).content
    except Exception as e:
        return f"出错了：{e}"


def rebuild_knowledge_base():
    """重建知识库（不删目录，避免 Docker 资源占用）"""
    global _vectorstore, _rag_chain

    # 1. 释放当前实例
    _vectorstore = None
    _rag_chain = None

    # 2. 尝试清空 vector_store 目录内容（不删目录本身）
    if os.path.exists(VECTOR_DIR):
        for item in os.listdir(VECTOR_DIR):
            path = os.path.join(VECTOR_DIR, item)
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
            except Exception as e:
                print(f"[RAG] 清理 {path} 失败（忽略）: {e}")

    # 3. 重新构建
    return _build_vectorstore()
def chat_with_ollama_native(question: str, context: str, history: str = ''):
    """直接用 Ollama 原生 API 流式输出"""
    user_content = f"{history}\n用户：{question}" if history else question

    prompt = (
        "你是西安同盛祥泡馍老店的店员小同。请按以下规则回答：\n\n"
        "【有资料时（门店专属问题）】\n"
        "严格依据下面的【资料】回答价格、地址、营业时间、电话等问题。"
        "资料里没有的，说「抱歉，这个我暂时没有准确信息」。"
        "绝对不要编造价格、地址、电话。\n\n"
        "【无资料时（通用问题）】\n"
        "涉及吃法、口味、推荐、搭配、解腻、特色等通用问题时，"
        "用你自己的知识回答，要具体、有画面感、说老店行话。\n"
        "参考风格：\n"
        "- 泡馍怎么吃 → 「馍掰成黄豆大小，越小越入味，配糖蒜和辣子酱，最后来口汤」\n"
        "- 怎么解腻 → 「来份糖蒜或者凉皮，喝口酸梅汤，比冰峰更清爽」\n"
        "- 第一次来点什么 → 「招牌牛肉泡馍小份，加凉拌黄瓜，配瓶冰峰，人均40上下」\n"
        "两到三句话，口语化，像店员跟客人聊天。\n\n"
        "【健康医疗问题（严格）】\n"
        "涉及糖尿病、高血压、孕妇、过敏、忌口等健康问题时，"
        "绝对不能推荐具体菜品！只说：\n"
        "「这个建议您以医生或营养师的建议为准。如果您来店里，"
        "可以告诉店员您的忌口，我们帮您调整汤的油盐量和配菜。」\n\n"
        "【格式要求】\n"
        "不要输出「用户：」「助手：」标签，不要重复问题，语气亲切自然。\n\n"
        f"【资料（可能为空）】\n{context}\n\n"
        f"【用户提问】\n{user_content}\n\n"
        "【回答】"
    )

    url = f"{OLLAMA_HOST}/api/chat"
    payload = {
        "model": CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "think": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 120,
        }
    }

    try:
        with requests.post(url, json=payload, stream=True, timeout=120) as r:
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    data = _json.loads(line)
                except Exception:
                    continue
                content = data.get("message", {}).get("content", "")
                if content:
                    yield content
    except Exception as e:
        yield f"出错了：{e}"