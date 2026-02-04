"""
Сервис для управления хранилищем файлов
"""
import hashlib
import shutil
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

from app.config import settings
from app.utils.logging import get_logger
from app.utils.exceptions import StorageError

logger = get_logger(__name__)


class StorageService:
    """Сервис для работы с хранилищем файлов"""
    
    def __init__(self):
        self.storage_type = settings.STORAGE_TYPE
        self.storage_path = Path(settings.STORAGE_PATH)
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Создать необходимые директории если их нет"""
        uploaded_dir = self.storage_path / "uploaded"
        processed_dir = self.storage_path / "processed"
        
        uploaded_dir.mkdir(parents=True, exist_ok=True)
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Storage directories ensured", 
                   storage_path=str(self.storage_path),
                   storage_type=self.storage_type)
    
    def _compute_hash(self, file_content: bytes) -> str:
        """
        Вычислить SHA256 хеш файла
        
        Args:
            file_content: Содержимое файла в байтах
            
        Returns:
            SHA256 хеш в виде hex строки
        """
        return hashlib.sha256(file_content).hexdigest()
    
    def save_uploaded_file(self, file_content: bytes, filename: str) -> Tuple[str, str]:
        """
        Сохранить загруженный файл
        
        Args:
            file_content: Содержимое файла в байтах
            filename: Оригинальное имя файла
            
        Returns:
            Tuple[file_path, file_hash]
        """
        try:
            # Генерируем уникальное имя файла
            file_uuid = str(uuid4())
            file_extension = Path(filename).suffix
            new_filename = f"{file_uuid}{file_extension}"
            
            # Путь для сохранения
            file_path = self.storage_path / "uploaded" / new_filename
            
            # Сохраняем файл
            file_path.write_bytes(file_content)
            
            # Вычисляем хеш файла
            file_hash = self._compute_hash(file_content)
            
            logger.info("File saved", 
                       filename=filename,
                       file_path=str(file_path),
                       file_size=len(file_content),
                       file_hash=file_hash)
            
            return str(file_path), file_hash
            
        except Exception as e:
            logger.error("Failed to save file", 
                        filename=filename,
                        error=str(e))
            raise StorageError(f"Failed to save file: {str(e)}")
    
    def move_to_processed(self, file_path: str) -> str:
        """
        Переместить файл в директорию processed
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Новый путь к файлу
        """
        try:
            source_path = Path(file_path)
            if not source_path.exists():
                raise StorageError(f"File not found: {file_path}")
            
            # Создаем новое имя в директории processed
            new_path = self.storage_path / "processed" / source_path.name
            
            # Перемещаем файл
            shutil.move(str(source_path), str(new_path))
            
            logger.info("File moved to processed", 
                       source=str(source_path),
                       destination=str(new_path))
            
            return str(new_path)
            
        except Exception as e:
            logger.error("Failed to move file", 
                        file_path=file_path,
                        error=str(e))
            raise StorageError(f"Failed to move file: {str(e)}")
    
    def get_file_path(self, file_path: str) -> Path:
        """
        Получить Path объект для файла
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Path объект
        """
        path = Path(file_path)
        if not path.exists():
            raise StorageError(f"File not found: {file_path}")
        return path
    
    def delete_file(self, file_path: str) -> None:
        """
        Удалить файл
        
        Args:
            file_path: Путь к файлу
        """
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.info("File deleted", file_path=str(path))
            else:
                logger.warning("File not found for deletion", file_path=str(path))
                
        except Exception as e:
            logger.error("Failed to delete file", 
                        file_path=file_path,
                        error=str(e))
            raise StorageError(f"Failed to delete file: {str(e)}")
    
    def get_file_size(self, file_path: str) -> int:
        """
        Получить размер файла в байтах
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Размер файла в байтах
        """
        path = Path(file_path)
        if not path.exists():
            raise StorageError(f"File not found: {file_path}")
        return path.stat().st_size
