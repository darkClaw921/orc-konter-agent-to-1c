"""
Скрипт для резервного копирования БД
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def backup_database():
    """Создание резервной копии БД через pg_dump"""
    # Парсим DATABASE_URL
    db_url = settings.DATABASE_URL
    if not db_url.startswith("postgresql://"):
        logger.error("Invalid DATABASE_URL format")
        sys.exit(1)
    
    # Извлекаем параметры из URL
    url_parts = db_url.replace("postgresql://", "").split("@")
    if len(url_parts) != 2:
        logger.error("Invalid DATABASE_URL format")
        sys.exit(1)
    
    user_pass, host_db = url_parts
    user, password = user_pass.split(":")
    host_port, database = host_db.split("/")
    host, port = host_port.split(":") if ":" in host_port else (host_port, "5432")
    
    # Создаем директорию для бэкапов
    backup_dir = Path("./storage/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем имя файла с датой и временем
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"backup_{database}_{timestamp}.sql"
    
    # Устанавливаем переменную окружения для пароля
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    
    logger.info("Starting database backup", database=database, backup_file=str(backup_file))
    
    try:
        # Выполняем pg_dump
        cmd = [
            "pg_dump",
            "-h", host,
            "-p", port,
            "-U", user,
            "-d", database,
            "-F", "c",  # Custom format
            "-f", str(backup_file)
        ]
        
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )
        
        logger.info("Database backup completed successfully", backup_file=str(backup_file))
        
        # Удаляем старые бэкапы (оставляем последние 7)
        backups = sorted(backup_dir.glob("backup_*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old_backup in backups[7:]:
            old_backup.unlink()
            logger.info("Deleted old backup", backup_file=str(old_backup))
        
        return str(backup_file)
        
    except subprocess.CalledProcessError as e:
        logger.error("Failed to create database backup", error=str(e), stderr=e.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error during backup", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    backup_database()
