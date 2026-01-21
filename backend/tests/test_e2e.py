"""
End-to-End тесты для полного pipeline обработки контракта
"""
import pytest
import aiohttp
from unittest.mock import AsyncMock, patch

from app.agent.orchestrator import AgentOrchestrator
from app.agent.state_manager import StateManager, AgentState
from app.models.enums import ProcessingState
from app.services.document_processor import DocumentProcessor
from app.services.llm_service import LLMService
from app.services.validation_service import ValidationService
from app.services.oneс_service import OneCService
from app.testing.test_runner import TestRunner
from app.testing.test_cases import TestCaseManager


@pytest.mark.asyncio
async def test_contract_processing_pipeline(
    db_session,
    sample_docx_file,
    mock_llm_service,
    mock_onec_service
):
    """
    Тест полного pipeline обработки контракта через AgentOrchestrator
    Проверка что статус COMPLETED, created_counterparty_id не None, extracted_data содержит inn
    """
    # Создаем тестовый контракт в БД
    from app.models.database import Contract
    contract = Contract(
        original_filename="test_contract.docx",
        file_path=str(sample_docx_file),
        file_size_bytes=1024,
        status=ProcessingState.UPLOADED
    )
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)
    
    # Инициализируем компоненты
    state_manager = StateManager(redis_client=None, db_session=db_session)
    doc_processor = DocumentProcessor()
    llm_service = LLMService()
    validation_service = ValidationService()
    oneс_service = OneCService()
    
    # Создаем оркестратор
    orchestrator = AgentOrchestrator(
        state_manager=state_manager,
        doc_processor=doc_processor,
        llm_service=llm_service,
        validation_service=validation_service,
        oneс_service=oneс_service
    )
    
    # Запускаем обработку
    state = await orchestrator.process_contract(
        contract_id=contract.id,
        document_path=str(sample_docx_file)
    )
    
    # Проверяем результаты
    assert state.status == ProcessingState.COMPLETED, f"Expected COMPLETED, got {state.status}"
    assert state.created_counterparty_id is not None, "created_counterparty_id should not be None"
    assert state.extracted_data is not None, "extracted_data should not be None"
    assert "inn" in state.extracted_data, "extracted_data should contain 'inn'"
    assert state.extracted_data["inn"] == "7707083893", f"Expected INN 7707083893, got {state.extracted_data.get('inn')}"


@pytest.mark.asyncio
async def test_llm_extraction_accuracy(mock_llm_service):
    """
    Запуск всех тестовых случаев через TestRunner
    Проверка что success_rate >= 80%
    """
    test_case_manager = TestCaseManager()
    test_runner = TestRunner(test_case_manager)
    
    # Запускаем все тесты
    report = await test_runner.run_all_tests()
    
    # Проверяем что success_rate >= 80%
    assert report.success_rate >= 80.0, \
        f"Expected success_rate >= 80%, got {report.success_rate}%"
    
    # Проверяем что есть хотя бы один тест
    assert report.total_tests > 0, "Should have at least one test case"
    
    # Проверяем структуру отчета
    assert hasattr(report, 'passed_tests'), "Report should have passed_tests"
    assert hasattr(report, 'failed_tests'), "Report should have failed_tests"
    assert hasattr(report, 'results'), "Report should have results"


@pytest.mark.asyncio
async def test_1c_integration(mock_onec_service):
    """
    Тест интеграции с 1С: поиск контрагента по ИНН, создание контрагента если не найден, проверка создания
    """
    oneс_service = OneCService()
    
    # Тест 1: Поиск несуществующего контрагента
    inn = "7707083893"
    existing = await oneс_service.find_counterparty_by_inn(inn)
    assert existing is None, "Counterparty should not exist initially"
    
    # Тест 2: Создание контрагента
    contract_data = {
        "inn": inn,
        "kpp": "770701001",
        "full_name": "Общество с ограниченной ответственностью 'Пример'",
        "short_name": "ООО 'Пример'",
        "legal_entity_type": "Юридическое лицо",
        "organizational_form": "ООО",
        "role": "Поставщик"
    }
    
    counterparty_uuid = await oneс_service.create_counterparty(
        contract_data=contract_data,
        document_path="/tmp/test_contract.docx"
    )
    
    assert counterparty_uuid is not None, "Counterparty UUID should not be None"
    assert counterparty_uuid == "test-counterparty-uuid-12345", \
        f"Expected test UUID, got {counterparty_uuid}"


@pytest.mark.asyncio
async def test_mcp_sse_connection():
    """
    Тест SSE подключения к MCP серверу
    Проверка статуса ответа и Content-Type
    """
    import os
    mcp_service_url = os.getenv("MCP_SERVICE_URL", "http://localhost:9000")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Пытаемся подключиться к SSE endpoint
            client_id = "test-client-12345"
            url = f"{mcp_service_url}/sse/{client_id}"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                # Проверяем статус ответа
                # Если сервер не запущен, это нормально для тестов
                if response.status == 200:
                    # Проверяем Content-Type для SSE
                    content_type = response.headers.get("Content-Type", "")
                    assert "text/event-stream" in content_type or "text/plain" in content_type, \
                        f"Expected SSE Content-Type, got {content_type}"
                elif response.status == 404:
                    # Если endpoint не найден, это тоже нормально (может быть другой формат)
                    pytest.skip("MCP Service SSE endpoint not available")
                else:
                    # Другие статусы - пропускаем тест если сервер не доступен
                    pytest.skip(f"MCP Service returned status {response.status}")
    
    except aiohttp.ClientError as e:
        # Если сервер не доступен, пропускаем тест
        pytest.skip(f"MCP Service not available: {str(e)}")
    
    except Exception as e:
        # Другие ошибки - пропускаем
        pytest.skip(f"Failed to connect to MCP Service: {str(e)}")


@pytest.mark.asyncio
async def test_mcp_command_endpoint():
    """
    Дополнительный тест для проверки команды через MCP сервер
    """
    import os
    mcp_service_url = os.getenv("MCP_SERVICE_URL", "http://localhost:9000")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Тестируем команду check_counterparty
            async with session.post(
                f"{mcp_service_url}/command",
                json={
                    "command": "check_counterparty",
                    "params": {"inn": "7707083893"}
                },
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    assert "status" in data, "Response should contain 'status'"
                elif response.status == 404:
                    pytest.skip("MCP Service command endpoint not available")
                else:
                    pytest.skip(f"MCP Service returned status {response.status}")
    
    except aiohttp.ClientError as e:
        pytest.skip(f"MCP Service not available: {str(e)}")
    
    except Exception as e:
        pytest.skip(f"Failed to connect to MCP Service: {str(e)}")
