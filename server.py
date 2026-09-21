# server.py
"""生产环境启动脚本（Windows 友好）"""
import os
from waitress import serve
from app import app, warmup

if __name__ == '__main__':
    # 先预热 AI 服务
    warmup()

    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    threads = int(os.environ.get('THREADS', 8))

    print(f"=== Waitress 启动 http://{host}:{port} (threads={threads}) ===")
    serve(app, host=host, port=port, threads=threads)