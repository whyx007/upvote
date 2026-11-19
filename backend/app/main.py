import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine.url import make_url

from .config import Settings
from .db import Base, ensure_schema, make_engine, make_session_factory
from .routers import (
    admin,
    auth,
    classes,
    data_admin,
    exports,
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
from .services.data_backup import auto_backup_loop


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database:
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)

    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(app.state.engine)
        ensure_schema(app.state.engine)
        with make_session_factory(app.state.engine)() as session:
            seed_admin(session, settings)
        backup_task = None
        if settings.backup_scheduler_enabled:
            backup_task = asyncio.create_task(auto_backup_loop(settings.database_url))
            app.state.backup_task = backup_task
        yield
        if backup_task is not None:
            backup_task.cancel()
            with suppress(asyncio.CancelledError):
                await backup_task
        app.state.engine.dispose()

    app = FastAPI(title="星灿点赞积分系统", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.login_failures = {}
    app.state.maintenance = False
    app.state.data_lock = asyncio.Lock()

    @app.middleware("http")
    async def maintenance_guard(request, call_next):
        if app.state.maintenance and request.url.path not in (
            "/api/health",
            "/api/admin/data/restore",
        ):
            return JSONResponse(status_code=503, content={"detail": "数据恢复中，请稍候"})
        return await call_next(request)

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(data_admin.router)
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
    app.include_router(exports.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # 前端构建产物（存在时托管，开发模式下由 Vite 代理）
    dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    return app