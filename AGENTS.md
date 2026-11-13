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

## 常用命令
- 后端测试：`cd backend; E:\code\upvote\.venv\Scripts\python.exe -m pytest`（75 测试）
- 启动服务：`cd backend; ..\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --port 8000`
- 前端构建：`cd frontend; & '<node>' '<pnpm.mjs>' build`（Node/pnpm 用 DSH 运行时路径，见 load_workspace_dependencies）
- 端到端冒烟：`python scripts/smoke.py`（需全新数据库的运行中服务，24 项）
- 默认账号：admin/admin123；教师导入默认密码 123456