# Архитектура проекта SGR Agent для создания контрагентов в 1С

## Общая структура проекта

Проект состоит из трех основных компонентов, взаимодействующих через REST API и Server-Sent Events:

```
orc-konter-agent-to-1c/
├── backend/              # Backend сервис (Python/FastAPI)
├── frontend/            # Frontend приложение (React/TypeScript)
├── mcp_service/         # MCP сервис для взаимодействия с 1С
├── prometheus/          # Конфигурация Prometheus
├── grafana/             # Grafana дашборды
└── storage/             # Хранилище файлов и логов
```

## Backend структура

### Директории и файлы

```
backend/
├── app/
│   ├── __init__.py                    # Инициализация пакета
│   ├── main.py                        # Точка входа FastAPI приложения
│   ├── config.py                      # Конфигурация приложения (Settings: LLM настройки, MAX_CHUNK_TOKENS, MAX_TABLE_CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS, база данных, Redis, хранилище, 1C интеграция)
│   │
│   ├── core/                          # Ядро приложения
│   │   ├── __init__.py
│   │   ├── security.py                # Аутентификация и авторизация (JWT токены)
│   │   ├── settings.py                # Настройки приложения
│   │   └── dependencies.py            # Зависимости FastAPI (get_current_user)
│   │
│   ├── models/                         # Модели данных
│   │   ├── __init__.py
│   │   ├── database.py                # SQLAlchemy модели (Contract, ContractData, ProcessingHistory, ValidationResult, Counterparty1C)
│   │   ├── schemas.py                 # Pydantic схемы для API (ContractUploadResponse, ContractStatusResponse, ContractDataResponse, ContractRawTextResponse, RefreshServicesResponse, LLMInfoResponse, OneCInfoResponse)
│   │   ├── contract_schemas.py       # Pydantic схемы для валидации контрактов (ContractDataSchema с полями services и all_services, валидаторы validate_inn, validate_kpp, validate_legal_entity_type, validate_kpp_required, validate_dates, sync_locations; ResponsiblePerson, ServiceLocation, Service)
│   │   └── enums.py                   # Перечисления (ProcessingState, LegalEntityType, Role)
│   │
│   ├── api/                           # REST API эндпоинты
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py             # Главный router для API v1
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── contracts.py       # Эндпоинты для работы с контрактами (upload, status, data, list, delete, llm-info, 1c-info, create-in-1c, refresh-services, raw-text; преобразование Decimal в float для JSONB полей через convert_decimal_for_jsonb при сохранении all_services)
│   │           └── testing.py          # Эндпоинты для управления тестами (run-all, run/{id}, cases, validate-extraction, process-contract для повторной обработки уже обработанных документов по contract_id, test-mcp-1c для проверки работы MCP 1С)
│   │
│   ├── services/                      # Бизнес-логика сервисов
│   │   ├── __init__.py
│   │   ├── document_processor.py     # Парсинг DOCX и PDF файлов с использованием docling для извлечения таблиц (ElementType enum, DocumentElement dataclass с is_splittable для таблиц; DocumentProcessor: load_document, extract_text с созданием document_elements[], extract_tables, get_tables_markdown, extract_sections, get_context_for_llm, split_into_chunks с поддержкой разбиения больших таблиц с сохранением заголовков и отдельным лимитом MAX_TABLE_CHUNK_TOKENS для таблиц, get_chunks_for_llm с настройками MAX_CHUNK_TOKENS и MAX_TABLE_CHUNK_TOKENS из config, estimate_tokens, _extract_table_from_docling, _convert_table_to_markdown, _elements_to_text, _get_overlap_elements, _split_large_text, _split_large_table с сохранением заголовков, _extract_table_header_and_rows, _build_elements_from_paragraphs)
│   │   ├── document_validator.py     # Валидация загруженных документов DOCX и PDF (DocumentValidator)
│   │   ├── llm_service.py            # Интеграция с LLM провайдерами с ПАРАЛЛЕЛЬНОЙ обработкой чанков БАТЧАМИ и улучшенной обработкой ошибок соединения с подробным логированием (MAX_CONCURRENT_REQUESTS=3, BATCH_SIZE=50, DEFAULT_RETRY_COUNT=3, CONNECTION_ERROR_RETRY_COUNT=5, asyncio.Semaphore; LLMService: extract_contract_data, validate_extracted_data, aggregate_chunks_data, merge_extracted_data, extract_services_from_chunks (параллельно батчами по 50 через asyncio.gather), extract_contract_data_parallel (параллельно батчами по 50), _extract_services_from_chunk_with_retry, _extract_contract_data_from_chunk_with_retry, _is_connection_error, _calculate_retry_delay с экспоненциальным backoff и jitter; подробное логирование с traceback, временем выполнения, размером данных, типом ошибки, контекстом чанка; BaseLLMProvider: extract_services_only; OpenAIProvider с httpx.Timeout (connect=30s, read=LLM_REQUEST_TIMEOUT=300s, write=60s, pool=10s) для обработки больших документов и обработкой APIConnectionError/APITimeoutError с детальным логированием, YandexGPTProvider)
│   │   ├── prompts.py                # Prompt templates для LLM (EXTRACT_CONTRACT_DATA_PROMPT, VALIDATE_EXTRACTED_DATA_PROMPT, MERGE_CHUNKS_DATA_PROMPT, EXTRACT_SERVICES_ONLY_PROMPT)
│   │   ├── validation_service.py     # Валидация извлеченных данных (ValidationService: validate_contract_data, auto_correct_data, _perform_additional_checks) - улучшенная очистка ИНН от префиксов
│   │   ├── oneс_service.py          # Интеграция с 1С через MCP (OneCService)
│   │   └── storage_service.py        # Управление хранилищем файлов (StorageService: save_uploaded_file, move_to_processed, delete_file)
│   │
│   ├── testing/                       # Система автоматического тестирования
│   │   ├── __init__.py
│   │   ├── test_cases.py             # Хранилище тестовых случаев (TestCase dataclass, TestCaseManager: get_test_case, get_test_cases)
│   │   └── test_runner.py            # Test Runner для запуска тестов (TestRunner: run_test_case, run_all_tests, _compare_results, generate_report; TestResult, TestReport)
│   │
│   ├── agent/                         # SGR Agent Core
│   │   ├── __init__.py
│   │   ├── orchestrator.py           # Оркестрация обработки контракта с ПАРАЛЛЕЛЬНОЙ обработкой чанков БАТЧАМИ и улучшенной обработкой частичных сбоев с подробным логированием (AgentOrchestrator: process_contract, _extract_contract_data с extract_contract_data_parallel (батчи по 50) для извлечения ТОЛЬКО основных данных контракта БЕЗ услуг и обработкой failed_chunks, статистикой успешных/неуспешных чанков, предупреждениями при большом количестве сбоев, детальным логированием ошибок с traceback, контекстом чанков, размерами данных, индексами неуспешных чанков, _extract_all_services с параллельным extract_services_from_chunks (батчи по 50) для извлечения ВСЕХ услуг отдельным запросом в шаге 3.5, _validate_data, _check_counterparty, _create_in_1c, _build_chunk_context БЕЗ секции услуг, _prepare_counterparty_data)
│   │   └── state_manager.py          # Управление состоянием агента (StateManager, AgentState)
│   │
│   ├── tasks/                         # Celery задачи
│   │   ├── __init__.py
│   │   ├── celery_app.py             # Конфигурация Celery
│   │   └── processing_tasks.py       # Асинхронные задачи обработки (process_contract_task с преобразованием Decimal в float для JSONB полей через convert_decimal_for_jsonb)
│   │
│   └── utils/                         # Утилиты
│       ├── __init__.py
│       ├── logging.py                # Настройка логирования (structlog)
│       ├── exceptions.py             # Кастомные исключения (SGRAgentException)
│       ├── metrics.py                # Метрики Prometheus (contract_processing_duration, llm_api_calls_total, etc)
│       ├── tracing.py                # Трассировка OpenTelemetry/Jaeger (configure_tracing, get_tracer)
│       ├── json_utils.py              # Утилиты для работы с JSON (convert_decimal_for_jsonb - рекурсивное преобразование Decimal в float для JSON-сериализации перед сохранением в JSONB поля БД)
│       └── validators.py             # Валидаторы данных
│
├── scripts/                           # Скрипты для БД
│   ├── __init__.py
│   ├── init_db.py                    # Скрипт инициализации БД и применения миграций
│   ├── seed_db.py                    # Скрипт заполнения БД тестовыми данными
│   └── backup_db.py                  # Скрипт резервного копирования БД через pg_dump
│
├── tests/                             # Тесты
│   ├── __init__.py
│   ├── conftest.py                   # Конфигурация и фикстуры для тестов (db_session, client, auth_headers, temp_dir, sample_docx_file, mock_llm_service, mock_onec_service, mock_redis)
│   ├── test_e2e.py                   # End-to-end тесты (test_contract_processing_pipeline, test_llm_extraction_accuracy, test_1c_integration, test_mcp_sse_connection, test_mcp_command_endpoint)
│   ├── test_integration.py           # Интеграционные тесты API (test_contract_upload_endpoint, test_get_contract_status, test_validation_api, test_get_contract_data, test_list_contracts, test_delete_contract)
│   └── test_cases/                   # Тестовые случаи (JSON файлы с TestCase: id, name, description, input_document, expected_output, required_fields, tolerance, tags)
│
├── alembic.ini                        # Конфигурация Alembic
└── migrations/                        # Alembic миграции БД
    ├── env.py                        # Конфигурация окружения Alembic
    ├── script.py.mako                # Шаблон для миграций
    └── versions/                     # Файлы миграций
```

### Взаимодействие компонентов Backend

1. **API Gateway** (`app/main.py`) - принимает HTTP запросы, регистрирует роуты, обрабатывает исключения
2. **REST API Endpoints** (`app/api/v1/endpoints/`) - обрабатывают HTTP запросы, вызывают сервисы
3. **SGR Agent Core** (`app/agent/orchestrator.py`) - оркестрирует процесс обработки контракта:
   - Загружает документ через `DocumentProcessor`
   - **ПАРАЛЛЕЛЬНО БАТЧАМИ** извлекает данные через `LLMService.extract_contract_data_parallel()` - чанки разбиваются на батчи по 50 и обрабатываются параллельно (до 3 параллельных запросов на батч)
   - **ПАРАЛЛЕЛЬНО БАТЧАМИ** извлекает услуги через `LLMService.extract_services_from_chunks()` с `asyncio.gather()` - батчи по 50 чанков
   - Выполняет финальную агрегацию результатов через `aggregate_chunks_data()` с разрешением конфликтов через LLM
   - Валидирует через `ValidationService`
   - Проверяет/создает контрагента через `OneCService`
4. **Services** (`app/services/`) - реализуют бизнес-логику:
   - `DocumentProcessor` - парсит DOCX и PDF файлы с использованием docling для извлечения структурированных данных из таблиц. Создает `document_elements[]` список элементов (TEXT и TABLE) в порядке появления в документе. Разбивает многостраничные документы на чанки (split_into_chunks, get_chunks_for_llm) для обработки через LLM с максимальным размером `MAX_CHUNK_TOKENS` для текста и `MAX_TABLE_CHUNK_TOKENS` для таблиц (по умолчанию 2000 токенов). **Большие таблицы** (превышающие лимит `MAX_TABLE_CHUNK_TOKENS`) **разбиваются на части с сохранением заголовков** таблицы в каждом чанке для сохранения контекста. Таблицы извлекаются в markdown формате. Поддерживает fallback на python-docx для DOCX файлов при ошибках docling
   - `LLMService` - взаимодействует с LLM провайдерами с **ПАРАЛЛЕЛЬНОЙ обработкой** чанков **БАТЧАМИ** (`MAX_CONCURRENT_REQUESTS=3`, `BATCH_SIZE=50`, `asyncio.Semaphore`). Методы `extract_contract_data_parallel()` и `extract_services_from_chunks()` разбивают чанки на батчи по 50 штук и обрабатывают каждый батч параллельно через `asyncio.gather()`. Объединяет результаты через финальную агрегацию через LLM (aggregate_chunks_data) с разрешением конфликтов. При ошибке использует fallback на простое объединение (merge_extracted_data)
   - `prompts.py` - содержит промпты для LLM: EXTRACT_CONTRACT_DATA_PROMPT с явными инструкциями по извлечению полной контактной информации об агентах и контрагентах (телефоны, email, адреса, должности) и основных данных контракта БЕЗ извлечения услуг, VALIDATE_EXTRACTED_DATA_PROMPT для валидации извлеченных данных, MERGE_CHUNKS_DATA_PROMPT для объединения данных из разных чанков с использованием накопленного контекста из предыдущих чанков (accumulated_context) для приоритизации и разрешения конфликтов (locations, responsible_persons), EXTRACT_SERVICES_ONLY_PROMPT для специализированного извлечения услуг из спецификации/таблиц (название, количество, единица измерения, цена за единицу, общая стоимость, описание) отдельным запросом в шаге 3.5
   - `ValidationService` - валидирует извлеченные данные, улучшенная очистка ИНН от префиксов (ИНН:, ИНН , inn: и т.д.)
   - `OneCService` - взаимодействует с 1С через MCP Service
5. **Testing System** (`app/testing/`) - система автоматического тестирования:
   - `TestCaseManager` - загружает тестовые случаи из JSON файлов в `tests/test_cases/`
   - `TestRunner` - запускает тесты, сравнивает результаты с ожидаемыми, генерирует отчеты
   - API endpoint `POST /testing/process-contract` - позволяет повторно обработать уже обработанные документы по contract_id без загрузки новых файлов, что удобно для тестирования и обновления результатов обработки
6. **State Management** (`app/agent/state_manager.py`) - сохраняет состояние обработки в Redis
7. **Celery Tasks** (`app/tasks/processing_tasks.py`) - выполняют асинхронную обработку контрактов:
   - `process_contract_task` - задача обработки контракта, запускается через `process_contract_task.delay()` из API endpoint
   - Задачи отправляются в очередь Redis и обрабатываются Celery Worker
   - Celery Worker запускается отдельным контейнером с командой `celery -A app.tasks.celery_app worker --loglevel=info`

## Frontend структура

### Директории и файлы

```
frontend/
├── public/
│   └── index.html                    # HTML шаблон
│
├── src/
│   ├── main.jsx                      # Точка входа React приложения
│   ├── App.jsx                       # Корневой компонент приложения
│   │
│   ├── components/                   # React компоненты
│   │   ├── Header.jsx                # Шапка приложения
│   │   ├── Sidebar.jsx               # Боковая панель навигации
│   │   ├── ContractUploader.jsx      # Компонент загрузки контрактов (drag-and-drop)
│   │   ├── ContractList.jsx         # Список контрактов с фильтрацией
│   │   ├── ContractDetails.jsx      # Детальный просмотр контракта (вкладки: Данные, Услуги, Валидация; кнопки: Работа с 1С, Обновить услуги; модальные окна: LLM запросы, 1С информация)
│   │   ├── DataViewer.jsx            # Отображение JSON данных (renderField, renderResponsiblePersons, renderLocations, renderCounterparty, renderAllServicesTable - сворачиваемая таблица услуг, formatValue, translateField)
│   │   ├── ValidationResults.jsx    # Результаты валидации
│   │   ├── LoadingSpinner.jsx       # Индикатор загрузки
│   │   ├── NotificationContainer.jsx # Контейнер уведомлений
│   │   ├── TestFileList.jsx         # Список файлов для тестирования с управлением обработкой
│   │   └── TestResultViewer.jsx     # Просмотр результатов обработки с полным текстом документа
│   │
│   ├── pages/                        # Страницы приложения
│   │   ├── DashboardPage.jsx        # Главная страница
│   │   ├── UploadPage.jsx           # Страница загрузки контрактов
│   │   ├── HistoryPage.jsx          # История обработки
│   │   ├── TestsPage.jsx            # Страница тестирования с загрузкой файлов, просмотром результатов и кнопкой проверки работы MCP 1С
│   │   └── SettingsPage.jsx         # Настройки
│   │
│   ├── services/                     # API сервисы
│   │   ├── api.js                   # Базовая конфигурация axios
│   │   └── contractService.js       # Сервис для работы с контрактами (uploadContract, getContractStatus, getContractData, listContracts, deleteContract, getContractRawText, getLLMInfo, get1CInfo, createCounterpartyIn1C, refreshServices, processContractForTests, testMCP1C)
│   │
│   ├── store/                        # Redux store
│   │   ├── store.js                 # Конфигурация Redux store
│   │   └── slices/
│   │       ├── contractSlice.js     # Redux slice для контрактов (addContract, updateContract, setContracts, setFilter)
│   │       ├── userSlice.js         # Redux slice для пользователя
│   │       └── uiSlice.js           # Redux slice для UI состояния
│   │
│   ├── hooks/                        # React хуки
│   │   ├── useContract.js           # Хук для работы с контрактами
│   │   ├── useAuth.js               # Хук для аутентификации
│   │   └── useFetch.js              # Хук для загрузки данных
│   │
│   └── styles/                       # Стили
│       ├── global.css               # Глобальные стили
│       └── variables.css           # CSS переменные
│
├── vite.config.js                    # Конфигурация Vite
├── package.json                      # Зависимости Node.js
├── tsconfig.json                     # Конфигурация TypeScript
├── tailwind.config.js                # Конфигурация TailwindCSS
└── postcss.config.js                 # Конфигурация PostCSS
```

### Взаимодействие компонентов Frontend

1. **React App** (`src/App.jsx`) - корневой компонент с роутингом
2. **Pages** (`src/pages/`) - страницы приложения, используют компоненты и сервисы:
   - `TestsPage` - страница тестирования с загрузкой файлов, управлением обработкой и просмотром результатов
3. **Components** (`src/components/`) - переиспользуемые UI компоненты:
   - `TestFileList` - отображает список загруженных файлов с возможностью обработки по одному или все сразу
   - `TestResultViewer` - модальное окно с результатами обработки, включая полный распознанный текст документа, извлеченные данные, информацию о запросах LLM и статус обработки
   - `ContractDetails` - детальный просмотр контракта с вкладками:
     - **Данные** - основные извлеченные данные договора
     - **Услуги** - таблица всех услуг с колонками: №, Наименование, Кол-во, Ед. изм., Цена за ед., Сумма; итоговая строка с общей суммой
     - **Валидация** - результаты валидации данных
     - Кнопка "Обновить услуги" - повторное извлечение услуг через API endpoint refresh-services
     - Кнопка "Работа с 1С" - создание контрагента в 1С
     - Модальное окно "Запросы LLM" - отображает все запросы LLM включая services_extraction с количеством найденных услуг
   - `DataViewer` - рендеринг JSON данных с поддержкой сворачиваемой таблицы услуг (all_services - ОСНОВНОЙ источник услуг из шага 3.5)
4. **Services** (`src/services/`) - взаимодействие с Backend API через axios:
   - `contractService.getContractRawText()` - получение полного распознанного текста документа
   - `contractService.getLLMInfo()` - получение информации о запросах LLM (включая запросы services_extraction)
   - `contractService.get1CInfo()` - получение информации о работе с 1С
   - `contractService.createCounterpartyIn1C()` - создание контрагента в 1С
   - `contractService.refreshServices()` - повторное извлечение услуг из документа через LLM (POST /contracts/{id}/refresh-services)
5. **Redux Store** (`src/store/`) - управление глобальным состоянием приложения
6. **Hooks** (`src/hooks/`) - кастомные React хуки для переиспользования логики

## MCP Service структура

### Директории и файлы

```
mcp_service/
├── server/
│   ├── __init__.py
│   └── mcp_server.py                # MCP сервер (MCPServer: handle_sse_connect, execute_command, _check_counterparty, _create_counterparty, _update_counterparty, _create_agreement, _attach_file, _get_one_counterparty)
│
├── client/
│   ├── __init__.py
│   └── oneс_client.py               # OData клиент для 1С (OneCClient: execute_query, query_data, create_entity, update_entity, attach_file)
│
├── server.py                         # Точка входа MCP сервиса (create_app, main: AIOHTTP приложение с маршрутами /sse/{client_id}, /command, /health)
├── Dockerfile                        # Docker образ для MCP сервиса
└── requirements.txt                 # Python зависимости (aiohttp, structlog, pydantic)
```

### Взаимодействие компонентов MCP Service

1. **MCP Server** (`server/mcp_server.py`) - обрабатывает SSE подключения и команды:
   - `handle_sse_connect` - устанавливает SSE соединение с heartbeat каждые 30 секунд
   - `execute_command` - выполняет команды через `_execute_command_impl`
   - `_check_counterparty` - проверяет наличие контрагента по ИНН через OData запрос
   - `_create_counterparty` - создает нового контрагента в 1С с данными из контракта
   - `_prepare_note` - формирует заметку для контрагента со всей информацией о контракте, включая услуги из `all_services` (извлеченные в шаге 3.5) в конце заметки (название, количество, единица измерения, цена за единицу, общая стоимость)
   - `_update_counterparty` - обновляет данные существующего контрагента
   - `_create_agreement` - создает договор с контрагентом
   - `_attach_file` - прикрепляет файл контракта к контрагенту или договору через каталог Catalog_ХранилищеДополнительнойИнформации (поддерживает параметры counterparty_uuid, agreement_uuid, file_path, file_name)
   - `_get_one_counterparty` - получает одного контрагента из 1С (первого из списка) для тестирования подключения
2. **OData Client** (`client/oneс_client.py`) - взаимодействует с 1С через OData API:
   - `initialize` - инициализирует aiohttp сессию с базовой аутентификацией
   - `execute_query` - выполняет GET запросы к OData endpoint (например, Catalog_Контрагенты)
   - `query_data` - выполняет запросы данных с фильтрацией, пагинацией и сортировкой (filter_expr, top, skip, order_by)
   - `create_entity` - создает сущности через POST запрос
   - `update_entity` - обновляет сущности через PATCH запрос с форматом URL `{entity_set}(guid'{entity_key}')`
   - `attach_file` - прикрепляет файлы к сущностям через каталог Catalog_ХранилищеДополнительнойИнформации (создает запись с полями Хранилище_Base64Data, ИмяФайла, Объект, Объект_Type, Расширение, Размер, ТипХраненияФайла). Поддерживает прикрепление к договорам (Catalog_ДоговорыКонтрагентов) и контрагентам (Catalog_Контрагенты)
   - `close` - закрывает HTTP сессию
3. **AIOHTTP App** (`server.py`) - HTTP сервер с маршрутами и middleware:
   - `GET /sse/{client_id}` - SSE подключение для real-time коммуникации
   - `POST /command` - выполнение команд (check_counterparty, create_counterparty, update_counterparty, create_agreement, attach_file, get_one_counterparty)
   - `GET /health` - health check endpoint
   - CORS middleware для кросс-доменных запросов
   - Инициализация OneCClient при старте приложения

## Поток обработки контракта

1. **Frontend** - пользователь загружает DOCX или PDF файл через `ContractUploader`
2. **Backend API** (`POST /contracts/upload`) - принимает файл, валидирует через `DocumentValidator` (поддерживает DOCX и PDF), сохраняет в хранилище
3. **Celery Task** (`process_contract_task`) - задача отправляется в очередь Redis через `process_contract_task.delay()`
4. **Celery Worker** - обрабатывает задачу из очереди Redis, обновляет статус контракта на `PROCESSING`
5. **Agent Orchestrator** - выполняет pipeline:
   - Загружает документ через `DocumentProcessor` (DOCX или PDF)
   - Извлекает текст и таблицы из документа через docling (таблицы в markdown формате). Создает список `document_elements[]` с элементами типа TEXT и TABLE
   - Проверяет размер документа: если документ большой, разбивает на чанки через `DocumentProcessor.get_chunks_for_llm()` с максимальным размером `MAX_CHUNK_TOKENS` для текста и `MAX_TABLE_CHUNK_TOKENS` для таблиц (по умолчанию 2000 токенов). **ВАЖНО**: большие таблицы, превышающие лимит `MAX_TABLE_CHUNK_TOKENS`, разбиваются на части с сохранением заголовков столбцов в каждом чанке для сохранения контекста LLM
   - **Шаг 3: ПАРАЛЛЕЛЬНАЯ обработка чанков БАТЧАМИ для извлечения основных данных контракта**: извлекает данные через `LLMService.extract_contract_data_parallel()` с промптом `EXTRACT_CONTRACT_DATA_PROMPT`. Чанки разбиваются на батчи по 50 штук (`BATCH_SIZE=50`) и каждый батч обрабатывается параллельно через `asyncio.gather()` с ограничением до 3 одновременных запросов (`MAX_CONCURRENT_REQUESTS=3`) через `asyncio.Semaphore`. Это ускоряет обработку в ~2-3 раза по сравнению с последовательной обработкой и позволяет эффективно обрабатывать большие документы. Извлекаются ТОЛЬКО основные данные: название договора, номер, дата, цена, НДС, контрагенты (заказчик, исполнитель), ответственные лица, контактная информация, условия оплаты, адреса оказания услуг и т.д. БЕЗ извлечения услуг. Затем выполняет финальную агрегацию через `LLMService.aggregate_chunks_data()` для объединения результатов и разрешения конфликтов между чанками через LLM с промптом `MERGE_CHUNKS_DATA_PROMPT`. При ошибке агрегации используется fallback на `merge_extracted_data()`. Таблицы в markdown формате включены в контекст для LLM. Информация о всех запросах LLM (включая финальную агрегацию) сохраняется в `llm_requests` с типом `chunk_parallel` и `aggregation_parallel`
   - **Шаг 3.5: Параллельное извлечение ВСЕХ услуг отдельным запросом БАТЧАМИ** через `_extract_all_services()`: после основного извлечения данных выполняется ОТДЕЛЬНОЕ ПАРАЛЛЕЛЬНОЕ извлечение услуг через `LLMService.extract_services_from_chunks()` со специализированным промптом `EXTRACT_SERVICES_ONLY_PROMPT`. Чанки разбиваются на батчи по 50 штук (`BATCH_SIZE=50`) и каждый батч обрабатывается параллельно через `asyncio.gather()` с ограничением до 3 одновременных запросов. Специализированный промпт оптимизирован для извлечения ВСЕХ строк из таблиц спецификаций. Результаты агрегируются с дедупликацией по названию услуги. Результат сохраняется в `state.extracted_data['all_services']`. Промпт учитывает русский формат цен (пробел как разделитель тысяч, запятая для десятичных: "7 702,40" → 7702.40). Информация о запросе логируется в `state.llm_requests` с типом `services_extraction_parallel`. Преимущества: специализированный промпт лучше справляется с извлечением всех строк из таблиц, уменьшение размера промптов в шаге 3 улучшает качество извлечения основных данных
   - Валидирует данные через `ValidationService` (с улучшенной очисткой ИНН от префиксов)
   - Проверяет наличие контрагента в 1С через `OneCService` -> MCP Service
   - Создает контрагента в 1С если не найден
   - Прикрепляет файл контракта к договору (если создан) или к контрагенту через каталог Catalog_ХранилищеДополнительнойИнформации
5. **State Manager** - сохраняет состояние обработки в Redis на каждом этапе
6. **Frontend** - периодически опрашивает статус через `GET /contracts/{id}/status` и отображает результаты

## База данных

### Таблицы PostgreSQL

- **contracts** - информация о загруженных контрактах (id, uuid, filename, status, timestamps)
- **contract_data** - извлеченные данные контракта (inn, full_name, contract_price, dates, locations JSONB, responsible_persons JSONB, services JSONB - DEPRECATED, сохранено для обратной совместимости, будет null или пустым массивом, all_services JSONB - ОСНОВНОЙ источник услуг, список всех услуг из специализированного извлечения в шаге 3.5 с полями: name, quantity, unit, unit_price, total_price, description)
- **processing_history** - история обработки контрактов (включая запросы типа chunk_parallel, aggregation_parallel, services_extraction_parallel)
- **validation_results** - результаты валидации извлеченных данных
- **counterparty_1c** - связь контрактов с контрагентами в 1С (contract_id, counterparty_uuid, agreement_uuid)

## Хранилище файлов

- **storage/contracts/uploaded/** - загруженные DOCX файлы
- **storage/contracts/processed/** - обработанные файлы
- **storage/logs/** - логи приложения

## Мониторинг

- **Prometheus** (`prometheus/prometheus.yml`) - сбор метрик (время обработки, количество успешных/неудачных обработок, использование ресурсов). Метрики доступны через `/metrics` endpoint. Конфигурация включает scrape_configs для backend, postgres, redis, mcp-service
- **Grafana** (`grafana/dashboards/sgr-agent-dashboard.json`) - визуализация метрик через дашборды (порт 3001). Дашборд включает панели: Contracts Processed (Daily), Processing Duration (p95), LLM API Call Success Rate, 1C Integration Success Rate, Task Queue Length, API Response Time (p99). Автоматическая настройка через provisioning (`grafana/provisioning/datasources/prometheus.yml`, `grafana/provisioning/dashboards/default.yml`)
- **Jaeger** - distributed tracing для отслеживания запросов через OpenTelemetry (порт 16686 для UI)
- **Structlog** (`app/utils/logging.py`) - структурированное логирование с поддержкой JSON формата для ELK Stack. Использует pythonjsonlogger.JsonFormatter для JSON вывода, RotatingFileHandler для ротации логов (10MB, 5 файлов), добавляет поля service_name, environment, version для ELK
- **Filebeat** (`filebeat/filebeat.yml`) - сбор и отправка логов в Elasticsearch. Настроен для чтения логов из `/var/log/sgr-agent/*.log` и Docker контейнеров, добавляет метаданные Docker, настраивает ILM (Index Lifecycle Management) для ротации индексов

## Инфраструктура

- **Docker Compose** (`docker-compose.yml`) - оркестрация всех сервисов для разработки:
  - **Сетевая конфигурация**: все сервисы кроме PostgreSQL и Frontend находятся только внутри сети `sgr_network` без внешних портов. PostgreSQL и Frontend имеют внешние порты для доступа извне, но также подключены к сети `sgr_network` для взаимодействия с другими сервисами
  - Frontend (порт 3000) - внешний доступ
  - PostgreSQL (порт 5434) - внешний доступ
  - Backend - только внутри сети sgr_network
  - Celery Worker - только внутри сети sgr_network, обработка асинхронных задач через Redis
  - Redis - только внутри сети sgr_network
  - MCP Service - только внутри сети sgr_network
  - Prometheus - только внутри сети sgr_network
  - Grafana - только внутри сети sgr_network
  - Jaeger - только внутри сети sgr_network
- **Docker Compose Production** (`docker-compose.prod.yml`) - production конфигурация с:
  - Оптимизированными Dockerfile для backend и frontend
  - Celery Worker для обработки асинхронных задач
  - Nginx reverse proxy (порты 80, 443)
  - Filebeat для отправки логов в Elasticsearch
  - Health checks для всех сервисов
  - Автоматическим применением миграций БД при старте
- **Nginx** (`nginx/nginx.conf`) - reverse proxy для production с поддержкой HTTP/HTTPS
- **Alembic** - управление миграциями БД с автоматическим применением при старте приложения через `scripts/init_db.py`
- **Storage Service** - локальное хранилище файлов в `storage/contracts/uploaded/` и `storage/contracts/processed/`
- **Backup Scripts** (`scripts/backup_db.py`) - автоматическое резервное копирование БД через pg_dump с ротацией (последние 7 бэкапов)

## Последние изменения (2026-02-04)

### Удаление дублирующего извлечения услуг из шага 3

**Проблема**: Извлечение услуг дублировалось в двух местах:
- Шаг 3 (`_extract_contract_data`) - извлекал услуги вместе с основными данными контракта через `EXTRACT_CONTRACT_DATA_PROMPT`
- Шаг 3.5 (`_extract_all_services`) - отдельное специализированное извлечение услуг через `EXTRACT_SERVICES_ONLY_PROMPT`

**Решение**: Удалено извлечение услуг из шага 3, оставлено только в шаге 3.5.

**Изменения**:

1. **`backend/app/services/prompts.py`**:
   - Удалено поле 17 "Services (Услуги из спецификации/таблиц)" из `EXTRACT_CONTRACT_DATA_PROMPT`
   - Удалена секция "CRITICAL: SERVICES EXTRACTION" с детальными инструкциями по извлечению услуг
   - Перенумерованы оставшиеся поля с 17-25 (ранее 18-26)
   - Обновлен `MERGE_CHUNKS_DATA_PROMPT`: удалены инструкции по объединению услуг из секции 7 "List Fields"
   - Обновлена секция 9 "Using Accumulated Context": убрана ссылка на services

2. **`backend/app/agent/orchestrator.py`**:
   - Удалена секция "УСЛУГИ ИЗ СПЕЦИФИКАЦИИ" из метода `_build_chunk_context` (25 строк кода)
   - Контекст для последующих чанков больше не содержит информацию об услугах из предыдущих чанков

3. **База данных и API**:
   - Поле `contract_data.services` сохранено для обратной совместимости (deprecated, будет null или пустым)
   - Основной источник услуг: `contract_data.all_services` (извлекается в шаге 3.5)
   - API endpoints не изменены
   - Frontend не изменен (уже использует `all_services`)

**Преимущества**:
- Уменьшение размера промптов для шага 3 → улучшение качества извлечения основных данных
- Устранение дублирования кода и логики
- Специализированный промпт `EXTRACT_SERVICES_ONLY_PROMPT` в шаге 3.5 лучше справляется с извлечением всех строк из таблиц
- Более чистая архитектура: один источник ответственности для каждого типа данных

**Тестирование**:
- Создан автоматический тест `test_no_duplicate_services.py` для верификации изменений
- Все тесты пройдены успешно ✅
- Создан документ `IMPLEMENTATION_SUMMARY.md` с детальным описанием изменений и чек-листом для проверки
