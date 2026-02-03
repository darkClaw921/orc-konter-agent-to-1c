import React from 'react';

const DataViewer = ({ data, title = 'Данные' }) => {
  if (!data) {
    return (
      <div className="text-gray-500 text-center py-8">
        Данные отсутствуют
      </div>
    );
  }

  // Маппинг английских названий полей на русские
  const fieldTranslations = {
    contract_id: 'ID контракта',
    inn: 'ИНН',
    kpp: 'КПП',
    legal_entity_type: 'Тип юридического лица',
    full_name: 'Полное наименование',
    short_name: 'Краткое наименование',
    organizational_form: 'Организационно-правовая форма',
    is_supplier: 'Поставщик',
    is_buyer: 'Покупатель',
    customer: 'Заказчик',
    contractor: 'Исполнитель',
    contract_name: 'Наименование договора',
    contract_number: 'Номер договора',
    contract_date: 'Дата договора',
    contract_price: 'Цена договора',
    vat_percent: 'Процент НДС',
    vat_type: 'Тип НДС',
    service_description: 'Описание услуг/товаров',
    service_start_date: 'Начало периода услуг',
    service_end_date: 'Окончание периода услуг',
    locations: 'Адреса оказания услуг',
    responsible_persons: 'Ответственные лица',
    extraction_confidence: 'Уверенность в извлечении',
    payment_terms: 'Условия оплаты',
    specification_exists: 'Наличие спецификации',
    pricing_method: 'Порядок ценообразования',
    acceptance_procedure: 'Порядок приема-сдачи',
    reporting_forms: 'Формы отчетности',
    additional_conditions: 'Дополнительные условия',
    technical_info: 'Техническая информация',
    services: 'Услуги по договору',
    // Поля для услуг
    unit: 'Единица измерения',
    quantity: 'Количество',
    unit_price: 'Цена за единицу',
    total_price: 'Общая стоимость',
    // Поля для ответственных лиц
    name: 'ФИО',
    email: 'Email',
    phone: 'Телефон',
    position: 'Должность',
    // Поля для адресов
    address: 'Адрес',
    city: 'Город',
    region: 'Регион',
    postal_code: 'Почтовый индекс',
    responsible_person: 'Ответственное лицо',
    directions: 'Как добраться',
  };

  const translateField = (key) => {
    return fieldTranslations[key] || key.replace(/_/g, ' ');
  };

  const formatValue = (value, key = null) => {
    if (value === null || value === undefined) {
      return <span className="text-gray-400">—</span>;
    }
    if (typeof value === 'boolean') {
      return value ? 'Да' : 'Нет';
    }
    if (Array.isArray(value)) {
      return (
        <ul className="list-disc list-inside space-y-1">
          {value.map((item, index) => (
            <li key={index} className="break-words">
              {typeof item === 'object' ? (
                <pre className="text-sm bg-gray-50 p-2 rounded overflow-auto max-w-full whitespace-pre-wrap break-words">
                  {JSON.stringify(item, null, 2)}
                </pre>
              ) : (
                <span className="break-words">{String(item)}</span>
              )}
            </li>
          ))}
        </ul>
      );
    }
    if (typeof value === 'object') {
      return (
        <pre className="text-sm bg-gray-50 p-2 rounded overflow-auto max-w-full whitespace-pre-wrap break-words">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }
    
    // Форматирование дат
    if (key && (key.includes('date') || key.includes('Date'))) {
      try {
        const date = new Date(value);
        if (!isNaN(date.getTime())) {
          return date.toLocaleDateString('ru-RU');
        }
      } catch (e) {
        // Если не удалось распарсить дату, возвращаем как есть
      }
    }
    
    // Форматирование цен
    if (key && (key.includes('price') || key.includes('Price'))) {
      if (typeof value === 'number' || (typeof value === 'string' && !isNaN(parseFloat(value)))) {
        return `${parseFloat(value).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`;
      }
    }
    
    // Форматирование процентов
    if (key && (key.includes('percent') || key.includes('Percent') || key.includes('confidence'))) {
      if (typeof value === 'number' || (typeof value === 'string' && !isNaN(parseFloat(value)))) {
        const numValue = parseFloat(value);
        if (key.includes('confidence')) {
          return `${(numValue * 100).toFixed(2)}%`;
        }
        return `${numValue.toFixed(2)}%`;
      }
    }
    
    // Для длинных строк добавляем переносы
    const stringValue = String(value);
    if (stringValue.length > 100) {
      return (
        <div className="break-words whitespace-pre-wrap">
          {stringValue}
        </div>
      );
    }
    
    return <span className="break-words">{stringValue}</span>;
  };

  const renderResponsiblePersons = (persons) => {
    if (!Array.isArray(persons) || persons.length === 0) {
      return <span className="text-gray-400">—</span>;
    }

    return (
      <div className="space-y-4">
        {persons.map((person, index) => (
          <div key={index} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
            {person.name && (
              <div className="mb-2">
                <span className="text-sm font-medium text-gray-600">ФИО:</span>
                <span className="ml-2 text-gray-900">{person.name}</span>
              </div>
            )}
            {person.position && (
              <div className="mb-2">
                <span className="text-sm font-medium text-gray-600">Должность:</span>
                <span className="ml-2 text-gray-900">{person.position}</span>
              </div>
            )}
            {person.email && (
              <div className="mb-2">
                <span className="text-sm font-medium text-gray-600">Email:</span>
                <span className="ml-2 text-gray-900">{person.email}</span>
              </div>
            )}
            {person.phone && (
              <div>
                <span className="text-sm font-medium text-gray-600">Телефон:</span>
                <span className="ml-2 text-gray-900">{person.phone}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderLocations = (locations) => {
    if (!Array.isArray(locations) || locations.length === 0) {
      return <span className="text-gray-400">—</span>;
    }

    return (
      <div className="space-y-4">
        {locations.map((location, index) => (
          <div key={index} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
            {location.address && (
              <div className="mb-2">
                <span className="text-sm font-medium text-gray-600">Адрес:</span>
                <span className="ml-2 text-gray-900">{location.address}</span>
              </div>
            )}
            {location.directions && (
              <div className="mb-2">
                <span className="text-sm font-medium text-gray-600">Как добраться:</span>
                <span className="ml-2 text-gray-900">{location.directions}</span>
              </div>
            )}
            {location.responsible_person && typeof location.responsible_person === 'object' && (
              <div className="mt-3 pt-3 border-t border-gray-300">
                <span className="text-sm font-medium text-gray-600 mb-2 block">Ответственное лицо:</span>
                {location.responsible_person.name && (
                  <div className="mb-1">
                    <span className="text-sm text-gray-600">ФИО:</span>
                    <span className="ml-2 text-gray-900">{location.responsible_person.name}</span>
                  </div>
                )}
                {location.responsible_person.position && (
                  <div className="mb-1">
                    <span className="text-sm text-gray-600">Должность:</span>
                    <span className="ml-2 text-gray-900">{location.responsible_person.position}</span>
                  </div>
                )}
                {location.responsible_person.phone && (
                  <div className="mb-1">
                    <span className="text-sm text-gray-600">Телефон:</span>
                    <span className="ml-2 text-gray-900">{location.responsible_person.phone}</span>
                  </div>
                )}
                {location.responsible_person.email && (
                  <div>
                    <span className="text-sm text-gray-600">Email:</span>
                    <span className="ml-2 text-gray-900">{location.responsible_person.email}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderServices = (services) => {
    if (!Array.isArray(services) || services.length === 0) {
      return <span className="text-gray-400">—</span>;
    }

    return (
      <div className="space-y-4">
        {services.map((service, index) => (
          <div key={index} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
            <div className="font-semibold text-gray-700 mb-3">
              Услуга {index + 1}
            </div>
            <div className="space-y-2">
              {service.name && (
                <div>
                  <span className="text-sm font-medium text-gray-600">Наименование:</span>
                  <div className="ml-2 text-gray-900 break-words whitespace-pre-wrap mt-1">
                    {service.name}
                  </div>
                </div>
              )}
              {service.description && (
                <div>
                  <span className="text-sm font-medium text-gray-600">Описание:</span>
                  <div className="ml-2 text-gray-900 break-words whitespace-pre-wrap mt-1">
                    {service.description}
                  </div>
                </div>
              )}
              {(service.quantity !== null && service.quantity !== undefined) && (
                <div>
                  <span className="text-sm font-medium text-gray-600">Количество:</span>
                  <span className="ml-2 text-gray-900">
                    {service.quantity} {service.unit || ''}
                  </span>
                </div>
              )}
              {service.unit_price !== null && service.unit_price !== undefined && (
                <div>
                  <span className="text-sm font-medium text-gray-600">Цена за единицу:</span>
                  <span className="ml-2 text-gray-900">
                    {typeof service.unit_price === 'number' 
                      ? `${service.unit_price.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`
                      : service.unit_price}
                  </span>
                </div>
              )}
              {service.total_price !== null && service.total_price !== undefined && (
                <div>
                  <span className="text-sm font-medium text-gray-600">Общая стоимость:</span>
                  <span className="ml-2 text-gray-900">
                    {typeof service.total_price === 'number'
                      ? `${service.total_price.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₽`
                      : service.total_price}
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderCounterparty = (counterparty, title) => {
    if (!counterparty || typeof counterparty !== 'object') {
      return null;
    }

    return (
      <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
        <h4 className="font-semibold text-gray-700 mb-3">{title}</h4>
        <div className="space-y-2">
          {counterparty.full_name && (
            <div>
              <span className="text-sm font-medium text-gray-600">Полное наименование:</span>
              <span className="ml-2 text-gray-900">{counterparty.full_name}</span>
            </div>
          )}
          {counterparty.short_name && (
            <div>
              <span className="text-sm font-medium text-gray-600">Краткое наименование:</span>
              <span className="ml-2 text-gray-900">{counterparty.short_name}</span>
            </div>
          )}
          {counterparty.inn && (
            <div>
              <span className="text-sm font-medium text-gray-600">ИНН:</span>
              <span className="ml-2 text-gray-900">{counterparty.inn}</span>
            </div>
          )}
          {counterparty.kpp && (
            <div>
              <span className="text-sm font-medium text-gray-600">КПП:</span>
              <span className="ml-2 text-gray-900">{counterparty.kpp}</span>
            </div>
          )}
          {counterparty.organizational_form && (
            <div>
              <span className="text-sm font-medium text-gray-600">ОПФ:</span>
              <span className="ml-2 text-gray-900">{counterparty.organizational_form}</span>
            </div>
          )}
          {counterparty.legal_entity_type && (
            <div>
              <span className="text-sm font-medium text-gray-600">Тип юридического лица:</span>
              <span className="ml-2 text-gray-900">{counterparty.legal_entity_type}</span>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderField = (key, value, level = 0, allData = null) => {
    if (value === null || value === undefined) {
      return null;
    }

    // Специальная обработка для customer - показываем информацию о заказчике
    if (key === 'customer' && typeof value === 'object') {
      return (
        <div
          key="customer"
          className={`py-2 border-b border-gray-100 ${level > 0 ? 'ml-4' : ''}`}
        >
          <div className="flex flex-col">
            <span className="font-medium text-gray-600 mb-2">
              {translateField(key)}:
            </span>
            <div className="text-gray-900">
              {renderCounterparty(value, 'Заказчик')}
            </div>
          </div>
        </div>
      );
    }

    // Специальная обработка для contractor - показываем информацию об исполнителе
    if (key === 'contractor' && typeof value === 'object') {
      return (
        <div
          key="contractor"
          className={`py-2 border-b border-gray-100 ${level > 0 ? 'ml-4' : ''}`}
        >
          <div className="flex flex-col">
            <span className="font-medium text-gray-600 mb-2">
              {translateField(key)}:
            </span>
            <div className="text-gray-900">
              {renderCounterparty(value, 'Исполнитель')}
            </div>
          </div>
        </div>
      );
    }

    // Пропускаем is_supplier и is_buyer (они заменены на customer и contractor)
    if (key === 'is_supplier' || key === 'is_buyer') {
      return null;
    }

    // Специальная обработка для responsible_persons
    if (key === 'responsible_persons' && Array.isArray(value)) {
      return (
        <div
          key={key}
          className={`py-2 border-b border-gray-100 ${level > 0 ? 'ml-4' : ''}`}
        >
          <div className="flex flex-col">
            <span className="font-medium text-gray-600 mb-2">
              {translateField(key)}:
            </span>
            <div className="text-gray-900">
              {renderResponsiblePersons(value)}
            </div>
          </div>
        </div>
      );
    }

    // Специальная обработка для locations (адреса оказания услуг)
    if ((key === 'locations' || key === 'service_locations') && Array.isArray(value)) {
      return (
        <div
          key={key}
          className={`py-2 border-b border-gray-100 ${level > 0 ? 'ml-4' : ''}`}
        >
          <div className="flex flex-col">
            <span className="font-medium text-gray-600 mb-2">
              {translateField(key)}:
            </span>
            <div className="text-gray-900">
              {renderLocations(value)}
            </div>
          </div>
        </div>
      );
    }

    // Специальная обработка для services (услуги по договору)
    if (key === 'services' && Array.isArray(value)) {
      return (
        <div
          key={key}
          className={`py-2 border-b border-gray-100 ${level > 0 ? 'ml-4' : ''}`}
        >
          <div className="flex flex-col">
            <span className="font-medium text-gray-600 mb-2">
              {translateField(key)}:
            </span>
            <div className="text-gray-900">
              {renderServices(value)}
            </div>
          </div>
        </div>
      );
    }

    if (typeof value === 'object' && !Array.isArray(value)) {
      return (
        <div key={key} className={level > 0 ? 'ml-4 mt-2' : ''}>
          <h4 className="font-semibold text-gray-700 mb-2">
            {translateField(key)}
          </h4>
          <div className="space-y-2">
            {Object.entries(value).map(([subKey, subValue]) =>
              renderField(subKey, subValue, level + 1, value)
            )}
          </div>
        </div>
      );
    }

    return (
      <div
        key={key}
        className={`py-2 border-b border-gray-100 ${level > 0 ? 'ml-4' : ''}`}
      >
        <div className="flex justify-between items-start gap-4">
          <span className="font-medium text-gray-600 min-w-[200px] flex-shrink-0">
            {translateField(key)}:
          </span>
          <div className="text-gray-900 flex-1 min-w-0 break-words">
            {formatValue(value, key)}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
      </div>
      <div className="p-6">
        {typeof data === 'object' ? (
          <div className="space-y-2">
            {Object.entries(data).map(([key, value]) =>
              renderField(key, value, 0, data)
            )}
          </div>
        ) : (
          <div>{formatValue(data)}</div>
        )}
      </div>
    </div>
  );
};

export default DataViewer;
