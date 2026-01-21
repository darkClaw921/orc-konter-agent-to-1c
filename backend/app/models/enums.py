"""
Перечисления для моделей данных
"""
from enum import Enum


class ProcessingState(str, Enum):
    """Состояния обработки контракта"""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    DOCUMENT_LOADED = "document_loaded"
    TEXT_EXTRACTED = "text_extracted"
    DATA_EXTRACTED = "data_extracted"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    CHECKING_1C = "checking_1c"
    CREATING_IN_1C = "creating_in_1c"
    COMPLETED = "completed"
    FAILED = "failed"


class LegalEntityType(str, Enum):
    """Тип юридического лица"""
    LEGAL = "Юридическое лицо"
    INDIVIDUAL = "Физическое лицо"


class GovComType(str, Enum):
    """Тип организации (государственная/коммерческая)"""
    GOVERNMENT = "Государственное"
    COMMERCIAL = "Коммерческое"


class VATType(str, Enum):
    """Тип НДС"""
    WITHOUT = "Без НДС"
    INCLUDED = "Включен в цену"
    ADDITIONAL = "Добавляется"


class Role(str, Enum):
    """Роль контрагента в договоре"""
    SUPPLIER = "Поставщик"
    BUYER = "Покупатель"
    BOTH = "Поставщик и Покупатель"


class EventStatus(str, Enum):
    """Статус события обработки"""
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class OneCStatus(str, Enum):
    """Статус интеграции с 1С"""
    CREATED = "created"
    UPDATED = "updated"
    ERROR = "error"
