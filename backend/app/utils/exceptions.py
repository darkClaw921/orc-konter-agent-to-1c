"""
Кастомные исключения
"""


class SGRAgentException(Exception):
    """Базовое исключение для SGR Agent"""
    def __init__(self, message: str, error_code: str = "UNKNOWN"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DocumentProcessingError(SGRAgentException):
    """Ошибка обработки документа"""
    pass


class LLMServiceError(SGRAgentException):
    """Ошибка LLM сервиса"""
    pass


class ValidationError(SGRAgentException):
    """Ошибка валидации данных"""
    pass


class OneCServiceError(SGRAgentException):
    """Ошибка интеграции с 1С"""
    pass


class StorageError(SGRAgentException):
    """Ошибка хранилища файлов"""
    pass
