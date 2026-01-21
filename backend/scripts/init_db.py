"""
Скрипт для инициализации БД и применения миграций
"""
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic.config import Config
from alembic import command
from app.config import settings
from app.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def init_db():
    """Инициализация БД через Alembic миграции"""
    alembic_cfg = Config("alembic.ini")
    
    logger.info("Starting database initialization")
    
    try:
        # Применяем все миграции
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied successfully")
        
    except Exception as e:
        logger.error("Failed to apply migrations", error=str(e))
        raise


if __name__ == "__main__":
    init_db()
