# 云服务器部署指南

> 从零开始，把项目部署到阿里云轻量服务器。预计 30 分钟完成。
>
> 本指南按**线上真实环境**（`tsx.accggcc.online`）核对过：容器端口绑 `127.0.0.1`，外网一律走 Nginx 反代，**不需要也不应该对公网开放 5000**。

## 一、前置准备

### 1.1 服务器要求
- CPU: 2 核 / 内存: 2GB+ / 硬盘: 40GB
- 系统: Alibaba Cloud Linux / Ubuntu 20.04+ / CentOS 7+
- 建议阿里云轻量应用服务器（学生价 ~60 元/年）

### 1.2 域名（可选，上 HTTPS 才需要）
阿里云注册域名 + 免费备案（7-20 天）

### 1.3 本地准备
```bash
git add -A
git commit -m "ready to deploy"
git push origin main
```

### 1.4 重置服务器密码
阿里云控制台 → 找到服务器 → 更多 → 重置密码 → 重启

## 二、服务器初始化

### 2.1 SSH 连接
```bash
ssh root@你的服务器公网IP
```
首次连接输 yes 确认指纹，再输密码。

如果报 Permission denied (publickey)：
```bash
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no root@你的IP
```

### 2.2 装 Docker（如未预装）
```bash
docker version
```
未装则：
```bash
# Alibaba Cloud Linux / CentOS / RHEL
dnf install -y dnf-utils git

# Ubuntu / Debian
apt update && apt install -y git curl
curl -fsSL https://get.docker.com | sh

systemctl enable --now docker
```

### 2.3 配 Docker 镜像加速
```bash
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
```

### 2.4 装 Docker Compose
```bash
dnf install -y docker-compose-plugin
```
装不上则用二进制：
```bash
curl -SL "https://gh-proxy.com/https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
mkdir -p /usr/local/lib/docker/cli-plugins
ln -sf /usr/local/bin/docker-compose /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version
```

## 三、部署应用

### 3.1 拉代码
```bash
mkdir -p /root/apps && cd /root/apps
git clone https://github.com/acc12138-x/smart-restaurant-ai-waiter.git
cd smart-restaurant-ai-waiter
```

私有仓库用：
```bash
git clone https://用户名:token@github.com/用户名/仓库名.git
```

> 若 clone 慢/超时，可临时套一层 gh-proxy 下载：`https://gh-proxy.com/https://github.com/...`。
> 但**clone 完成后建议把 origin 换回官方地址**，否则以后 `git pull` 都要经过代理，容易卡：
> ```bash
> git remote set-url origin https://github.com/acc12138-x/smart-restaurant-ai-waiter.git
> ```

### 3.2 预创建数据文件（关键！）
`data/` 下的这几个 json **不在仓库里**（被 `.gitignore` 排除），但 Gunicorn 多 worker 同时首次写入会竞争报错，所以必须先建好空文件：

```bash
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
```

⚠️ **必须在部署目录里执行**。换个目录跑这段，会在别处造出一堆 3 字节的空文件，而应用读的还是 `data/`——线上曾经因此留下过 `/home/admin/data/` 这样的空壳目录。

菜单数据 `data/menu.json` 是仓库里的文件，clone 下来就有，不用手工建。

### 3.3 配置环境变量
`docker-compose.yml` 的 `environment` 段：
```yaml
environment:
  - OLLAMA_HOST=http://127.0.0.1:11434
  - SKIP_WARMUP=1
  - WARMUP_EMBED=0
  - FLASK_ENV=production
```

- `SKIP_WARMUP=1` **必须有**：云端没装 Ollama，不跳过预热会在启动时反复连不上、拖慢甚至卡住启动
- `OLLAMA_HOST` 在容器里指向的是**容器自己**，不是宿主机；只要后台切了远程 API 就没有实际影响，留着无害

另外确认 compose 里有 `restart: unless-stopped`，否则服务器一重启站点就 502。

### 3.4 构建镜像
```bash
docker compose build
```
首次 5-15 分钟。**注意**：compose 已经把源码目录挂载进容器（`./routes:/app/routes` 等 14 处），所以日常改代码**不需要重新 build**，只有改了 `requirements.txt` / `Dockerfile` / `docker-compose.yml` 才需要。

### 3.5 启动容器
```bash
docker compose up -d
sleep 5
docker compose ps
curl -I http://127.0.0.1:5000/
```
容器名固定为 `tsx-app`（compose 里的 `container_name`），端口为 `127.0.0.1:5000->5000/tcp`。

## 四、配置后台

### 4.1 初始化管理员
```bash
docker exec tsx-app python scripts/init_admin.py
```
默认：admin / admin888

### 4.2 对外访问必须走 Nginx（不要开放 5000）

容器只绑 `127.0.0.1:5000`，所以**公网直连 `IP:5000` 一定不通**，这是刻意的：证书、压缩、SSE 都交给 Nginx。

```bash
cat > /etc/nginx/conf.d/tsx.conf << 'EOF'
server {
    listen 80;
    server_name tsx.你的域名;
    location /.well-known/acme-challenge/ {
        root /opt/apps/after-sales/frontend/dist;   # 证书续期校验的 webroot
    }
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name tsx.你的域名;

    ssl_certificate     /etc/letsencrypt/live/tsx.你的域名/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tsx.你的域名/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # AI 回复是流式输出（打字机效果），必须关缓冲，否则会攒完一次性吐出
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
EOF
nginx -t && systemctl reload nginx
```

防火墙/安全组只需放行 **80 和 443**（外加 22 供 SSH）。申请证书：

```bash
certbot certonly --webroot -w /opt/apps/after-sales/frontend/dist -d tsx.你的域名
```

> 证书续期若依赖 `certbot/certbot` 这类 Docker 镜像，注意 `docker image prune -a` 会把它删掉，续期前需要重新 `docker pull`。

### 4.3 浏览器访问
https://tsx.你的域名/

仅本机调试时才用 `http://127.0.0.1:5000/`（在服务器上执行）。

### 4.4 配置远程 LLM
云端跑不动本地 Ollama，必须走远程 API。

1. 登录 `https://tsx.你的域名/admin/login`
2. 进入 设置 → AI 大模型
3. 填：

| 字段 | 值 |
|---|---|
| 使用方式 | 远程 API |
| API Base URL | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| API Key | 你的 DashScope key（sk-...）|
| 模型名 | qwen3.7-plus |

获取 key：https://bailian.console.aliyun.com/ → API-KEY 管理 → 创建

验证 AI 链路真的通（会消耗一次远程调用）：
```bash
curl -s -X POST http://127.0.0.1:5000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"你们几点关门","table_no":"05"}' | python3 -m json.tool
```
预期返回 `intent: "query_hours"` 和一句营业时间。

### 4.5 改默认密码
```bash
docker exec tsx-app python -c "from services.admin_service import admin_service; admin_service.create_admin('yourname', 'your-strong-password', 'owner'); print('新管理员已创建')"
```

## 五、常见问题

### Q1. FileNotFoundError: rag_logs.json.tmp
Gunicorn 多 worker 竞争。解决：
```bash
cd /root/apps/smart-restaurant-ai-waiter
for f in rag_logs.json members.json orders.json message.json events.json points_log.json; do
  [ ! -f "data/$f" ] && echo '[]' > "data/$f"
done
docker compose restart
```

### Q2. HTTPConnectionPool 127.0.0.1:11434 Connection refused
云端没 Ollama。解决：切远程 API（见 4.4）。

顺带说明：`/health` 接口**只探测本地 Ollama**，完全不看后台设置里的"使用方式"。所以云端它会一直返回：

```json
{ "status": "degraded", "checks": { "flask": true, "vector_store": true, "ollama": false } }
```

**HTTP 503 是预期行为，不代表站点故障**——只要 `flask` 和 `vector_store` 是 `true`，服务就是健康的。目前 Dockerfile 没有 `HEALTHCHECK`、Nginx 也没引用它，所以没有自动化依赖这个状态；但**如果你以后接 uptime 监控，别拿 `/health` 当探针**。

### Q3. pip install 卡住
Dockerfile 里 pip 加阿里云源：
```dockerfile
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### Q4. exclude-patterns 错误
`.dockerignore` 含中文。改成纯 ASCII：

```
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
```

### Q5. 外网访问不通
1. `docker compose ps` 容器 Up 吗（容器名 `tsx-app`）
2. `curl http://127.0.0.1:5000/` 本机通吗
3. `nginx -t` 通过吗，`systemctl status nginx` 正常吗
4. **别再想着放行 5000**：容器绑的是 `127.0.0.1`。只放行 80/443
5. 域名解析到这台服务器的公网 IP 了吗（`dig +short tsx.你的域名`）

### Q6. git clone 慢
用 gh-proxy 加速：
```bash
git clone https://gh-proxy.com/https://github.com/用户名/仓库名.git
```

### Q7. 内存不足
加 swap：
```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 六、更新部署

**关键前提**：compose 把源码目录挂载进了容器（`./routes:/app/routes` 等），容器读的就是宿主机这份代码。所以改代码**不需要重新 build 镜像**，`restart` 即可生效。

```bash
D=/root/apps/smart-restaurant-ai-waiter

# 1) 先看有没有本地改动（服务器上直接改过文件会产生冲突）
git -C $D status --short

# 2) 拉取
git -C $D pull
git -C $D log --oneline -3

# 3) 重启进程（源码是挂载的，不用 --build）
docker compose -f $D/docker-compose.yml restart

# 4) 验证
docker compose -f $D/docker-compose.yml ps
docker compose -f $D/docker-compose.yml logs --tail=60
curl -I -m 5 http://127.0.0.1:5000/
curl -I -m 8 https://tsx.你的域名/
```

用 `-f $D/docker-compose.yml` 而不是先 `cd` 的好处：compose 会把**配置文件所在目录**当作工程目录，`./data`、`./vector_store` 这些相对挂载会正确解析，不会跑到 `/root` 下新建一套空数据。

**什么时候才需要重建**：

```bash
docker compose -f $D/docker-compose.yml up -d --build   # 只在改了 requirements.txt / Dockerfile / docker-compose.yml 时
```

**回退**：

```bash
git -C $D log --oneline -5
git -C $D reset --hard <上一个正常版本>
docker compose -f $D/docker-compose.yml restart
```

**只改了文档（README / DEPLOY.md / .gitignore / docs/）**：`git pull` 就够了，连 `restart` 都不用——这些路径不在运行时代码路径上。

`git pull` 不会碰业务数据：`data/app.db`、`data/*.json` 都在 `.gitignore` 里。

## 七、生产环境现状速查

以 `tsx.accggcc.online` 这台为例，排查时按这张表定位：

| 项 | 实际值 |
|---|---|
| 域名 / 入口 | `tsx.accggcc.online` → Nginx `/etc/nginx/conf.d/tsx.conf` → `127.0.0.1:5000` |
| 代码目录 | `/root/apps/smart-restaurant-ai-waiter`（root 所有，普通用户需 `sudo`） |
| 仓库 | `github.com/acc12138-x/smart-restaurant-ai-waiter`（官方地址，非代理） |
| 容器 / 镜像 | `tsx-app` / `smart-restaurant-ai-waiter-app` |
| 端口 | `127.0.0.1:5000->5000/tcp`（仅本机） |
| 数据 | `$D/data/`（`app.db` + `menu.json` + 各 json） |
| 重启策略 | `restart: unless-stopped` |
| LLM | 云端无 Ollama，走远程 API（阿里云百炼） |

排查命令：

```bash
docker ps -a                                  # 含已停止的容器；只看在跑的容易漏
docker inspect tsx-app --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'
docker inspect tsx-app --format '重启策略: {{.HostConfig.RestartPolicy.Name}}'
docker compose ls -a                          # 服务器上所有 compose 工程
ss -tlnp                                      # 端口占用（非 root 看不到他人进程名，加 sudo）
```

> 注意：`admin` 用户读不了 `/root`，全局搜代码时要加 `sudo`，否则会误判"代码不在这台机器上"。

## 八、下一步（可选）
- CI/CD 自动部署（GitHub Actions → SSH）：目前 CI 只跑 pytest，部署仍需手动 pull
- frp 反代本机 Ollama（省 API 费）：注意 `frps` 的 `allowPorts` 需覆盖目标端口，且不能让 frp 顶掉 Nginx 的反代链路
