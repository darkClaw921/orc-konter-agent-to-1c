"""
Скрипт для заполнения БД тестовыми данными
"""
import sys
from pathlib import Path
from datetime import datetime

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.database import SessionLocal, Contract, ProcessingState
from app.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def seed_db():
    """Заполнение БД тестовыми данными"""
    db = SessionLocal()
    
    try:
        logger.info("Starting database seeding")
        
        # Здесь можно добавить тестовые данные
        # Например, создать тестовый контракт
        
        logger.info("Database seeded successfully")
        
    except Exception as e:
        logger.error("Failed to seed database", error=str(e))
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_db()
