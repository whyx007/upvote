# 星灿点赞积分系统（十一初）

私域部署的师生点赞积分系统：老师用 Pad 一键点赞学生/学习小组 → 按学期累计**星灿币** → 管理员确认兑换奖励。

- **私域**：强制登录、无公开注册、数据完全自持（校内服务器或自有云服务器）
- **轻量**：Python FastAPI + SQLite 单文件数据库，Docker 一键部署，备份 = 拷文件
- **移动端优先**：Vue3 + Vant 的 PWA，Pad 浏览器"添加到主屏幕"后全屏运行，体验接近 APP
- 与飞书/微信无依赖（学校不用飞书，已确认）

## 功能

| 角色 | 功能 |
|---|---|
| 管理员 | **班级工作区**（左侧班级导航，班内学生/小组/任课教师三页签，小组成员勾选器、快速增删改）、班主任/副班主任任命、教师按学科→年级分组管理、Excel 导入师生/小组/任教（零散增量、幂等去重、逐行报错）、学期管理、奖励目录、兑换确认/取消、统计与 Excel 导出 |
| 班主任 | 普通教师功能 + 管理本班学生、小组、任课教师及班级角色；不能管理其他班级或全校设置 |
| 副班主任 | 普通教师功能 + 管理本班学生和小组；不能调整任课教师 |
| 教师 | 任教班级花名册一键点赞、减少最近一次当日点赞、小组一键全员点赞、当日撤销、余额与排行 |

关键语义：**1 赞 = 1 星灿币**；小组赞 = 当时每个成员各 +1（快照，整批可撤销）；余额按学期统计，就读期间累计保留；学生不建账号（未成年人数据最小化）。

## 快速开始（开发）

```bash
# 后端（Python 3.12+）
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt   # Windows；Linux 用 .venv/bin/pip
cd backend
../.venv/Scripts/python -m uvicorn app.main:create_app --factory --port 8000

# 前端（Node 20+，pnpm）
cd frontend
pnpm install
pnpm dev        # http://localhost:5173，/api 自动代理到 8000
```

首次启动自动创建管理员：**admin / admin123（请立即修改）**。
也可以 `pnpm build` 后直接访问 8000 端口（FastAPI 托管前端构建产物）。

Windows 一键启动（自动生成并持久化随机密钥到 `.env`，监听 0.0.0.0:8000，局域网 Pad 可直接访问）：

```powershell
pwsh -File scripts\serve.ps1
```

## 生产部署（Docker）

### 方式一：单机 docker compose（自带 Caddy 自动 HTTPS）

```bash
cp .env.example .env    # 设置 UPVOTE_SECRET_KEY（随机 64 位 hex）
docker compose up -d --build
```

- 设置 `.env` 中 `DOMAIN=你的域名` → Caddy 自动申请 HTTPS 证书
- 校内部署可不设域名（监听 :80），建议配合校园网/IP 白名单
- 数据持久化在 `./data/upvote.db`

### 方式二：已有 Caddy/反代的 VPS（只跑应用容器）

```bash
# 宿主机需已安装 docker + compose；端口 9100 需在云安全组放行
cp .env.example .env    # 写入 UPVOTE_SECRET_KEY
docker compose -f docker-compose.vps.yml up -d --build
```

`docker-compose.vps.yml` 只启动应用容器（`9100 -> 8000`），不占 80/443，适合已有 Caddy/Nginx 的服务器；
数据在 `./data/upvote.db`，容器带健康检查与 `restart: unless-stopped`。

从本机一条命令推送并重建（git bundle 传输，不依赖 GitHub 可达）：

```bash
DSH_SSH_PASSWORD=... python scripts/deploy_vps.py            # 完整部署/更新
DSH_SSH_PASSWORD=... python scripts/deploy_vps.py --dry      # 只探测远端环境
```

**已上线实例**：`http://43.133.86.206:9100`（腾讯云 Ubuntu 22.04，容器 `upvote`，
代码在 `/opt/upvote`，数据 `/opt/upvote/data/upvote.db`；9000 端口为同机另一个项目，80/443 由系统 Caddy 占用）。

### 每日备份

```bash
python scripts/backup.py            # 在线安全备份到 data/backups/，保留最近 30 份
```

建议加入计划任务（Linux cron / Windows 任务计划程序）每日执行。

## 数据导入

管理台 → 导入 → 下载模板。一个 Excel 含 4 个工作表（可任意子集、可多次增量导入）：

| 工作表 | 列 | 幂等键 |
|---|---|---|
| 学生 | 学号*、姓名*、年级、班级*、入学年份、性别（男/女） | 学号 |
| 教师 | 工号*、姓名*、手机号、初始密码（默认 123456）、角色、学科 | 工号 |
| 小组 | 小组名称*、班级*、成员学号（逗号分隔） | 名称+班级 |
| 任教 | 工号*、班级*、角色（任课教师/班主任/副班主任，留空则保留原角色） | 工号+班级 |

重复导入只更新不重复；同一工作簿内小组可引用本簿学生、任教可引用本簿教师；错误逐行报告不影响其他行。

## 使用流程

1. 管理员：创建并激活学期 → 导入师生/小组/任教 → 维护奖励目录
2. 教师：登录（工号+密码）→ 选班级 → 点 👍（学生/小组）；点错当日可撤销
3. 兑换：管理员在"兑换"页选学生+奖励，当场确认扣分；可取消退还
4. 学期切换：管理台激活新学期，学期余额重新累计，总累计保留

## 安卓 APK（星灿点赞）

教师 Pad 可以直接装 APK，不用每次打开浏览器。前端资源随包内置，API 仍指向 VPS 后端。

```powershell
# 首次：安装 Android 命令行工具链（约 300MB，落在 tools\android-sdk）
powershell -ExecutionPolicy Bypass -File scripts\install_android_sdk.ps1

# 出包
powershell -ExecutionPolicy Bypass -File scripts\build_apk.ps1 -VersionName 1.0.0 -VersionCode 1
# 产物：android\build\upvote-1.0.0.apk
```

- 后端地址在 `android/app/src/main/java/site/whyx/upvote/Config.java` 的 `API_ORIGIN`
- 架构、构建细节与已知限制见 [docs/android-apk.md](docs/android-apk.md)
- 只需后端更新时不必重新出包，照旧执行 `scripts/deploy_vps.py`

## 测试

```bash
cd backend && pytest              # 108 个单元/接口测试
python scripts/smoke.py           # 24 项端到端冒烟（需全新数据库的运行中服务）
```

## 项目结构

```
backend/app/          FastAPI：routers/ 接口、services/ 导入与积分、models.py、security.py
backend/tests/        pytest（TDD）
frontend/src/         Vue3 + Vant：views/TeacherHome 教师端、views/admin/* 管理端
scripts/              gen_icons.py 图标、backup.py 备份、smoke.py 冒烟
docs/superpowers/specs/  设计文档
Dockerfile / docker-compose.yml / Caddyfile   部署
```

## 安全清单（上线前）

- [ ] 修改 admin 默认密码；教师首次登录后改密
- [ ] `.env` 设置随机 `UPVOTE_SECRET_KEY`
- [ ] 启用 HTTPS（域名）或限制校园网访问
- [ ] 配置每日备份
- [ ] 学生信息仅保留必要字段（姓名/学号/班级），不收集手机号/身份证