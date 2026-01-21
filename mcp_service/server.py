"""
Точка входа MCP сервиса
"""
import os
import sys
import structlog
from aiohttp import web

# Добавляем текущую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.mcp_server import MCPServer
from client.oneс_client import OneCClient

# Настройка логирования
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger(__name__)


def create_app() -> web.Application:
    """Создать AIOHTTP приложение"""
    
    # Загрузка конфигурации из переменных окружения
    config = {
        'ONEС_ODATA_URL': os.getenv('ONEС_ODATA_URL', ''),
        'ONEС_USERNAME': os.getenv('ONEС_USERNAME', ''),
        'ONEС_PASSWORD': os.getenv('ONEС_PASSWORD', ''),
    }
    
    mcp_server = MCPServer(config)
    
    app = web.Application()
    
    # Маршруты
    app.router.add_get('/sse/{client_id}', mcp_server.handle_sse_connect)
    app.router.add_post('/command', mcp_server.execute_command)
    app.router.add_get('/health', lambda request: web.json_response({'status': 'ok'}))
    
    # Middleware для CORS
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == 'OPTIONS':
            response = web.Response()
        else:
            response = await handler(request)
        
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    app.middlewares.append(cors_middleware)
    
    # Инициализация при старте
    async def on_startup(app):
        mcp_server.oneс_client = OneCClient(config)
        await mcp_server.oneс_client.initialize()
        logger.info("MCP Server started", config_base_url=config.get('ONEС_ODATA_URL', 'not configured'))
    
    async def on_cleanup(app):
        if mcp_server.oneс_client:
            await mcp_server.oneс_client.close()
        logger.info("MCP Server stopped")
    
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    return app


def main():
    """Главная функция запуска сервера"""
    app = create_app()
    
    port = int(os.getenv('PORT', '9000'))
    host = os.getenv('HOST', '0.0.0.0')
    
    logger.info("Starting MCP Service", host=host, port=port)
    
    web.run_app(app, host=host, port=port)


if __name__ == '__main__':
    main()
