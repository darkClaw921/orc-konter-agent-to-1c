"""
Конфигурация приложения
"""
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Application
    APP_NAME: str = "SGR Agent 1C Counterparty"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/sgr_agent_db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Security
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # LLM Configuration
    LLM_PROVIDER: Literal["openai", "yandex", "ollama"] = "openai"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4000
    LLM_REQUEST_TIMEOUT: int = 60
    
    # Storage
    STORAGE_TYPE: Literal["local", "minio"] = "local"
    STORAGE_PATH: str = "./storage/contracts"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    
    # MCP Service
    MCP_SERVICE_URL: str = "http://localhost:9000"
    
    # 1C Integration
    ONEС_ODATA_URL: str = ""
    ONEС_USERNAME: str = ""
    ONEС_PASSWORD: str = ""
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./storage/logs/app.log"
    
    # Validation
    VALIDATION_ENABLED: bool = True
    VALIDATION_STRICT_MODE: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
