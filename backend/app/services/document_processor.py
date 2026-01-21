"""
Парсер DOCX и PDF файлов с использованием docling для извлечения таблиц
"""
import os
import re
from typing import Dict, List, Optional, Any
from pathlib import Path

import pandas as pd
from docx import Document
from docx.document import Document as DocType
from docling.document_converter import DocumentConverter
from docling_core.types.doc import TextItem, TableItem

from app.utils.logging import get_logger

logger = get_logger(__name__)


class DocumentProcessor:
    """
    Процессор для извлечения текста из DOCX и PDF документов с использованием docling
    """
    
    def __init__(self):
        self.document: Optional[DocType] = None
        self.docling_result: Optional[Any] = None
        self.docling_converter: Optional[DocumentConverter] = None
        self.file_path: Optional[str] = None
        self.file_type: Optional[str] = None  # 'docx' или 'pdf'
        self.raw_text: str = ""
        self.paragraphs: List[str] = []
        self.tables: List[Dict[str, Any]] = []  # Список словарей с данными таблиц
    
    def load_document(self, file_path: str) -> bool:
        """
        Загрузить DOCX или PDF документ с использованием docling
        
        Args:
            file_path: Путь к файлу документа
            
        Returns:
            True если документ успешно загружен, False в противном случае
        """
        self.file_path = file_path
        file_ext = Path(file_path).suffix.lower()
        
        # Определяем тип файла
        if file_ext == '.docx':
            self.file_type = 'docx'
        elif file_ext == '.pdf':
            self.file_type = 'pdf'
        else:
            logger.error("Unsupported file type", file_path=file_path, extension=file_ext)
            return False
        
        # Пытаемся загрузить через docling
        try:
            if not self.docling_converter:
                self.docling_converter = DocumentConverter()
            
            self.docling_result = self.docling_converter.convert(file_path)
            logger.info("Document loaded with docling", 
                       file_path=file_path, 
                       file_type=self.file_type,
                       page_count=getattr(self.docling_result.input, 'page_count', None))
            
            # Для обратной совместимости также загружаем через python-docx для DOCX
            if self.file_type == 'docx':
                try:
                    self.document = Document(file_path)
                except Exception as e:
                    logger.warning("Failed to load with python-docx, using docling only",
                                 error=str(e))
            
            return True
        except Exception as e:
            logger.error("Failed to load document with docling", 
                        error=str(e), 
                        file_path=file_path,
                        error_type=type(e).__name__)
            
            # Fallback на python-docx для DOCX файлов
            if self.file_type == 'docx':
                try:
                    logger.info("Trying fallback to python-docx")
                    self.document = Document(file_path)
                    logger.info("Document loaded with python-docx fallback", file_path=file_path)
                    return True
                except Exception as fallback_error:
                    logger.error("Fallback to python-docx also failed",
                               error=str(fallback_error))
            
            return False
    
    def extract_text(self) -> str:
        """
        Извлечь весь текст из документа включая таблицы в markdown формате
        
        Returns:
            Текст документа с таблицами в markdown формате
        """
        if not self.docling_result and not self.document:
            raise ValueError("Document not loaded")
        
        text_parts = []
        self.paragraphs = []
        self.tables = []
        
        # Используем docling если доступен
        if self.docling_result:
            doc = self.docling_result.document
            
            # Извлекаем текст и таблицы через docling API
            for item, level in doc.iterate_items():
                if isinstance(item, TextItem):
                    text = item.text.strip()
                    if text:
                        text_parts.append(text)
                        self.paragraphs.append(text)
                elif isinstance(item, TableItem):
                    # Извлекаем таблицу в структурированном виде
                    table_data = self._extract_table_from_docling(item)
                    if table_data:
                        self.tables.append(table_data)
                        # Добавляем таблицу в markdown формате в текст
                        text_parts.append(f"\n\n## Таблица {len(self.tables)}\n\n")
                        text_parts.append(table_data['markdown'])
                        text_parts.append("\n")
        
        # Fallback на python-docx для DOCX если docling не сработал
        elif self.document and self.file_type == 'docx':
            logger.info("Using python-docx fallback for text extraction")
            
            # Извлечение текста из параграфов
            for paragraph in self.document.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text)
                    self.paragraphs.append(paragraph.text)
            
            # Извлечение текста из таблиц (простой формат)
            for table_idx, table in enumerate(self.document.tables):
                table_data = []
                for row in table.rows:
                    row_data = []
                    for cell in row.cells:
                        row_data.append(cell.text.strip())
                    table_data.append(row_data)
                
                # Сохраняем таблицу в старом формате для обратной совместимости
                self.tables.append({
                    "index": table_idx,
                    "markdown": self._convert_table_to_markdown(table_data),
                    "dataframe": pd.DataFrame(table_data[1:], columns=table_data[0]) if table_data else pd.DataFrame(),
                    "row_count": len(table_data),
                    "column_count": len(table_data[0]) if table_data else 0
                })
                
                text_parts.append(f"\n\n## Таблица {table_idx + 1}\n\n")
                text_parts.append(self.tables[-1]['markdown'])
                text_parts.append("\n")
        
        self.raw_text = "\n".join(text_parts)
        logger.info("Text extracted", 
                   length=len(self.raw_text),
                   paragraphs_count=len(self.paragraphs),
                   tables_count=len(self.tables))
        return self.raw_text
    
    def _extract_table_from_docling(self, table_item: TableItem) -> Optional[Dict[str, Any]]:
        """
        Извлечь таблицу из docling TableItem в структурированном виде
        
        Args:
            table_item: TableItem из docling
            
        Returns:
            Словарь с данными таблицы или None если не удалось извлечь
        """
        try:
            df = table_item.export_to_dataframe(doc=self.docling_result.document)
            
            # Конвертируем DataFrame в markdown
            markdown_table = df.to_markdown(index=False)
            
            table_data = {
                "index": len(self.tables),
                "markdown": markdown_table,
                "dataframe": df,
                "row_count": len(df),
                "column_count": len(df.columns)
            }
            
            logger.debug("Table extracted", 
                        table_index=table_data["index"],
                        rows=table_data["row_count"],
                        columns=table_data["column_count"])
            
            return table_data
        except Exception as e:
            logger.warning("Failed to extract table from docling",
                         error=str(e),
                         error_type=type(e).__name__)
            return None
    
    def _convert_table_to_markdown(self, table_data: List[List[str]]) -> str:
        """
        Конвертировать таблицу в markdown формат
        
        Args:
            table_data: Список строк таблицы
            
        Returns:
            Таблица в markdown формате
        """
        if not table_data:
            return ""
        
        # Первая строка - заголовки
        headers = table_data[0] if table_data else []
        if not headers:
            return ""
        
        # Формируем markdown таблицу
        markdown_lines = []
        
        # Заголовки
        markdown_lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        
        # Разделитель
        markdown_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        
        # Данные
        for row in table_data[1:]:
            # Дополняем строку до нужной длины если нужно
            row_padded = row + [""] * (len(headers) - len(row))
            markdown_lines.append("| " + " | ".join(str(cell) for cell in row_padded[:len(headers)]) + " |")
        
        return "\n".join(markdown_lines)
    
    def extract_tables(self) -> List[Dict[str, Any]]:
        """
        Извлечь все таблицы из документа в структурированном виде
        
        Returns:
            Список словарей с данными таблиц (markdown, DataFrame, метаданные)
        """
        if not self.tables:
            # Если таблицы еще не извлечены, вызываем extract_text
            self.extract_text()
        
        return self.tables
    
    def get_tables_markdown(self) -> str:
        """
        Получить все таблицы в markdown формате для включения в контекст LLM
        
        Returns:
            Все таблицы документа в markdown формате, разделенные заголовками
        """
        if not self.tables:
            self.extract_tables()
        
        if not self.tables:
            return ""
        
        markdown_parts = []
        for table_data in self.tables:
            markdown_parts.append(f"## Таблица {table_data['index'] + 1}")
            markdown_parts.append("")
            markdown_parts.append(table_data['markdown'])
            markdown_parts.append("")
        
        return "\n".join(markdown_parts)
    
    def extract_sections(self) -> Dict[str, str]:
        """Извлечь основные разделы документа"""
        if not self.raw_text:
            self.extract_text()
        
        sections = {}
        
        # Ищем типичные разделы контрактов
        section_patterns = {
            "header": r"(?:договор|контракт|соглашение)(.*?)(?:стороны|участники|предмет)",
            "parties": r"(?:стороны|участники):(.*?)(?:предмет|место оказания)",
            "subject": r"(?:предмет|услуг)(.*?)(?:стоимость|цена|размер)",
            "price": r"(?:стоимость|цена|размер вознаграждения)(.*?)(?:срок|дата|условия)",
            "terms": r"(?:срок|сроки|период)(.*?)(?:условия|порядок|оплата)",
            "conditions": r"(?:условия|прочие положения)(.*?)(?:подпись|подписано|дата)",
        }
        
        for section_name, pattern in section_patterns.items():
            match = re.search(pattern, self.raw_text, re.IGNORECASE | re.DOTALL)
            if match:
                sections[section_name] = match.group(1)[:1000]
        
        logger.info("Sections extracted", count=len(sections))
        return sections
    
    def get_context_for_llm(self, max_tokens: int = 8000) -> str:
        """
        Подготовить контекст для отправки в LLM.
        Включает текст документа и таблицы в markdown формате.
        Ограничивает размер, чтобы не превысить лимиты токенов.
        
        Args:
            max_tokens: Максимальное количество токенов в контексте
            
        Returns:
            Контекст документа с таблицами в markdown формате
        """
        if not self.raw_text:
            self.extract_text()
        
        # Таблицы уже включены в raw_text через extract_text()
        # Но если нужно, можно добавить дополнительную обработку
        
        # Если текст слишком большой, берем только начало
        # Примерно 4 символа на токен
        max_chars = max_tokens * 4
        if len(self.raw_text) > max_chars:
            truncated_text = self.raw_text[:max_chars]
            logger.warning("Document truncated", 
                         original=len(self.raw_text), 
                         truncated=len(truncated_text),
                         max_tokens=max_tokens)
            return truncated_text
        
        return self.raw_text
    
    def estimate_tokens(self, text: str) -> int:
        """Оценить количество токенов в тексте"""
        # Примерная оценка: 1 токен ≈ 4 символа
        return len(text) // 4
    
    def split_into_chunks(self, max_chunk_size: int, overlap: int = 200) -> List[str]:
        """
        Разбить текст документа на чанки с перекрытием
        
        Args:
            max_chunk_size: Максимальный размер чанка в символах
            overlap: Размер перекрытия между чанками в символах
            
        Returns:
            Список текстовых чанков
        """
        if not self.raw_text:
            self.extract_text()
        
        if len(self.raw_text) <= max_chunk_size:
            return [self.raw_text]
        
        chunks = []
        paragraphs = self.paragraphs.copy()
        
        # Если параграфов нет, разбиваем по предложениям
        if not paragraphs:
            sentences = re.split(r'(?<=[.!?])\s+', self.raw_text)
            paragraphs = [s for s in sentences if s.strip()]
        
        current_chunk = []
        current_size = 0
        
        for paragraph in paragraphs:
            para_text = paragraph.strip()
            if not para_text:
                continue
            
            para_size = len(para_text)
            
            # Если параграф сам по себе больше max_chunk_size, разбиваем его
            if para_size > max_chunk_size:
                # Сохраняем текущий чанк если есть
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    current_size = 0
                
                # Разбиваем большой параграф на части
                words = para_text.split()
                temp_chunk = []
                temp_size = 0
                
                for word in words:
                    word_size = len(word) + 1  # +1 для пробела
                    if temp_size + word_size > max_chunk_size and temp_chunk:
                        chunks.append(" ".join(temp_chunk))
                        # Добавляем перекрытие из предыдущего чанка
                        overlap_words = temp_chunk[-overlap//10:] if len(temp_chunk) > overlap//10 else temp_chunk
                        temp_chunk = overlap_words + [word]
                        temp_size = sum(len(w) + 1 for w in temp_chunk)
                    else:
                        temp_chunk.append(word)
                        temp_size += word_size
                
                if temp_chunk:
                    current_chunk = temp_chunk
                    current_size = temp_size
                continue
            
            # Проверяем, поместится ли параграф в текущий чанк
            if current_size + para_size + 1 <= max_chunk_size:
                current_chunk.append(para_text)
                current_size += para_size + 1
            else:
                # Сохраняем текущий чанк
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                
                # Начинаем новый чанк с перекрытием
                if overlap > 0 and current_chunk:
                    # Берем последние параграфы для перекрытия
                    overlap_text = "\n".join(current_chunk[-overlap//100:]) if len(current_chunk) > overlap//100 else "\n".join(current_chunk)
                    overlap_size = len(overlap_text)
                    current_chunk = [overlap_text, para_text] if overlap_size < max_chunk_size // 2 else [para_text]
                    current_size = len("\n".join(current_chunk))
                else:
                    current_chunk = [para_text]
                    current_size = para_size
        
        # Добавляем последний чанк
        if current_chunk:
            chunks.append("\n".join(current_chunk))
        
        logger.info("Document split into chunks", 
                   total_chunks=len(chunks),
                   avg_chunk_size=sum(len(c) for c in chunks) // len(chunks) if chunks else 0)
        
        return chunks
    
    def get_chunks_for_llm(self, max_tokens_per_chunk: int = 8000) -> List[str]:
        """
        Получить список чанков документа для обработки через LLM
        
        Args:
            max_tokens_per_chunk: Максимальное количество токенов в одном чанке
            
        Returns:
            Список текстовых чанков
        """
        # Примерно 4 символа на токен
        max_chunk_size = max_tokens_per_chunk * 4
        # Перекрытие ~200 символов для сохранения контекста
        overlap = 200
        
        return self.split_into_chunks(max_chunk_size=max_chunk_size, overlap=overlap)