"""
Настройка трассировки с OpenTelemetry и Jaeger
"""
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from app.config import settings


def configure_tracing(service_name: str = "sgr-agent-backend", jaeger_host: str = "localhost", jaeger_port: int = 14268) -> None:
    """
    Настройка OpenTelemetry трассировки с экспортом в Jaeger
    
    Args:
        service_name: Имя сервиса для трассировки
        jaeger_host: Хост Jaeger
        jaeger_port: Порт Jaeger HTTP collector
    """
    # Создание ресурса с информацией о сервисе
    resource = Resource.create({
        "service.name": service_name,
        "service.version": settings.APP_VERSION,
    })
    
    # Настройка провайдера трассировки
    trace.set_tracer_provider(TracerProvider(resource=resource))
    
    # Настройка экспорта в Jaeger
    jaeger_exporter = JaegerExporter(
        agent_host_name=jaeger_host,
        agent_port=jaeger_port,
    )
    
    # Добавление процессора для батчинга spans
    span_processor = BatchSpanProcessor(jaeger_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)
    
    # Инструментация FastAPI
    FastAPIInstrumentor().instrument()
    
    # Инструментация SQLAlchemy
    SQLAlchemyInstrumentor().instrument()
    
    # Инструментация HTTPX
    HTTPXClientInstrumentor().instrument()


def get_tracer(name: str) -> trace.Tracer:
    """
    Получить tracer для модуля
    
    Args:
        name: Имя модуля (обычно __name__)
        
    Returns:
        Tracer для создания spans
    """
    return trace.get_tracer(name)


def create_span(tracer: trace.Tracer, span_name: str, attributes: Optional[dict] = None):
    """
    Контекстный менеджер для создания span
    
    Args:
        tracer: Tracer для создания span
        span_name: Имя span
        attributes: Атрибуты span
        
    Returns:
        Context manager для span
    """
    span = tracer.start_span(span_name)
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    return span
