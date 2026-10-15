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

> ⚠️ **别用 `up -d` 代替 `restart` 来应用代码改动**（踩过）
>
> 容器已经在跑、compose 配置又没变时，`up -d` 只会打印一行 `Container tsx-app Running`，
> **不会重启进程**。挂载的源码文件是新的，但 Python 模块早就加载进内存了，
> 跑的还是旧代码 —— 现象是"代码明明改了、行为一点没变"，非常难查。
>
> - 改**应用代码**（`.py` / 模板 / CSS）：`docker compose -f $D/docker-compose.yml restart`
> - 改过 compose 里的 `environment` / `volumes`：必须 `up -d --force-recreate`（`restart` 不重读环境变量）

**怎么确认进程真的加载了新代码**

```bash
curl -s http://127.0.0.1:5000/health | python3 -m json.tool
```

```json
"code": {
  "commit": "fe43d0a",                          // 当前加载的提交（挂了 .git 才有，否则 unknown）
  "process_started_at": "2026-10-14 21:05:00",  // 进程启动时间
  "newest_source_mtime": "2026-10-14 21:30:12", // 代码文件最后修改时间
  "stale": true,                                // ← true = 代码比进程新，跑的是旧代码
  "hint": "代码比进程新 —— 拉了代码但没重启…"
}
```

`stale: true` → 执行 `restart`，再访问本接口应变成 `false`。这比翻容器日志快得多。

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

## 八、证书续期运维

线上两个站点（`tsx.accggcc.online`、`agent.accggcc.online`）共用一套续期机制。**任何一个环节静默失效，到期日一到两个站点会同时因证书过期而无法访问**，而且中间不会有任何告警。这一节记录实测踩过的坑。

### 8.1 现状

| 项 | 值 |
|---|---|
| 定时任务 | `/etc/cron.d/certbot-renew`，每天 03:20 |
| 执行方式 | `docker run --rm` 跑 `certbot/certbot` 镜像 |
| 校验方式 | webroot（HTTP-01），两个域共用 `/opt/apps/after-sales/frontend/dist` |
| 证书目录 | `/etc/letsencrypt/live/{tsx,agent}.accggcc.online/`，密钥类型 **ECDSA P-256** |
| 续期窗口 | 到期前 30 天自动触发（cron 每天跑，进入窗口才真正续） |
| 错误日志 | `/var/log/certbot-renew.log`（**只在出错时才有内容**） |
| 到期看门狗 | `/etc/cron.d/cert-expiry-watch`，每周一 09:00 记一行到期时间 |

nginx 侧靠 `location /.well-known/acme-challenge/ { root /opt/apps/after-sales/frontend/dist; }` 放行校验，**两个域的 conf 都要有这段**。

### 8.2 坑一：certbot 必须 ≥ 2.0（ECDSA）

线上证书是 **ECDSA P-256**，而 certbot 从 **2.0 才开始支持 ECDSA**。用 1.x 的 certbot 续期，它会把证书**静默换成 RSA**——不报错、不告警，密钥类型就悄悄变了。

镜像里的 certbot 版本要和 `/etc/letsencrypt/renewal/*.conf` 里的 `version` 对齐。先确认当前证书类型：

```bash
for d in tsx.accggcc.online agent.accggcc.online; do
  printf '%-24s ' "$d"
  openssl x509 -in /etc/letsencrypt/live/$d/cert.pem -noout -text | grep -E 'Public Key Algorithm|NIST CURVE'
done
```

出现 `id-ecPublicKey` 就必须用 certbot ≥ 2.0。

### 8.3 坑二：Docker Hub 拉不动 → 本地自建镜像

`docker pull certbot/certbot:latest` 在国内基本拉不动。阿里云 ACR 的加速地址对 `latest` 可能只命中多年前的旧缓存（实测拿到过 **4 年前的 certbot 1.22.0**），而指定版本 tag 又会回落 Docker Hub 超时。

**可靠做法：用本地已有的 Python 镜像自建**（基础镜像在本地、pip 走阿里云源，全程不碰 Docker Hub）：

```bash
mkdir -p /root/certbot-image && cd /root/certbot-image

cat > Dockerfile << 'EOF'
FROM smart-restaurant-ai-waiter-app:latest
RUN pip install --no-cache-dir "certbot==5.8.0" \
    -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
ENTRYPOINT ["certbot"]
EOF

docker build -t certbot/certbot:latest .
docker tag certbot/certbot:latest certbot-local:5.8.0    # 备份标签，防 latest 被覆盖
docker run --rm certbot/certbot --version                # 确认版本
```

`certbot==5.8.0` 这个版本号要和 renewal 配置里的 `version` 一致。打完仍叫 `certbot/certbot:latest`，**cron 一行都不用改**。

镜像被误删时，两种恢复方式：

```bash
docker tag certbot-local:5.8.0 certbot/certbot:latest                  # 从备份标签还原
cd /root/certbot-image && docker build -t certbot/certbot:latest .      # 重新构建
```

⚠️ **不要再对 `certbot/certbot` 执行 `docker pull`**，否则会把自建的新镜像盖成 Hub 上的旧版本。

### 8.4 坑三：`docker image prune -a` 会把它删掉

certbot 镜像**不被任何运行中的容器使用**，正好落在 `docker image prune -a` 的清理范围内——一旦被删，那条 cron 就开始每天静默失败。

**清理只用不带 `-a` 的形式：**

```bash
docker image prune -f        # 只删 dangling 镜像，安全
docker builder prune -f      # 构建缓存，安全
```

### 8.5 坑四：失败完全没有声音

cron 用了 `--quiet`（**只输出错误**），而这台机器**没有 MTA**——失败信息会凭空消失。所以 cron 必须带日志重定向：

```bash
cat > /etc/cron.d/certbot-renew << 'EOF'
20 3 * * * root docker run --rm -v /etc/letsencrypt:/etc/letsencrypt -v /var/lib/letsencrypt:/var/lib/letsencrypt -v /opt/apps/after-sales/frontend/dist:/var/www/html certbot/certbot renew --webroot -w /var/www/html --quiet >> /var/log/certbot-renew.log 2>&1 && systemctl reload nginx
EOF
chmod 644 /etc/cron.d/certbot-renew
```

注意 `/var/log/certbot-renew.log` **是错误日志**：平时空着 = 正常，有内容 = 出事了。**续期成功不会有任何记录**，想确认成功请看证书到期时间或看门狗日志。

### 8.6 到期看门狗

```bash
cat > /etc/cron.d/cert-expiry-watch << 'EOF'
0 9 * * 1 root echo "$(date -Is) tsx:$(echo | openssl s_client -connect tsx.accggcc.online:443 -servername tsx.accggcc.online 2>/dev/null | openssl x509 -noout -enddate) agent:$(echo | openssl s_client -connect agent.accggcc.online:443 -servername agent.accggcc.online 2>/dev/null | openssl x509 -noout -enddate)" >> /var/log/cert-expiry.log
EOF
chmod 644 /etc/cron.d/cert-expiry-watch
```

每周一记一行。**如果到期日期不再往后跳，就说明续期断了**——比等站点报证书错误早发现一个月。手工验证一次：

```bash
echo "$(date -Is) tsx:$(echo | openssl s_client -connect tsx.accggcc.online:443 -servername tsx.accggcc.online 2>/dev/null | openssl x509 -noout -enddate)" >> /var/log/cert-expiry.log
cat /var/log/cert-expiry.log
```

### 8.7 排查与演练

```bash
# ① cron 守护进程活着吗（它死了两个定时任务都不会跑）
systemctl is-active crond

# ② 校验链路自检：写个文件，看公网能否取到（两个域都要通）
mkdir -p /opt/apps/after-sales/frontend/dist/.well-known/acme-challenge
echo selftest-ok > /opt/apps/after-sales/frontend/dist/.well-known/acme-challenge/selftest
curl -s http://tsx.accggcc.online/.well-known/acme-challenge/selftest
curl -s http://agent.accggcc.online/.well-known/acme-challenge/selftest
rm -f /opt/apps/after-sales/frontend/dist/.well-known/acme-challenge/selftest

# ③ 演练续期（staging 环境，不消耗配额）
docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/lib/letsencrypt:/var/lib/letsencrypt \
  -v /var/log/letsencrypt:/var/log/letsencrypt \
  -v /opt/apps/after-sales/frontend/dist:/var/www/html \
  certbot/certbot renew --dry-run --webroot -w /var/www/html --no-random-sleep-on-renew
```

看到 `Congratulations, all simulated renewals succeeded` 即通过。

**四个容易卡住的地方：**

- 手动跑要加 `--no-random-sleep-on-renew`。不加的话 certbot 会随机睡最多 8 分钟（日志里是 `Non-interactive renewal: random delay of 100.4 seconds`），看起来像卡死。**但定时任务里要保留这个延迟**，那是 Let's Encrypt 建议的错峰行为
- `-w` 后面写**容器内路径** `/var/www/html`（它挂载到宿主机 `/opt/apps/after-sales/frontend/dist`），不是宿主机路径
- 报 `Another instance of Certbot is already running` 说明有别的实例（或后台任务）占着锁，等它结束再跑
- **只跑 `--dry-run`，别手动跑正式 `renew`**——Let's Encrypt 有每周 5 次重复签发配额。例外：证书已进入到期前 30 天窗口却还没续上时，那就该立刻手工续一次

### 8.8 `/etc/cron.d` 的格式要求

- 文件**必须以换行符结尾**，否则可能被整个忽略
- 权限 `644`、属主 root；Vixie cron 会**跳过任何人可写的文件**（别 `chmod 666`）
- 行格式是 `分 时 日 月 周 用户 命令`，别漏掉用户字段
- 命令里的 `%` 会被 cron 当作换行，需要时写成 `\%`
- cron 的 `PATH` 只有 `/usr/bin:/bin`；用到非常规路径的工具时写绝对路径

## 九、下一步（可选）
- CI/CD 自动部署（GitHub Actions → SSH）：目前 CI 只跑 pytest，部署仍需手动 pull
- frp 反代本机 Ollama（省 API 费）：注意 `frps` 的 `allowPorts` 需覆盖目标端口，且不能让 frp 顶掉 Nginx 的反代链路
