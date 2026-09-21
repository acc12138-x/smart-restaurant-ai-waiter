import os


class Config:
    """基础配置"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me-please-override-in-prod-32bytes')

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    DOCS_DIR = os.path.join(BASE_DIR, 'knowledge_docs')
    VECTOR_DIR = os.path.join(BASE_DIR, 'vector_store')
    LOG_DIR = os.path.join(BASE_DIR, 'logs')

    CHAT_MODEL = "modelscope.cn/Qwen/Qwen3-4B-GGUF:latest"
    EMBED_MODEL = "bge-m3"

    ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'admin-token-dev')


class DevConfig(Config):
    DEBUG = True
    ENV = 'development'


class ProdConfig(Config):
    DEBUG = False
    ENV = 'production'


config_map = {
    'development': DevConfig,
    'production': ProdConfig,
}


def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    return config_map.get(env, DevConfig)