"""
Управление состоянием агента
"""
import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

from app.models.enums import ProcessingState
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AgentState:
    """Состояние обработки контракта"""
    contract_id: int
    status: ProcessingState
    document_path: str
    raw_text: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    validation_errors: Optional[list] = None
    existing_counterparty_id: Optional[str] = None
    created_counterparty_id: Optional[str] = None
    created_agreement_id: Optional[str] = None
    counterparty_inn_source: Optional[str] = None  # Источник ИНН: 'root', 'customer', 'contractor'
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    llm_requests: Optional[list] = None  # Список запросов и ответов LLM
    
    def to_dict(self) -> Dict[str, Any]:
        """Сериализовать в словарь"""
        data = asdict(self)
        data['status'] = self.status.value
        return data
    
    def to_json(self) -> str:
        """Сериализовать в JSON"""
        return json.dumps(self.to_dict(), default=str, ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentState':
        """Десериализовать из словаря"""
        if isinstance(data.get('status'), str):
            data['status'] = ProcessingState(data['status'])
        return cls(**data)


class StateManager:
    """Менеджер состояния агента"""
    
    def __init__(self, redis_client=None, db_session=None):
        self.redis = redis_client
        self.db = db_session
    
    async def save_state(self, state: AgentState) -> bool:
        """Сохранить состояние"""
        try:
            if self.redis:
                key = f"agent:state:{state.contract_id}"
                await self.redis.set(key, state.to_json(), ex=86400)  # 24 часа
            
            logger.info("State saved", contract_id=state.contract_id, status=state.status.value)
            return True
        except Exception as e:
            logger.error("Failed to save state", error=str(e))
            return False
    
    async def load_state(self, contract_id: int) -> Optional[AgentState]:
        """Загрузить состояние"""
        try:
            if self.redis:
                key = f"agent:state:{contract_id}"
                state_json = await self.redis.get(key)
                if state_json:
                    if isinstance(state_json, bytes):
                        state_json = state_json.decode('utf-8')
                    state_dict = json.loads(state_json)
                    return AgentState.from_dict(state_dict)
            return None
        except Exception as e:
            logger.error("Failed to load state", error=str(e))
            return None
    
    async def update_status(self, contract_id: int, status: ProcessingState, **kwargs):
        """Обновить статус"""
        state = await self.load_state(contract_id)
        if not state:
            state = AgentState(contract_id=contract_id, status=status, document_path="")
        
        state.status = status
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
        
        await self.save_state(state)
