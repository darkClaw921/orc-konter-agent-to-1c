"""
Хранилище тестовых случаев для валидации результатов обработки
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TestCase:
    """Тестовый случай для валидации обработки контракта"""
    id: str
    name: str
    description: str
    input_document: str  # Путь к DOCX файлу
    expected_output: Dict[str, Any]  # Ожидаемые извлеченные данные
    required_fields: List[str] = field(default_factory=list)  # Обязательные поля для проверки
    tolerance: Dict[str, float] = field(default_factory=dict)  # Допустимые отклонения для числовых полей
    tags: List[str] = field(default_factory=list)  # Теги для фильтрации
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], base_path: Optional[str] = None) -> 'TestCase':
        """Создать TestCase из словаря"""
        # Если input_document относительный путь, делаем его абсолютным относительно base_path
        input_document = data.get('input_document', '')
        if base_path and not os.path.isabs(input_document):
            input_document = os.path.join(base_path, input_document)
        
        return cls(
            id=data['id'],
            name=data['name'],
            description=data.get('description', ''),
            input_document=input_document,
            expected_output=data['expected_output'],
            required_fields=data.get('required_fields', []),
            tolerance=data.get('tolerance', {}),
            tags=data.get('tags', [])
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать TestCase в словарь"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'input_document': self.input_document,
            'expected_output': self.expected_output,
            'required_fields': self.required_fields,
            'tolerance': self.tolerance,
            'tags': self.tags
        }


class TestCaseManager:
    """Менеджер для загрузки и управления тестовыми случаями"""
    
    def __init__(self, test_cases_dir: Optional[str] = None):
        """
        Инициализация менеджера тестовых случаев
        
        Args:
            test_cases_dir: Путь к директории с JSON файлами тестовых случаев.
                          Если не указан, используется tests/test_cases/ относительно корня проекта
        """
        if test_cases_dir is None:
            # Определяем корень проекта (backend/)
            backend_dir = Path(__file__).parent.parent
            test_cases_dir = str(backend_dir / 'tests' / 'test_cases')
        
        self.test_cases_dir = Path(test_cases_dir)
        self.test_cases: Dict[str, TestCase] = {}
        self._load_test_cases()
    
    def _load_test_cases(self):
        """Загрузить все тестовые случаи из JSON файлов"""
        if not self.test_cases_dir.exists():
            logger.warning("Test cases directory does not exist", directory=str(self.test_cases_dir))
            return
        
        json_files = list(self.test_cases_dir.glob('*.json'))
        logger.info("Loading test cases", directory=str(self.test_cases_dir), count=len(json_files))
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Поддерживаем как один объект, так и массив объектов
                if isinstance(data, list):
                    for item in data:
                        test_case = TestCase.from_dict(item, base_path=str(self.test_cases_dir))
                        self.test_cases[test_case.id] = test_case
                else:
                    test_case = TestCase.from_dict(data, base_path=str(self.test_cases_dir))
                    self.test_cases[test_case.id] = test_case
                
                logger.debug("Test case loaded", file=str(json_file), test_id=test_case.id)
            
            except Exception as e:
                logger.error("Failed to load test case", file=str(json_file), error=str(e))
    
    def get_test_case(self, test_id: str) -> Optional[TestCase]:
        """Получить тестовый случай по ID"""
        return self.test_cases.get(test_id)
    
    def get_test_cases(self, tags: Optional[List[str]] = None) -> List[TestCase]:
        """
        Получить список тестовых случаев с фильтрацией по тегам
        
        Args:
            tags: Список тегов для фильтрации. Если указан, возвращаются только тесты,
                 у которых есть хотя бы один из указанных тегов.
                 Если None, возвращаются все тесты.
        
        Returns:
            Список тестовых случаев
        """
        if tags is None or len(tags) == 0:
            return list(self.test_cases.values())
        
        filtered = []
        for test_case in self.test_cases.values():
            # Проверяем, есть ли хотя бы один общий тег
            if any(tag in test_case.tags for tag in tags):
                filtered.append(test_case)
        
        return filtered
    
    def get_all_test_cases(self) -> List[TestCase]:
        """Получить все тестовые случаи"""
        return list(self.test_cases.values())
    
    def reload(self):
        """Перезагрузить тестовые случаи из файлов"""
        self.test_cases.clear()
        self._load_test_cases()
