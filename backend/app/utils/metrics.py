"""
Настройка метрик Prometheus
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# Метрики для обработки контрактов
contract_processing_duration = Histogram(
    'sgr_agent_contract_processing_duration_seconds',
    'Время обработки контракта в секундах',
    ['status']
)

contract_processing_total = Counter(
    'sgr_agent_contract_processing_total',
    'Общее количество обработанных контрактов',
    ['status']
)

contract_validation_failures = Counter(
    'sgr_agent_contract_validation_failures_total',
    'Количество ошибок валидации контрактов',
    ['error_type']
)

# Метрики для LLM API
llm_api_calls_total = Counter(
    'sgr_agent_llm_api_calls_total',
    'Общее количество вызовов LLM API',
    ['provider', 'status']
)

llm_api_duration = Histogram(
    'sgr_agent_llm_api_duration_seconds',
    'Время выполнения запроса к LLM API',
    ['provider']
)

# Метрики для 1С интеграции
onec_api_calls_total = Counter(
    'sgr_agent_1c_api_calls_total',
    'Общее количество вызовов 1С API',
    ['operation', 'status']
)

onec_api_duration = Histogram(
    'sgr_agent_1c_api_duration_seconds',
    'Время выполнения запроса к 1С API',
    ['operation']
)

# Метрики для очереди задач
queue_length = Gauge(
    'sgr_agent_queue_length',
    'Текущая длина очереди задач'
)

# Метрики для API
api_response_time = Histogram(
    'sgr_agent_api_response_time_seconds',
    'Время отклика API',
    ['method', 'endpoint', 'status_code']
)

api_requests_total = Counter(
    'sgr_agent_api_requests_total',
    'Общее количество запросов к API',
    ['method', 'endpoint', 'status_code']
)


def get_metrics_response() -> Response:
    """Получить метрики в формате Prometheus"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
