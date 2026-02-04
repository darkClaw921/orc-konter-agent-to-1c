"""
Утилиты для работы с JSON и сериализацией данных
"""
from decimal import Decimal
from typing import Any


def convert_decimal_for_jsonb(obj: Any) -> Any:
    """
    Рекурсивно преобразует Decimal значения в float для JSON-сериализации.
    Используется перед сохранением данных в JSONB поля БД.
    
    Args:
        obj: Объект для преобразования (может быть dict, list, Decimal, или другой тип)
        
    Returns:
        JSON-совместимый объект с Decimal преобразованными в float
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: convert_decimal_for_jsonb(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal_for_jsonb(item) for item in obj]
    else:
        return obj
