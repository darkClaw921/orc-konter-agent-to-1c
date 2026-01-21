"""
Test Runner для автоматического запуска тестов и сравнения результатов
"""
import asyncio
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Any, List, Optional

from app.services.document_processor import DocumentProcessor
from app.services.llm_service import LLMService
from app.testing.test_cases import TestCase, TestCaseManager
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TestResult:
    """Результат выполнения тестового случая"""
    test_case_id: str
    test_case_name: str
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    expected: Dict[str, Any] = field(default_factory=dict)
    actual: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    missing_fields: List[str] = field(default_factory=list)
    incorrect_fields: List[str] = field(default_factory=list)


@dataclass
class TestReport:
    """Отчет о выполнении тестов"""
    total_tests: int
    passed_tests: int
    failed_tests: int
    success_rate: float
    results: List[TestResult] = field(default_factory=list)
    execution_time: float = 0.0


class TestRunner:
    """Класс для запуска тестов и сравнения результатов"""
    
    def __init__(self, test_case_manager: Optional[TestCaseManager] = None):
        """
        Инициализация TestRunner
        
        Args:
            test_case_manager: Менеджер тестовых случаев. Если не указан, создается новый.
        """
        self.test_case_manager = test_case_manager or TestCaseManager()
        self.document_processor = DocumentProcessor()
        self._llm_service = None
    
    @property
    def llm_service(self) -> LLMService:
        """Ленивая инициализация LLMService"""
        if self._llm_service is None:
            self._llm_service = LLMService()
        return self._llm_service
    
    async def run_test_case(self, test_case: TestCase) -> TestResult:
        """
        Запустить один тестовый случай
        
        Args:
            test_case: Тестовый случай для выполнения
        
        Returns:
            Результат выполнения теста
        """
        start_time = time.time()
        result = TestResult(
            test_case_id=test_case.id,
            test_case_name=test_case.name,
            passed=False,
            expected=test_case.expected_output
        )
        
        try:
            # Проверяем существование файла документа
            if not test_case.input_document or not os.path.exists(test_case.input_document):
                result.errors.append(f"Input document not found: {test_case.input_document}")
                result.execution_time = time.time() - start_time
                return result
            
            # Загружаем документ
            if not self.document_processor.load_document(test_case.input_document):
                result.errors.append("Failed to load document")
                result.execution_time = time.time() - start_time
                return result
            
            # Извлекаем текст
            document_text = self.document_processor.extract_text()
            if not document_text:
                result.errors.append("Failed to extract text from document")
                result.execution_time = time.time() - start_time
                return result
            
            # Извлекаем данные через LLM
            try:
                extracted_data = await self.llm_service.extract_contract_data(document_text)
                result.actual = extracted_data
            except Exception as e:
                result.errors.append(f"Failed to extract data via LLM: {str(e)}")
                result.execution_time = time.time() - start_time
                return result
            
            # Сравниваем результаты
            comparison_result = self._compare_results(
                expected=test_case.expected_output,
                actual=extracted_data,
                required_fields=test_case.required_fields,
                tolerance=test_case.tolerance
            )
            
            result.errors.extend(comparison_result['errors'])
            result.warnings.extend(comparison_result['warnings'])
            result.missing_fields = comparison_result['missing_fields']
            result.incorrect_fields = comparison_result['incorrect_fields']
            result.passed = len(comparison_result['errors']) == 0
            
            logger.info("Test case executed",
                       test_id=test_case.id,
                       passed=result.passed,
                       errors_count=len(result.errors),
                       warnings_count=len(result.warnings))
        
        except Exception as e:
            logger.error("Test case execution failed", test_id=test_case.id, error=str(e))
            result.errors.append(f"Unexpected error: {str(e)}")
        
        finally:
            result.execution_time = time.time() - start_time
        
        return result
    
    async def run_all_tests(self, tags: Optional[List[str]] = None) -> TestReport:
        """
        Запустить все тесты с опциональной фильтрацией по тегам
        
        Args:
            tags: Список тегов для фильтрации тестов
        
        Returns:
            Отчет о выполнении тестов
        """
        start_time = time.time()
        test_cases = self.test_case_manager.get_test_cases(tags)
        
        logger.info("Running all tests", total=len(test_cases), tags=tags)
        
        results = []
        for test_case in test_cases:
            result = await self.run_test_case(test_case)
            results.append(result)
        
        execution_time = time.time() - start_time
        
        # Подсчитываем статистику
        passed_tests = sum(1 for r in results if r.passed)
        failed_tests = len(results) - passed_tests
        success_rate = (passed_tests / len(results) * 100) if results else 0.0
        
        report = TestReport(
            total_tests=len(results),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            success_rate=success_rate,
            results=results,
            execution_time=execution_time
        )
        
        logger.info("All tests completed",
                   total=report.total_tests,
                   passed=report.passed_tests,
                   failed=report.failed_tests,
                   success_rate=f"{report.success_rate:.2f}%")
        
        return report
    
    def _compare_results(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        required_fields: List[str],
        tolerance: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Сравнить ожидаемые и фактические результаты
        
        Args:
            expected: Ожидаемые данные
            actual: Фактические данные
            required_fields: Список обязательных полей для проверки
            tolerance: Допустимые отклонения для числовых полей
        
        Returns:
            Словарь с ошибками, предупреждениями и списками отсутствующих/некорректных полей
        """
        errors: List[str] = []
        warnings: List[str] = []
        missing_fields: List[str] = []
        incorrect_fields: List[str] = []
        
        # Проверяем обязательные поля
        fields_to_check = required_fields if required_fields else list(expected.keys())
        
        for field in fields_to_check:
            if field not in expected:
                warnings.append(f"Field '{field}' is in required_fields but not in expected_output")
                continue
            
            expected_value = expected[field]
            
            if field not in actual:
                errors.append(f"Missing required field: {field}")
                missing_fields.append(field)
                continue
            
            actual_value = actual[field]
            
            # Сравнение с учетом типа данных
            if isinstance(expected_value, (int, float, str)) and isinstance(actual_value, (int, float, str)):
                # Для числовых полей используем tolerance
                if field in tolerance and isinstance(expected_value, (int, float)) and isinstance(actual_value, (int, float)):
                    expected_decimal = Decimal(str(expected_value))
                    actual_decimal = Decimal(str(actual_value))
                    tolerance_value = Decimal(str(tolerance[field]))
                    
                    difference = abs(expected_decimal - actual_decimal)
                    if difference > tolerance_value:
                        errors.append(
                            f"Field '{field}' value mismatch: expected {expected_value}, "
                            f"got {actual_value} (difference: {difference}, tolerance: {tolerance_value})"
                        )
                        incorrect_fields.append(field)
                else:
                    # Для строковых полей - точное сравнение (но нормализуем пробелы)
                    expected_str = str(expected_value).strip()
                    actual_str = str(actual_value).strip()
                    
                    if expected_str.lower() != actual_str.lower():
                        errors.append(
                            f"Field '{field}' value mismatch: expected '{expected_value}', got '{actual_value}'"
                        )
                        incorrect_fields.append(field)
            
            elif isinstance(expected_value, list) and isinstance(actual_value, list):
                # Для списков проверяем длину и элементы
                if len(expected_value) != len(actual_value):
                    errors.append(
                        f"Field '{field}' list length mismatch: expected {len(expected_value)}, got {len(actual_value)}"
                    )
                    incorrect_fields.append(field)
                else:
                    # Рекурсивное сравнение элементов списка
                    for i, (exp_item, act_item) in enumerate(zip(expected_value, actual_value)):
                        if isinstance(exp_item, dict) and isinstance(act_item, dict):
                            nested_result = self._compare_results(
                                expected=exp_item,
                                actual=act_item,
                                required_fields=list(exp_item.keys()),
                                tolerance={}
                            )
                            if nested_result['errors']:
                                errors.extend([f"{field}[{i}].{e}" for e in nested_result['errors']])
                                incorrect_fields.append(f"{field}[{i}]")
                        elif exp_item != act_item:
                            errors.append(
                                f"Field '{field}[{i}]' value mismatch: expected '{exp_item}', got '{act_item}'"
                            )
                            incorrect_fields.append(f"{field}[{i}]")
            
            elif isinstance(expected_value, dict) and isinstance(actual_value, dict):
                # Рекурсивное сравнение вложенных словарей
                nested_result = self._compare_results(
                    expected=expected_value,
                    actual=actual_value,
                    required_fields=list(expected_value.keys()),
                    tolerance={}
                )
                if nested_result['errors']:
                    errors.extend([f"{field}.{e}" for e in nested_result['errors']])
                    incorrect_fields.append(field)
            
            else:
                # Простое сравнение
                if expected_value != actual_value:
                    errors.append(
                        f"Field '{field}' value mismatch: expected '{expected_value}', got '{actual_value}'"
                    )
                    incorrect_fields.append(field)
        
        # Проверяем наличие лишних полей в actual (предупреждение, не ошибка)
        extra_fields = set(actual.keys()) - set(expected.keys())
        if extra_fields:
            warnings.append(f"Extra fields in actual data: {', '.join(extra_fields)}")
        
        return {
            'errors': errors,
            'warnings': warnings,
            'missing_fields': missing_fields,
            'incorrect_fields': incorrect_fields
        }
    
    def generate_report(self, results: List[TestResult]) -> Dict[str, Any]:
        """
        Сгенерировать отчет о результатах тестирования
        
        Args:
            results: Список результатов выполнения тестов
        
        Returns:
            Словарь с отчетом
        """
        if not results:
            return {
                'success_rate': 0.0,
                'passed_tests': 0,
                'failed_tests': 0,
                'total_tests': 0,
                'results': []
            }
        
        passed_tests = sum(1 for r in results if r.passed)
        failed_tests = len(results) - passed_tests
        success_rate = (passed_tests / len(results)) * 100
        
        return {
            'success_rate': round(success_rate, 2),
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'total_tests': len(results),
            'results': [
                {
                    'test_case_id': r.test_case_id,
                    'test_case_name': r.test_case_name,
                    'passed': r.passed,
                    'errors': r.errors,
                    'warnings': r.warnings,
                    'execution_time': round(r.execution_time, 3),
                    'missing_fields': r.missing_fields,
                    'incorrect_fields': r.incorrect_fields
                }
                for r in results
            ]
        }
