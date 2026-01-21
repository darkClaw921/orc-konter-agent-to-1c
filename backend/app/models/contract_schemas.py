"""
Pydantic схемы для валидации контрактов
"""
import re
from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import LegalEntityType, Role


class ResponsiblePerson(BaseModel):
    """Ответственное лицо"""
    name: str = Field(..., description="ФИО ответственного лица")
    phone: Optional[str] = Field(None, description="Телефон")
    email: Optional[str] = Field(None, description="Email")
    position: Optional[str] = Field(None, description="Должность")


class CounterpartyInfo(BaseModel):
    """Информация о контрагенте"""
    inn: str = Field(..., min_length=10, max_length=12, description="ИНН контрагента")
    kpp: Optional[str] = Field(None, min_length=9, max_length=9, description="КПП (только для ЮЛ)")
    full_name: str = Field(..., min_length=5, description="Полное наименование с ОПФ")
    short_name: Optional[str] = Field(None, min_length=3, description="Краткое наименование без ОПФ")
    organizational_form: Optional[str] = Field(None, description="ОПФ (ООО, АО, ИП и т.д.)")
    legal_entity_type: LegalEntityType = Field(..., description="Тип юр.лица")


class ServiceLocation(BaseModel):
    """Адрес оказания услуг"""
    address: str = Field(..., description="Полный адрес")
    responsible_person: Optional[ResponsiblePerson] = Field(None, description="Ответственное лицо на адресе")
    directions: Optional[str] = Field(None, description="Как добраться")


class ContractDataSchema(BaseModel):
    """Главная схема для валидации извлеченных данных контракта"""
    
    # Обязательные поля (могут быть опциональными если есть customer/contractor)
    inn: Optional[str] = Field(None, min_length=10, max_length=12, description="ИНН контрагента")
    full_name: Optional[str] = Field(None, min_length=5, description="Полное наименование с ОПФ")
    short_name: Optional[str] = Field(None, min_length=3, description="Краткое наименование без ОПФ")
    organizational_form: Optional[str] = Field(None, description="ОПФ (ООО, АО, ИП и т.д.)")
    legal_entity_type: Optional[LegalEntityType] = Field(None, description="Тип юр.лица")
    role: Optional[Role] = Field(None, description="Роль контрагента в договоре")
    
    # Опциональные поля
    kpp: Optional[str] = Field(None, min_length=9, max_length=9, description="КПП (только для ЮЛ)")
    contract_name: Optional[str] = Field(None, description="Наименование договора")
    contract_number: Optional[str] = Field(None, description="Номер договора")
    contract_date: Optional[date] = Field(None, description="Дата договора")
    contract_price: Optional[Decimal] = Field(None, gt=0, description="Цена договора")
    vat_percent: Optional[Decimal] = Field(None, ge=0, le=100, description="Процент НДС")
    vat_type: Optional[str] = Field(None, description="Тип НДС: Без НДС, Включен в цену, Добавляется")
    
    # Дополнительные поля
    service_description: Optional[str] = Field(None, description="Описание услуг/товаров")
    service_start_date: Optional[date] = Field(None, description="Начало периода услуг")
    service_end_date: Optional[date] = Field(None, description="Окончание периода услуг")
    service_locations: Optional[List[ServiceLocation]] = Field(None, description="Адреса оказания услуг")
    locations: Optional[List[ServiceLocation]] = Field(None, description="Адреса оказания услуг (алиас для service_locations)")
    responsible_persons: Optional[List[ResponsiblePerson]] = Field(None, description="Ответственные лица")
    # Информация о контрагентах
    customer: Optional[CounterpartyInfo] = Field(None, description="Информация о заказчике (Покупателе)")
    contractor: Optional[CounterpartyInfo] = Field(None, description="Информация об исполнителе (Поставщике)")
    payment_terms: Optional[str] = Field(None, description="Условия оплаты")
    specification_exists: Optional[bool] = Field(None, description="Наличие спецификации")
    pricing_method: Optional[str] = Field(None, description="Порядок ценообразования")
    acceptance_procedure: Optional[str] = Field(None, description="Порядок приема-сдачи")
    reporting_forms: Optional[str] = Field(None, description="Формы отчетности")
    additional_conditions: Optional[str] = Field(None, description="Дополнительные условия")
    technical_info: Optional[str] = Field(None, description="Техническая информация")
    extraction_confidence: Optional[Decimal] = Field(None, ge=0, le=1, description="Уверенность в извлечении данных")
    
    @field_validator('inn')
    @classmethod
    def validate_inn(cls, v: Optional[str]) -> Optional[str]:
        """Валидация формата ИНН"""
        if v is None:
            return None
        
        # Удаляем все нецифровые символы
        inn_clean = re.sub(r'\D', '', str(v))
        
        # Проверяем длину
        if len(inn_clean) not in [10, 12]:
            raise ValueError(f"ИНН должен содержать 10 или 12 цифр, получено {len(inn_clean)}")
        
        # Проверяем что состоит только из цифр
        if not inn_clean.isdigit():
            raise ValueError("ИНН должен содержать только цифры")
        
        return inn_clean
    
    @field_validator('kpp')
    @classmethod
    def validate_kpp(cls, v: Optional[str], info) -> Optional[str]:
        """Валидация формата КПП"""
        if v is None:
            return None
        
        # Удаляем все нецифровые символы
        kpp_clean = re.sub(r'\D', '', str(v))
        
        # Проверяем длину
        if len(kpp_clean) != 9:
            raise ValueError(f"КПП должен содержать 9 цифр, получено {len(kpp_clean)}")
        
        # Проверяем что состоит только из цифр
        if not kpp_clean.isdigit():
            raise ValueError("КПП должен содержать только цифры")
        
        return kpp_clean
    
    @model_validator(mode='after')
    def validate_legal_entity_type(self):
        """Проверка соответствия ИНН и типа юридического лица"""
        # Если ИНН отсутствует в корневых полях, но есть в customer/contractor, пропускаем проверку
        if not self.inn:
            return self
        
        inn_len = len(self.inn)
        
        if inn_len == 10 and self.legal_entity_type == LegalEntityType.INDIVIDUAL:
            raise ValueError("ИНН из 10 цифр соответствует юридическому лицу, а не физическому")
        
        if inn_len == 12 and self.legal_entity_type == LegalEntityType.LEGAL:
            raise ValueError("ИНН из 12 цифр соответствует физическому лицу, а не юридическому")
        
        return self
    
    @model_validator(mode='after')
    def validate_kpp_required(self):
        """Проверка обязательности КПП для юридических лиц"""
        # Если ИНН отсутствует в корневых полях, но есть в customer/contractor, пропускаем проверку
        if not self.inn:
            return self
        
        if self.legal_entity_type == LegalEntityType.LEGAL and len(self.inn) == 10:
            if not self.kpp:
                raise ValueError("КПП обязателен для юридических лиц (10-значный ИНН)")
        
        if len(self.inn) == 12 and self.kpp:
            raise ValueError("КПП не должен присутствовать для физических лиц (12-значный ИНН)")
        
        return self
    
    @model_validator(mode='after')
    def validate_dates(self):
        """Валидация логики дат"""
        # Проверка даты начала услуг не раньше даты договора
        if self.contract_date and self.service_start_date:
            if self.service_start_date < self.contract_date:
                raise ValueError("Дата начала услуг не может быть раньше даты договора")
        
        # Проверка даты окончания не раньше даты начала
        if self.service_start_date and self.service_end_date:
            if self.service_end_date < self.service_start_date:
                raise ValueError("Дата окончания услуг не может быть раньше даты начала")
        
        return self
    
    @model_validator(mode='after')
    def sync_locations(self):
        """Синхронизация locations и service_locations"""
        # Если указан locations, но не указан service_locations, копируем
        if self.locations and not self.service_locations:
            self.service_locations = self.locations
        # Если указан service_locations, но не указан locations, копируем
        elif self.service_locations and not self.locations:
            self.locations = self.service_locations
        
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "inn": "7707083893",
                "full_name": "Общество с ограниченной ответственностью 'Пример'",
                "short_name": "ООО 'Пример'",
                "organizational_form": "ООО",
                "legal_entity_type": "Юридическое лицо",
                "role": "Поставщик",
                "kpp": "770701001",
                "contract_name": "Договор оказания услуг",
                "contract_number": "123/2024",
                "contract_date": "2024-01-15",
                "contract_price": "1000000.00",
                "vat_percent": "20.00",
                "vat_type": "Добавляется"
            }
        }
