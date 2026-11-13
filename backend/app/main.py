from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine.url import make_url

from .config import Settings
from .db import Base, ensure_schema, make_engine, make_session_factory
from .routers import (
    auth,
    classes,
    groups,
    imports,
    likes,
    redemptions,
    rewards,
    semesters,
    stats,
    students,
    teachers,
)
from .seed import seed_admin


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database:
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        ensure_schema(engine)
        with make_session_factory(engine)() as session:
            seed_admin(session, settings)
        yield
        engine.dispose()

    app = FastAPI(title="星灿点赞积分系统", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.login_failures = {}

    app.include_router(auth.router)
    app.include_router(imports.router)
    app.include_router(students.router)
    app.include_router(groups.router)
    app.include_router(teachers.router)
    app.include_router(semesters.router)
    app.include_router(likes.router)
    app.include_router(classes.router)
    app.include_router(rewards.router)
    app.include_router(redemptions.router)
    app.include_router(stats.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # 前端构建产物（存在时托管，开发模式下由 Vite 代理）
    dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    return app