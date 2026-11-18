from fastapi import FastAPI

from api.handlers import register_exception_handlers
from api.routes.health import router as health_router
from contexts.sales_assistant.interface.routes import router as sales_router
from contexts.self_practice.interface.routes import router as practice_router
from shared.infrastructure.observability.logging import configure_logging
from shared.infrastructure.observability.tracing import TraceIdMiddleware


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(practice_router)
    app.include_router(sales_router)
    return app


app = create_app()
