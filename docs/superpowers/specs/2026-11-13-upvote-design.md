# 十一初点赞积分系统（星灿币）— 简要设计

日期：2026-11-13 ｜ 状态：已获用户批准（"简要设计即可，主要要代码实现"）

## 1. 需求（来源：飞书纪要 + 会议文字记录，2026-11-13 沟通会）

1. 基础信息管理：全校师生信息，支持导入现有**零散、非全覆盖**的专项师生数据（增量幂等）。
2. 便捷点赞：老师上课时用 **Pad** 对**学生个人 / 学习小组**一键点赞；**无评价维度**（已简化，只有点赞一个动作）。
3. 积分兑换：点赞**按学期累计**（就读期间可跨学期累计），对应学校**星灿币**，可兑换奖励。
4. 基础属性：**私域**（师生信息不泄露，排除公开网站形式）、**长期日常使用**、不加复杂扩展功能。

## 2. 关键决策记录

| 决策 | 结论 | 理由 |
|---|---|---|
| 系统载体 | 独立私域 Web 应用（PWA，添加到主屏幕） | 学校不用飞书，飞书自建应用无法让校外教师登录；微信小程序需企业认证+审核，留作二期 |
| 与飞书关系 | **产品与飞书完全无关**（用户明确） | 飞书应用"捕光"仅用于内部读取需求文档 |
| 技术栈 | 前端 Vue3+Vant4；后端 **Python** FastAPI+SQLAlchemy+SQLite | 用户指定前端+Python；学校规模（≤3000 学生）SQLite 足够，备份=拷文件 |
| 学生账号 | 学生不建账号、不登录 | 未成年人数据最小化（仅姓名/学号/年级/班级/小组） |
| 点赞语义 | 1 赞 = 1 星灿币；小组赞 = 当时每个成员各 +1（快照，整批可撤销） | 账本始终在学生个人粒度，成员变动不影响历史 |
| 撤销 | 教师可撤销**本人当日**点赞（软删除，整批） | 容错且可审计 |
| 兑换 | 管理员选学生+奖励，当场确认扣分；可取消退还 | MVP 不做学生自助申请/商城物流 |

## 3. 架构

```
Pad/手机浏览器（PWA）
 └─ Vue3 + Vant4 + Pinia + vue-router（教师端/管理端同一应用，按角色显示）
     │ HTTPS + JWT（7 天）
 └─ FastAPI（Python 3.12）+ SQLAlchemy 2.0
     └─ SQLite（data/upvote.db，每日备份）
 └─ 部署：Docker（uvicorn，前端构建产物由 FastAPI 托管）+ Caddy 自动 HTTPS
     └─ 学校校内服务器 或 我方云服务器（数据自持）
```

## 4. 角色与功能

- **管理员**（如郑老师）：Excel 导入（学生/教师/小组/任教，4 sheet 可任意子集）、师生与小组管理、教师账号创建/重置、学期管理、奖励目录、兑换确认/取消、统计与 Excel 导出。
- **教师**：登录 → 任教班级 → 学生大按钮网格一键点赞 / 小组一键点赞 / 当日撤销；查看余额与班级排行。
- 初始管理员：`admin / admin123`（首次启动自动创建，文档提示立即改密）。

## 5. 数据模型

`teachers`(工号唯一/姓名/手机/密码哈希/角色) · `students`(学号唯一/姓名/年级/班级/入学年份) · `groups`(名称+班级唯一) · `group_members` · `teacher_classes`(任教) · `semesters`(名称/起止/是否当前) · `likes`(batch_id/教师/学生/来源小组/学期/撤销时间) · `rewards`(名称/币价/可选库存) · `redemptions`(学生/奖励/币价快照/学期/操作人/取消时间) · `import_batches`(留痕)

余额 = 学期内有效点赞数 × 1 − 学期内未取消兑换币价；另有就读期间累计视图。

## 6. API 契约（前缀 /api，JWT Bearer）

- 认证：`POST /auth/login` `GET /auth/me` `POST /auth/change-password`
- 师生小组（管理端写）：`GET/POST /teachers` `PATCH/DELETE /teachers/{id}`；`GET/POST /students` `PATCH/DELETE /students/{id}`；`GET /classes`；`GET/POST /groups` `PATCH/DELETE /groups/{id}`；`GET /my/classes`
- 学期：`GET /semesters` `POST /semesters` `POST /semesters/{id}/activate` `GET /semesters/current`
- 点赞：`POST /likes {target_type: student|group, target_id}` → batch_id+新余额；`POST /likes/revoke {batch_id}`；`GET /likes/recent`；`GET /classes/{name}/roster`
- 兑换：`GET/POST /rewards` `PATCH/DELETE /rewards/{id}`；`POST /redemptions {student_id,reward_id}`（余额/库存校验）；`GET /redemptions`；`POST /redemptions/{id}/cancel`
- 导入：`POST /imports`(multipart) → 逐行错误报告；`GET /imports/template`(xlsx)；`GET /imports`
- 统计：`GET /stats/overview`；`GET /stats/export`(xlsx)

## 7. 私域与安全

强制登录、无公开注册、bcrypt、JWT 7 天、登录限流、全站 HTTPS（Caddy）、可选 IP 白名单（校园网）、审计留痕（点赞/兑换/导入批次）、每日备份 SQLite、学生 PII 最小化。

## 8. 里程碑（1 人 + AI 辅助）

M1 脚手架+认证+导入（D1–2）→ M2 点赞/积分+教师端，MVP 可演示（D3–5）→ M3 管理端+兑换+统计（D6–9）→ M4 部署+试点（D10–12）。总计约 2 周。

## 9. 待确认假设

① 部署位置（学校服务器有无）；② 登录=工号+密码（不做短信）；③ 兑换=管理员当场确认；④ 小组赞=成员各+1。