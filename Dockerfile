FROM python:3.12-slim

WORKDIR /app

# 换成清华 Debian 镜像源（避免访问国外源超时）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null || true

# 不装 gcc（项目已去掉需要编译的包）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://mirrors.aliyun.com/pypi/simple/

COPY . .

RUN mkdir -p logs data vector_store

EXPOSE 5000

ENV FLASK_ENV=production \
    PYTHONUNBUFFERED=1

CMD ["gunicorn", "-k", "gthread", "-w", "2", "--threads", "8", "-b", "0.0.0.0:5000", \
     "--timeout", "300", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]