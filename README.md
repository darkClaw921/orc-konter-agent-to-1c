# ИИ агент для создания контрагентов в 1С

Интеллектуальный агент на базе SGR Agent Core для автоматизации создания и заполнения карточек контрагентов в информационной системе 1С на основе документов государственных контрактов (DOCX).

## Основные возможности

- Загрузка документов контрактов (DOCX) через веб-интерфейс
- Извлечение ключевых реквизитов из документов с помощью LLM
- Проверка наличия контрагента в справочнике 1С по ИНН
- Автоматическое создание новых контрагентов с заполнением всех полей согласно регламенту
- Создание сопутствующих договоров и документов в 1С
- Валидация результатов через систему автоматических проверок

## Архитектура

Проект состоит из трех основных компонентов:

- **Backend** (Python/FastAPI) - SGR Agent Core с интеграцией LLM и обработкой документов
- **Frontend** (React/TypeScript) - Веб-интерфейс для загрузки и управления контрактами
- **MCP Service** (Python/AIOHTTP) - Сервис для взаимодействия с 1С через Server-Sent Events

## Быстрый старт

### Требования

- Docker и Docker Compose
- Python 3.11+ (для локальной разработки)
- Node.js 18+ (для локальной разработки frontend)

### Запуск через Docker Compose

```bash
docker-compose up -d
```

Сервисы будут доступны по адресам:
- Frontend: http://localhost:3000 (через frontend доступен Backend API через прокси)
- PostgreSQL: localhost:5433

Остальные сервисы (Backend, MCP Service, Redis, Prometheus, Grafana, Jaeger) доступны только внутри Docker сети `sgr_network` и не имеют внешних портов.

### Локальная разработка

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # или `venv\Scripts\activate` на Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

#### MCP Service

```bash
cd mcp_service
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python server.py
```

## Конфигурация

Скопируйте `.env.example` в `.env` и заполните необходимые переменные окружения.

## Документация

Подробная документация доступна в директории `docs/`:
- `docs/build_your_agent.md` - Руководство по созданию агента
- `docs/tools.md` - Описание инструментов SGR Framework
- `docs/configuration.md` - Конфигурация системы

## Управление задачами

Проект использует **bd** (beads) для управления задачами:

```bash
bd ready              # Найти доступные задачи
bd show <id>          # Просмотр деталей задачи
bd update <id> --status in_progress  # Взять задачу в работу
bd close <id>         # Завершить задачу
bd sync               # Синхронизация с git
```

## Лицензия

Проект разработан для внутреннего использования.
