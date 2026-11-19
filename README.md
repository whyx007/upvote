# 星灿点赞积分系统（十一初）

私域部署的师生点赞积分系统：老师用 Pad 一键点赞学生/学习小组 → 按学期累计**星灿币** → 管理员确认兑换奖励。

- **私域**：强制登录、无公开注册、数据完全自持（校内服务器或自有云服务器）
- **轻量**：Python FastAPI + SQLite 单文件数据库，Docker 一键部署，备份 = 拷文件
- **移动端优先**：Vue3 + Vant 的 PWA，Pad 浏览器"添加到主屏幕"后全屏运行，体验接近 APP
- 与飞书/微信无依赖（学校不用飞书，已确认）

## 功能

| 角色 | 功能 |
|---|---|
| 校长/主任（admin） | **班级工作区**、**学生名册/班级主数据**（按 28/20/12 批量建班、空班指派教师、改名、导出）、教师按学科→年级分组管理、任教关系维护、Excel 名单导入/清除、学期管理、奖励目录、兑换确认/取消、全校统计与 Excel 导出、教师使用统计（周/月） |
| 学科组长（subject_lead） | 普通教师功能 + 查看**同学科教师**的点赞汇总与明细（点赞数、使用天数、最近点赞时间、学生明细），可导出；可查看本人任教班小组；**不管理小组**（除非同时兼任班主任/副班主任）；不能看其他学科或全校管理数据 |
| 班主任 | 普通教师功能 + 管理本班学生、小组、任课教师及班级角色；可看本班总点赞和每个学生的总点赞，但看不到其他老师的个人点赞数 |
| 副班主任 | 普通教师功能 + 管理本班学生和小组；可看本班总点赞和每个学生的总点赞，但看不到其他老师的个人点赞数；不能调整任课教师 |
| 任课教师 | 仅本人任教班级花名册一键点赞、减少最近一次当日点赞、小组一键全员点赞、当日撤销；只能看本人点赞数和本人点赞记录 |

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

管理台 → 名单导入 → 下载模板。支持两种方式，均可多次增量导入：

- **一张表**：一个「学生」sheet（含 `班级` 列）+ 一个「教师」sheet（含 `学科` 列）；
- **按班/按学科拆表**：学生每班一个 sheet（sheet 名=班级，如 `七年级一班`），教师每学科一个 sheet（sheet 名=学科，如 `语文`），可一个文件或分文件上传；
- **一个班一个文件**：文件名必须=班级名（如 `七年级一班.xlsx`），管理台支持鼠标多选文件批量上传；也可每个学科一个文件。

| 工作表 | 列 | 幂等键 |
|---|---|---|
| 学生 | 学号、姓名*、班级*（如 七年级一班）、级（入学年份）、性别（男/女） | 学号；未填学号时按姓名+班级+级 |
| 教师 | 工号、姓名*、学科、手机号、初始密码（默认 123456）、角色（任课教师/学科组长/校长主任） | 工号；未填工号时按手机号或姓名+学科 |

**年级不再单独填写，合并到班级**（如“七年级一班”）。小组、任教关系不在 Excel 输入，导入后到网页设置。重复导入只更新不重复；学生缺学号自动生成 `S...`，教师缺工号从 `T001` 起自动生成；错误逐行报告不影响其他行。

管理台「名单导入」页提供：**下载 Excel 名单模板**（含“说明”工作表，逐列标注是否必填/示例/规则）、**一键导入 Excel 名单**、**一键清除名单**（需当前管理员密码 + 输入“清除名单”确认）。清除范围：学生、小组、班级、任教关系、非管理员教师、点赞/兑换记录、导入历史；保留学期、奖励目录和管理员账号。完整字段说明见 [Excel 名单导入格式](docs/excel-import.md)，模板文件见 [名单导入模板.xlsx](docs/名单导入模板.xlsx)。

当前演示库的全量名单：[全量学生名单_按班级.xlsx](docs/全量学生名单_按班级.xlsx)、[全量教师名单_按学科.xlsx](docs/全量教师名单_按学科.xlsx)、[全量名单_按班级和学科.xlsx](docs/全量名单_按班级和学科.xlsx)、[按班拆分_60个Excel.zip](docs/按班拆分_60个Excel.zip)、[按学科拆分_13个Excel.zip](docs/按学科拆分_13个Excel.zip)。

## 使用流程

1. 校长/主任：在「名册 → 班级管理」按 七年级 28 个班、八年级 20 个班、九年级 12 个班批量建班（空班可先指派教师）；导入学生/教师名单；在网页设置小组与任教关系；创建并激活学期
2. 教师：登录（工号/手机号+密码）→ 选班级 → 点 👍（学生/小组）；点错当日可撤销；只能看到本人任教班和本人点赞数；班主任/副班主任额外看到本班总点赞和每个学生的总点赞，但看不到其他老师的个人点赞数
3. 学科组长：教师端「使用统计」查看本科目教师的点赞汇总/明细，按本周/本月/自定义导出
4. 校长/主任：管理台「统计」看全校概览，「使用统计」看全校教师周/月使用情况并导出
5. 兑换：管理员在"兑换"页选学生+奖励，当场确认扣分；可取消退还
6. 学期切换：管理台激活新学期，学期余额重新累计，总累计保留

## 班级 / 名册 / 使用统计

- **班级主数据**：可先建 60 个班再导入学生；学生导入时按班级名自动归班并补齐班级记录；班级改名会同步学生、小组、任教关系
- **级（入学年份）**：学生名册按“级”记录，如 2026 级；显示为 `2026级`，旧数据仍兼容“入学年份/届”表头
- **名册权限**：学生名册总表仅校长/主任可看；班主任/副班主任只能看本班花名册；任课教师只能看本人任教班
- **小组管理**：支持单个新增、批量新增（输入数量，按已有“第一组/第2组”等序号自动续号，没有编号组时从第一组开始）、随机补组（只把尚未分组的学生随机补进空小组，已有成员不动）；添加成员时一行 5 人勾选，已在其他小组的学生会二次确认后允许跨组；仅班主任/副班主任/管理员可操作
- **数据管理**（校长/主任）：下载完整 `.db` 备份、上传 `.db` 恢复、恢复出厂设置（保留当前管理员）、导出人员名单 + 每名学生本学期有效点赞总数 Excel；工作日 23:30 自动备份，保留最近 5 份；恢复/清空前自动做安全备份
- **点赞可见性**：普通任课教师只能看到自己的本学期累计点赞数；本班班主任/副班主任额外可见“班级本学期累计总点赞”和“每个学生被所有老师点赞的本学期累计数”，但系统不提供按老师拆分的明细；学科组长在“使用统计”看同学科教师的汇总和逐条明细；校长/主任看全部教师。学生官方星灿币余额（含兑换扣减）仅校长/主任和兑换流程使用
- **使用统计口径**：按**点赞发生时间**统计，不是登录/在线时长；指标含点赞数、使用天数、覆盖学生数、首次/最近点赞时间

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
cd backend && pytest              # 149 个单元/接口测试
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
- [ ] 检查教师任教关系：教师只能看到/点赞本人任教班；学科组长只能看本科目
- [ ] `.env` 设置随机 `UPVOTE_SECRET_KEY`
- [ ] 启用 HTTPS（域名）或限制校园网访问
- [ ] 配置每日备份
- [ ] 学生信息仅保留必要字段（姓名/学号/班级），不收集手机号/身份证