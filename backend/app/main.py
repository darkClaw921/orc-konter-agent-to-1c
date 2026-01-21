"""
Точка входа FastAPI приложения
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from app.config import settings
from app.api.v1.router import router as api_v1_router
from app.utils.logging import configure_logging, get_logger
from app.utils.metrics import get_metrics_response, api_response_time, api_requests_total
from app.utils.tracing import configure_tracing, get_tracer
from app.utils.exceptions import SGRAgentException

# Настройка логирования
configure_logging(settings.LOG_FILE if settings.LOG_FILE else None)
logger = get_logger(__name__)

# Настройка трассировки (если включена)
if not settings.DEBUG:
    try:
        configure_tracing(
            service_name=settings.APP_NAME.lower().replace(" ", "-"),
            jaeger_host="jaeger",
            jaeger_port=14268
        )
        logger.info("Tracing configured")
    except Exception as e:
        logger.warning("Failed to configure tracing", error=str(e))

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В production указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Обработка исключений
@app.exception_handler(SGRAgentException)
async def sgr_exception_handler(request: Request, exc: SGRAgentException):
    """Обработчик исключений SGR Agent"""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "error_code": getattr(exc, 'error_code', 'UNKNOWN')}
    )


# Middleware для метрик API
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware для сбора метрик API"""
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    # Собираем метрики
    api_response_time.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code
    ).observe(duration)
    
    api_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code
    ).inc()
    
    return response


# Регистрация роутов
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return get_metrics_response()


@app.on_event("startup")
async def startup_event():
    """События при запуске приложения"""
    logger.info("Starting application", 
               app_name=settings.APP_NAME,
               version=settings.APP_VERSION,
               debug=settings.DEBUG)


@app.on_event("shutdown")
async def shutdown_event():
    """События при остановке приложения"""
    logger.info("Shutting down application", app_name=settings.APP_NAME)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
