# MAGA 自动部署流程

## 目标

每次推送 `main` 到 GitLab 后，由 10.88.0.16 上的 GitLab Runner 自动部署线上环境。

当前服务器约定：

- SSH：`ssh -i ~/.ssh/id_ed25519 ubuntu@10.88.0.16`
- 项目目录：`/home/ubuntu/maga`
- 环境变量：`/home/ubuntu/maga/.env.prod`
- 前端静态目录：`/var/www/maga-console`
- Compose 命令：`sudo docker compose --env-file .env.prod -f docker-compose.prod.yml ...`

## 部署链路

```text
git push gitlab main
  -> GitLab pipeline
  -> 10.88.0.16 上的 maga-prod Runner 拉取任务
  -> ci/deploy_prod.sh
  -> rsync 代码到 /home/ubuntu/maga，保留 .env.prod
  -> docker compose up -d --build
  -> 构建前端镜像并拷出 dist
  -> rsync dist 到 /var/www/maga-console
  -> health check
```

## 服务器一次性配置

1. 安装 GitLab Runner。

2. 用 `ubuntu` 用户注册 shell runner，并加 tag `maga-prod`。

```bash
gitlab-runner register \
  --url https://ai-gitlab.sharpasshark.com \
  --token '<GitLab 项目 Runner token>' \
  --executor shell \
  --tag-list maga-prod \
  --description maga-prod-10.88.0.16
```

3. 确认 `ubuntu` 可以免密执行 Docker。

```bash
sudo -n docker ps
```

4. 确认线上环境文件存在。

```bash
test -f /home/ubuntu/maga/.env.prod
```

## 手动触发部署

在服务器或 Runner 工作区执行：

```bash
bash ci/deploy_prod.sh
```

## 验证

```bash
curl http://127.0.0.1:5100/api/v1/health/ready
cd /home/ubuntu/maga
sudo docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

## 注意

- `.env.prod` 不进 Git，也不会被部署脚本覆盖。
- 部署脚本使用 `flock` 防止多次 push 造成并发发布。
- 如果前端发布失败，后端容器可能已经更新；重新跑同一个 pipeline 即可幂等修复。
