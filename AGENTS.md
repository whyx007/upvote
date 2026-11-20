# AGENTS.md — upvote 项目指引

## 术语：捕光（飞书开放平台应用）
- **"捕光"是用户的飞书开放平台自建应用代号。用户提到"捕光"时，即指接入该飞书应用**：读取 `.feishu/credentials.json` 获取凭证，换取 `tenant_access_token` 后调用所需 API。
- App ID: `cli_a9fbc35a19f95bc6`；租户域名: `zfzn1a687b.feishu.cn`（飞书国内站，API 域名 `open.feishu.cn`）。
- 凭证文件 `.feishu/credentials.json` 已 gitignore，**禁止提交到 git 或外传**。
- 换 token：`POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`，body `{"app_id","app_secret"}`，token 有效期 7200 秒。
- 已验证可用权限：docx 文档读取（`/docx/v1/documents/{id}`、`raw_content`、`blocks`）、drive 素材下载（`/drive/v1/medias/{token}/download`）。其余权限（通讯录、租户信息、消息等）尚未开通，需要时提示用户在开发者后台开通。
- 注意：捕光仅用于内部协作/文档读取。**本项目产品（十一初点赞积分系统）与飞书无关**，是独立私域 Web 应用（用户已明确决策）。

## 项目概况
- 十一初点赞积分系统（星灿币）：教师 Pad 端一键点赞 → 学期累计积分 → 兑换奖励。
- 技术栈：前端 Vue 3 + Vant 4（PWA），后端 Python FastAPI + SQLAlchemy + SQLite。
- 需求来源：飞书纪要 `XPffdEk60o4CPLxvmVActYeinZe` 及文字记录 `Sx30dly9cox81SxB6V2ceFMpnGg`（缓存于 `.feishu/`）。
- 设计文档：`docs/superpowers/specs/2026-11-13-upvote-design.md`。
- 开发约定：后端 pytest TDD；`data/` 存放 SQLite 与备份，不入库。
- 班级权限：`teacher_classes.duty = teacher/head/deputy`；班主任可管本班学生、小组、任课教师，副班主任仅学生/小组，管理员全权；权限校验集中在 `app/services/class_roles.py`。
- 小组管理：仅班主任/副班主任（校长/主任后台全权）可建组/改名/删除/加减成员，支持批量新增和随机补组（只补空组，已有成员不动）；添加成员按一行 5 人勾选，跨组重复加入会二次确认；学科组长等只读查看，兼任班主任/副班主任时按班级职责可管理（`assert_class_group_manager`）。
- 工号规则：教师未填工号时自动生成 `T001`、`T002`…（admin 不占 T 号）。
- 三层数据权限：`teachers.role = teacher/subject_lead/admin`；任课教师只看本人任教班和本人点赞，学科组长可看同学科教师汇总/明细，校长/主任全权；集中校验在 `app/services/access.py`。
- 班级主数据：`classes` 表（年级/班号/级），支持先建空班再导入学生；学生 `enrollment_year` 即“级”（入学年份）。
- 名单格式：学生只填班级（如“七年级一班”，年级已合并），支持一张表、每班一个 sheet、或每班一个文件（文件名=班级，可多选文件批量上传）；教师同理按学科。小组、任教不在 Excel 输入，网页设置。

## 常用命令
- 后端测试：`cd backend; ..\.venv\Scripts\python.exe -m pytest`（152 测试）
- 启动服务：`cd backend; ..\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --port 8000`
- 前端构建：`cd frontend; & '<node>' '<pnpm.mjs>' build`（Node/pnpm 用 DSH 运行时路径，见 load_workspace_dependencies）
- 端到端冒烟：`python scripts/smoke.py`（需全新数据库的运行中服务，24 项）
- 默认账号：admin/admin123；教师导入默认密码 123456

## 安卓 APK
- 架构：APK 内 Vue 前端 + 回环 HTTP 服务（`LocalServer`）转发 `/api/**` 到 VPS，后端零改动。详见 `docs/android-apk.md`。
- 装工具链：`powershell -ExecutionPolicy Bypass -File scripts\install_android_sdk.ps1`（产物 `tools\android-sdk`，已 gitignore）
- 出包：`powershell -ExecutionPolicy Bypass -File scripts\build_apk.ps1 -VersionName 1.0.0 -VersionCode 1`
  产物 `android\build\upvote-<版本>.apk`
- 后端地址常量：`android/app/src/main/java/site/whyx/upvote/Config.java` 的 `API_ORIGIN`
- **.ps1 必须存为 UTF-8 with BOM**，否则 Windows PowerShell 5.1 按 GBK 解析中文会报语法错误
- 签名密钥 `android/keystore/upvote.jks`（gitignore），升级安装必须同一把密钥