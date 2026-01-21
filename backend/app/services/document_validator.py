"""
Валидация загруженных документов
"""
import os
from typing import Tuple

from docx import Document

from app.utils.logging import get_logger

logger = get_logger(__name__)


class DocumentValidator:
    """Валидация загруженных документов"""
    
    ALLOWED_EXTENSIONS = ['.docx', '.pdf']
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    
    @staticmethod
    def validate_file(file_path: str, filename: str) -> Tuple[bool, str]:
        """
        Валидировать загруженный файл
        
        Returns:
            (is_valid, error_message)
        """
        # Проверка расширения
        if not any(filename.lower().endswith(ext) for ext in DocumentValidator.ALLOWED_EXTENSIONS):
            return False, f"Invalid file extension. Allowed: {', '.join(DocumentValidator.ALLOWED_EXTENSIONS)}"
        
        # Проверка размера
        if os.path.getsize(file_path) > DocumentValidator.MAX_FILE_SIZE:
            return False, f"File size exceeds {DocumentValidator.MAX_FILE_SIZE / 1024 / 1024} MB"
        
        # Проверка, что файл может быть открыт
        file_ext = filename.lower()[-5:] if len(filename) >= 5 else filename.lower()
        if file_ext.endswith('.docx'):
            try:
                Document(file_path)
            except Exception as e:
                return False, f"Invalid DOCX file: {str(e)}"
        elif file_ext.endswith('.pdf'):
            # Для PDF проверяем только существование файла
            # Детальная проверка будет при обработке через docling
            if not os.path.exists(file_path):
                return False, f"PDF file not found: {file_path}"
        else:
            return False, f"Unsupported file type: {file_ext}"
        
        logger.info("Document validation passed", filename=filename, file_type=file_ext)
        return True, ""
