"""
Настройка логирования с structlog для ELK Stack
"""
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

import structlog
from structlog.stdlib import LoggerFactory
from pythonjsonlogger import jsonlogger

from app.config import settings


def configure_logging(log_file: Optional[str] = None) -> None:
    """
    Настройка структурированного логирования через structlog с поддержкой ELK
    
    Args:
        log_file: Путь к файлу для записи логов (опционально)
    """
    handlers = []
    
    # Console handler с JSON форматом для ELK
    console_handler = logging.StreamHandler(sys.stdout)
    json_formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )
    console_handler.setFormatter(json_formatter)
    handlers.append(console_handler)
    
    # File handler с JSON форматом и ротацией для ELK
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Используем RotatingFileHandler для ротации логов
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(json_formatter)
        handlers.append(file_handler)
    
    # Настройка стандартного логирования
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper()),
        handlers=handlers,
        force=True
    )
    
    # Настройка structlog с JSON renderer для ELK
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        # Добавляем дополнительные поля для ELK
        structlog.processors.add_log_level,
        structlog.processors.ExceptionPrettyPrinter(),
    ]
    
    # Всегда используем JSON renderer для совместимости с ELK
    processors.append(structlog.processors.JSONRenderer())
    
    # Добавляем контекстные поля для ELK через процессор
    def add_service_context(logger, method_name, event_dict):
        """Добавляет базовые поля сервиса в каждый лог"""
        if isinstance(event_dict, dict):
            event_dict['service_name'] = settings.APP_NAME
            event_dict['environment'] = "production" if not settings.DEBUG else "development"
            event_dict['version'] = settings.APP_VERSION
        return event_dict
    
    processors.append(add_service_context)
    
    # Настройка structlog с JSON renderer для ELK
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
        wrapper_class=structlog.stdlib.BoundLogger,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Получить logger для модуля
    
    Args:
        name: Имя модуля (обычно __name__)
        
    Returns:
        Настроенный logger
    """
    return structlog.get_logger(name)


# Инициализация логирования при импорте модуля
configure_logging(settings.LOG_FILE if settings.LOG_FILE else None)
