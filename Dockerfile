# ---- 前端构建 ----
FROM node:24-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/.npmrc frontend/pnpm-workspace.yaml ./
RUN corepack enable && pnpm install
COPY frontend/ ./
RUN pnpm build

# ---- 后端运行 ----
FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY docs/example /app/docs/example
COPY --from=frontend /app/frontend/dist /app/frontend/dist
ENV UPVOTE_DATABASE_URL=sqlite:////app/data/upvote.db
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]