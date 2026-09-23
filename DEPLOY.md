# 云服务器部署指南

> 从零开始，把项目部署到阿里云轻量服务器。预计 30 分钟完成。

## 一、前置准备

### 1.1 服务器要求
- CPU: 2 核 / 内存: 2GB+ / 硬盘: 40GB
- 系统: Alibaba Cloud Linux / Ubuntu 20.04+ / CentOS 7+
- 建议阿里云轻量应用服务器（学生价 ~60 元/年）

### 1.2 域名（可选，上 HTTPS 才需要）
阿里云注册域名 + 免费备案（7-20 天）

### 1.3 本地准备
{T3}bash
git add -A
git commit -m "ready to deploy"
git push origin main
{T3}

### 1.4 重置服务器密码
阿里云控制台 → 找到服务器 → 更多 → 重置密码 → 重启

## 二、服务器初始化

### 2.1 SSH 连接
{T3}bash
ssh root@你的服务器公网IP
{T3}
首次连接输 yes 确认指纹，再输密码。

如果报 Permission denied (publickey)：
{T3}bash
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@你的IP
{T3}

### 2.2 装 Docker（如未预装）
{T3}bash
docker version
{T3}
未装则：
{T3}bash
# Alibaba Cloud Linux / CentOS / RHEL
dnf install -y dnf-utils git

# Ubuntu / Debian
apt update && apt install -y git curl
curl -fsSL https://get.docker.com | sh

systemctl enable --now docker
{T3}

### 2.3 配 Docker 镜像加速
{T3}bash
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerproxy.com",
    "https://mirror.baidubce.com"
  ],
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
systemctl restart docker
{T3}

### 2.4 装 Docker Compose
{T3}bash
dnf install -y docker-compose-plugin
{T3}
装不上则用二进制：
{T3}bash
curl -SL "https://gh-proxy.com/https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
mkdir -p /usr/local/lib/docker/cli-plugins
ln -sf /usr/local/bin/docker-compose /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version
{T3}

## 三、部署应用

### 3.1 拉代码
{T3}bash
mkdir -p /root/apps && cd /root/apps
git clone https://gh-proxy.com/https://github.com/acc12138-x/smart-restaurant-ai-waiter.git
cd smart-restaurant-ai-waiter
{T3}
私有仓库用：
{T3}bash
git clone https://用户名:token@github.com/用户名/仓库名.git
{T3}

### 3.2 预创建数据文件（关键！）
{T3}bash
cd /root/apps/smart-restaurant-ai-waiter
mkdir -p data logs vector_store
for f in rag_logs.json members.json orders.json message.json events.json points_log.json; do
  if [ ! -f "data/$f" ]; then
    echo '[]' > "data/$f"
    echo "[CREATE] data/$f"
  else
    echo "[EXIST]  data/$f"
  fi
done
{T3}

### 3.3 配置环境变量
docker-compose.yml 的 environment 段：
{T3}yaml
environment:
  - OLLAMA_HOST=http://127.0.0.1:11434
  - SKIP_WARMUP=1
  - WARMUP_EMBED=0
  - FLASK_ENV=production
{T3}

### 3.4 构建镜像
{T3}bash
docker compose build
{T3}
首次 5-15 分钟。

### 3.5 启动容器
{T3}bash
docker compose up -d
sleep 5
docker compose ps
curl -I http://127.0.0.1:5000/
{T3}

## 四、配置后台

### 4.1 初始化管理员
{T3}bash
docker exec tsx-app python scripts/init_admin.py
{T3}
默认：admin / admin888

### 4.2 放行防火墙
阿里云控制台 → 服务器 → 防火墙 → 添加规则：

| 应用类型 | 协议 | 端口 | 授权对象 |
|---|---|---|---|
| 自定义 | TCP | 5000/5000 | 0.0.0.0/0 |

### 4.3 浏览器访问
http://你的服务器IP:5000/

### 4.4 配置远程 LLM
云端跑不动本地 Ollama，必须走远程 API。

1. 登录 http://你的IP:5000/admin/login
2. 进入 设置 → AI 大模型
3. 填：

| 字段 | 值 |
|---|---|
| 使用方式 | 远程 API |
| API Base URL | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| API Key | 你的 DashScope key（sk-...）|
| 模型名 | qwen3.7-plus |

获取 key：https://bailian.console.aliyun.com/ → API-KEY 管理 → 创建

### 4.5 改默认密码
{T3}bash
docker exec tsx-app python -c "from services.admin_service import admin_service; admin_service.create_admin('yourname', 'your-strong-password', 'owner'); print('新管理员已创建')"
{T3}

## 五、常见问题

### Q1. FileNotFoundError: rag_logs.json.tmp
Gunicorn 多 worker 竞争。解决：
{T3}bash
cd /root/apps/smart-restaurant-ai-waiter
for f in rag_logs.json members.json orders.json message.json events.json points_log.json; do
  [ ! -f "data/$f" ] && echo '[]' > "data/$f"
done
docker compose restart
{T3}

### Q2. HTTPConnectionPool 127.0.0.1:11434 Connection refused
云端没 Ollama。解决：切远程 API（见 4.4）。

### Q3. pip install 卡住
Dockerfile 里 pip 加阿里云源：
{T3}dockerfile
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
{T3}

### Q4. exclude-patterns 错误
.dockerignore 含中文。改成纯 ASCII：

{T3}
venv312/
__pycache__/
*.pyc
.pytest_cache/
.git/
.gitignore
logs/
vector_store/
*.pptx
*.docx
*.mp4
{T3}

### Q5. 外网访问不通
1. docker compose ps 容器 Up 吗
2. curl http://127.0.0.1:5000/ 本机通吗
3. 阿里云防火墙放行 5000
4. 阿里云安全组也放行

### Q6. git clone 慢
用 gh-proxy 加速：
{T3}bash
git clone https://gh-proxy.com/https://github.com/用户名/仓库名.git
{T3}

### Q7. 内存不足
加 swap：
{T3}bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
{T3}

## 六、更新部署

{T3}bash
cd /root/apps/smart-restaurant-ai-waiter
git pull
docker compose restart          # 只改了 Python/模板
# 或
docker compose up -d --build    # 改了依赖
{T3}

## 七、下一步（可选）
- Nginx + HTTPS（域名备案后）
- CI/CD 自动部署（GitHub Actions → SSH）
- frp 反代 Ollama
