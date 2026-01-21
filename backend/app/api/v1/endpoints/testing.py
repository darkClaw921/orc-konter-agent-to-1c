"""
Эндпоинты для управления тестами
"""
from typing import List, Optional, Dict, Any
import os

from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_optional_current_user
from app.models.database import get_db, Contract
from app.models.enums import ProcessingState
from app.services.validation_service import ValidationService
from app.tasks.processing_tasks import process_contract_task
from app.testing.test_cases import TestCaseManager, TestCase
from app.testing.test_runner import TestRunner, TestReport
from app.utils.logging import get_logger
import aiohttp

logger = get_logger(__name__)

router = APIRouter()

# Инициализация сервисов (ленивая инициализация для test_runner)
test_case_manager = TestCaseManager()
test_runner: Optional[TestRunner] = None
validation_service = ValidationService()

def get_test_runner() -> TestRunner:
    """Получить или создать TestRunner"""
    global test_runner
    if test_runner is None:
        test_runner = TestRunner(test_case_manager)
    return test_runner


class RunAllTestsRequest(BaseModel):
    """Запрос на запуск всех тестов"""
    tags: Optional[List[str]] = Field(None, description="Теги для фильтрации тестов")


class RunTestRequest(BaseModel):
    """Запрос на валидацию извлеченных данных"""
    extracted_data: dict = Field(..., description="Извлеченные данные для валидации")


class TestCaseInfo(BaseModel):
    """Информация о тестовом случае"""
    id: str
    name: str
    description: str
    tags: List[str]
    required_fields: List[str]


class TestCaseListResponse(BaseModel):
    """Ответ со списком тестовых случаев"""
    test_cases: List[TestCaseInfo]
    total: int


class TestResultResponse(BaseModel):
    """Ответ с результатом выполнения теста"""
    test_case_id: str
    test_case_name: str
    passed: bool
    errors: List[str]
    warnings: List[str]
    execution_time: float
    missing_fields: List[str]
    incorrect_fields: List[str]


class TestReportResponse(BaseModel):
    """Ответ с отчетом о выполнении тестов"""
    success_rate: float
    passed_tests: int
    failed_tests: int
    total_tests: int
    execution_time: float
    results: List[TestResultResponse]


@router.post("/run-all", response_model=TestReportResponse, status_code=status.HTTP_200_OK)
async def run_all_tests(
    request: RunAllTestsRequest = Body(default=RunAllTestsRequest()),
    current_user: dict = Depends(get_current_user)
):
    """
    Запустить все тестовые случаи с опциональной фильтрацией по тегам
    
    Возвращает отчет с результатами выполнения всех тестов.
    """
    try:
        logger.info("Running all tests", tags=request.tags, user=current_user.get("username"))
        
        report = await get_test_runner().run_all_tests(tags=request.tags)
        
        # Преобразуем TestReport в ответ
        result_responses = [
            TestResultResponse(
                test_case_id=r.test_case_id,
                test_case_name=r.test_case_name,
                passed=r.passed,
                errors=r.errors,
                warnings=r.warnings,
                execution_time=round(r.execution_time, 3),
                missing_fields=r.missing_fields,
                incorrect_fields=r.incorrect_fields
            )
            for r in report.results
        ]
        
        return TestReportResponse(
            success_rate=round(report.success_rate, 2),
            passed_tests=report.passed_tests,
            failed_tests=report.failed_tests,
            total_tests=report.total_tests,
            execution_time=round(report.execution_time, 3),
            results=result_responses
        )
    
    except Exception as e:
        logger.error("Failed to run all tests", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run tests: {str(e)}"
        )


@router.post("/run/{test_case_id}", response_model=TestResultResponse, status_code=status.HTTP_200_OK)
async def run_test_case(
    test_case_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Запустить конкретный тестовый случай
    
    Возвращает результат выполнения указанного теста.
    """
    try:
        test_case = test_case_manager.get_test_case(test_case_id)
        if not test_case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Test case '{test_case_id}' not found"
            )
        
        logger.info("Running test case", test_id=test_case_id, user=current_user.get("username"))
        
        result = await get_test_runner().run_test_case(test_case)
        
        return TestResultResponse(
            test_case_id=result.test_case_id,
            test_case_name=result.test_case_name,
            passed=result.passed,
            errors=result.errors,
            warnings=result.warnings,
            execution_time=round(result.execution_time, 3),
            missing_fields=result.missing_fields,
            incorrect_fields=result.incorrect_fields
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to run test case", test_id=test_case_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run test case: {str(e)}"
        )


@router.get("/cases", response_model=TestCaseListResponse, status_code=status.HTTP_200_OK)
async def list_test_cases(
    tags: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Получить список всех тестовых случаев
    
    Поддерживает фильтрацию по тегам через query параметр (разделенные запятой).
    """
    try:
        # Парсим теги из query параметра
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        test_cases = test_case_manager.get_test_cases(tags=tag_list)
        
        test_case_infos = [
            TestCaseInfo(
                id=tc.id,
                name=tc.name,
                description=tc.description,
                tags=tc.tags,
                required_fields=tc.required_fields
            )
            for tc in test_cases
        ]
        
        return TestCaseListResponse(
            test_cases=test_case_infos,
            total=len(test_case_infos)
        )
    
    except Exception as e:
        logger.error("Failed to list test cases", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list test cases: {str(e)}"
        )


@router.post("/validate-extraction", status_code=status.HTTP_200_OK)
async def validate_extraction(
    request: RunTestRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Валидировать извлеченные данные через ValidationService
    
    Принимает извлеченные данные и возвращает результат валидации.
    """
    try:
        logger.info("Validating extracted data", user=current_user.get("username"))
        
        validation_result = validation_service.validate_contract_data(
            data=request.extracted_data,
            auto_correct=True
        )
        
        return {
            "is_valid": validation_result['is_valid'],
            "errors": validation_result['errors'],
            "warnings": validation_result['warnings'],
            "validated_data": validation_result['validated_data']
        }
    
    except Exception as e:
        logger.error("Failed to validate extraction", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate extraction: {str(e)}"
        )


class ProcessContractRequest(BaseModel):
    """Запрос на обработку контракта"""
    contract_id: int = Field(..., description="ID контракта для обработки")


class ProcessContractResponse(BaseModel):
    """Ответ на запрос обработки контракта"""
    contract_id: int
    status: str
    message: str
    task_id: Optional[str] = None


@router.post("/process-contract", response_model=ProcessContractResponse, status_code=status.HTTP_200_OK)
async def process_contract(
    request: ProcessContractRequest = Body(...),
    current_user: dict = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Обработать уже загруженный контракт (для тестов)
    
    Позволяет повторно обработать документ, который уже был загружен и обработан ранее.
    Это полезно для тестирования, когда нужно обновить результаты обработки без загрузки новых файлов.
    """
    try:
        contract_id = request.contract_id
        username = current_user.get("username") if current_user else "anonymous"
        logger.info("Processing contract for tests", 
                   contract_id=contract_id, 
                   user=username)
        
        # Проверяем существование контракта
        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contract with id {contract_id} not found"
            )
        
        # Проверяем, что файл существует
        if not os.path.exists(contract.file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contract file not found: {contract.file_path}"
            )
        
        # Сбрасываем статус и очищаем ошибки для повторной обработки
        contract.status = ProcessingState.UPLOADED
        contract.error_message = None
        contract.processing_started_at = None
        contract.processing_completed_at = None
        db.commit()
        db.refresh(contract)
        
        # Запускаем асинхронную обработку
        try:
            task = process_contract_task.delay(contract.id, contract.file_path)
            logger.info("Contract processing queued for tests",
                       contract_id=contract.id,
                       filename=contract.original_filename,
                       task_id=task.id,
                       user=username)
            
            return ProcessContractResponse(
                contract_id=contract.id,
                status=contract.status.value,
                message=f"Contract processing queued successfully",
                task_id=task.id
            )
        except Exception as e:
            logger.error("Failed to queue processing task",
                        contract_id=contract.id,
                        error=str(e),
                        error_type=type(e).__name__)
            # Возвращаем статус в failed
            contract.status = ProcessingState.FAILED
            contract.error_message = f"Failed to queue processing task: {str(e)}"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to queue processing task: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to process contract", contract_id=request.contract_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process contract: {str(e)}"
        )


class TestMCP1CResponse(BaseModel):
    """Ответ на запрос тестирования MCP 1С"""
    success: bool
    message: str
    counterparty: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@router.get("/test-mcp-1c", response_model=TestMCP1CResponse, status_code=status.HTTP_200_OK)
async def test_mcp_1c(
    current_user: dict = Depends(get_optional_current_user)
):
    """
    Проверить работу MCP 1С - получить одного контрагента из 1С
    
    Тестирует подключение к MCP сервису и получение данных из 1С.
    """
    try:
        username = current_user.get("username") if current_user else "anonymous"
        logger.info("Testing MCP 1C connection", user=username)
        
        # Получаем URL MCP сервиса из настроек
        from app.config import settings
        mcp_service_url = settings.MCP_SERVICE_URL
        timeout = 30
        
        # Выполняем запрос к MCP сервису для получения одного контрагента
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{mcp_service_url}/command",
                json={
                    "command": "get_one_counterparty",
                    "params": {}
                },
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    response_data = await response.json()
                    if response_data.get("status") == "success":
                        result = response_data.get("result", {})
                        if result.get("found"):
                            counterparty_data = result.get("data", {})
                            counterparty_data["uuid"] = result.get("uuid")
                            logger.info("MCP 1C test successful", 
                                      counterparty_uuid=result.get("uuid"),
                                      user=username)
                            return TestMCP1CResponse(
                                success=True,
                                message="Успешно получен контрагент из 1С",
                                counterparty=counterparty_data
                            )
                        else:
                            logger.warning("MCP 1C test: no counterparties found", user=username)
                            return TestMCP1CResponse(
                                success=True,
                                message="Подключение к 1С успешно, но контрагенты не найдены",
                                counterparty=None
                            )
                    else:
                        error_msg = response_data.get("error", "Unknown error")
                        logger.error("MCP 1C test failed", error=error_msg, user=username)
                        return TestMCP1CResponse(
                            success=False,
                            message="Ошибка при выполнении команды MCP",
                            error=error_msg
                        )
                else:
                    error_text = await response.text()
                    logger.error("MCP 1C test failed", 
                               status=response.status,
                               error=error_text,
                               user=username)
                    return TestMCP1CResponse(
                        success=False,
                        message=f"Ошибка подключения к MCP сервису (статус {response.status})",
                        error=error_text
                    )
    
    except aiohttp.ClientError as e:
        logger.error("MCP 1C test connection error", error=str(e), user=username if 'username' in locals() else "anonymous")
        return TestMCP1CResponse(
            success=False,
            message="Ошибка подключения к MCP сервису",
            error=str(e)
        )
    except Exception as e:
        logger.error("MCP 1C test failed", error=str(e), user=username if 'username' in locals() else "anonymous")
        return TestMCP1CResponse(
            success=False,
            message="Неожиданная ошибка при тестировании MCP 1С",
            error=str(e)
        )
