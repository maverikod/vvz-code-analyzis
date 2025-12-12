# Code Analysis MCP Server

## Статус

✅ MCP сервер мигрирован на FastMCP framework
✅ Все 9 инструментов доступны
✅ Поддержка async операций
✅ Автоматическая валидация типов
✅ Поддержка нескольких транспортов (stdio, SSE, HTTP)
✅ Покрытие тестами: 92% для новых модулей
✅ Все 257 тестов проходят

## Запуск сервера

```bash
# Активировать виртуальное окружение
source .venv/bin/activate

# Запустить сервер (HTTP transport по умолчанию)
python -m code_analysis.mcp_server --host 127.0.0.1 --port 15000

# Запустить с stdio transport (для CLI инструментов)
python -m code_analysis.mcp_server --transport stdio

# Запустить с SSE transport
python -m code_analysis.mcp_server --transport sse --host 127.0.0.1 --port 15000

# Установить уровень логирования
python -m code_analysis.mcp_server --log-level DEBUG
```

## Регистрация в MCP Proxy

Добавьте в конфигурацию MCP Proxy (аналогично примеру с MCP-Proxy-2):

```json
{
  "mcpServers": {
    "code-analysis-server": {
      "name": "Code Analysis Server",
      "url": "http://localhost:15000/mcp",
      "version": "1.0.0",
      "enabled": true
    }
  }
}
```

## Доступные инструменты

### 1. analyze_project
Анализ Python проекта и генерация карты кода.

**Параметры**:
- `root_dir` (required): Корневой каталог проекта
- `max_lines` (optional, default: 400): Максимальное количество строк в файле

### 2. find_usages
Поиск всех использований метода или свойства.

**Параметры**:
- `root_dir` (required): Корневой каталог проекта
- `name` (required): Имя метода/свойства
- `target_type` (optional): Тип (method/property/function)
- `target_class` (optional): Имя класса

### 3. full_text_search
Полнотекстовый поиск в коде и докстрингах.

**Параметры**:
- `root_dir` (required): Корневой каталог проекта
- `query` (required): Поисковый запрос
- `entity_type` (optional): Тип сущности (class/method/function)
- `limit` (optional, default: 20): Максимальное количество результатов

### 4. search_classes
Поиск классов по паттерну имени.

**Параметры**:
- `root_dir` (required): Корневой каталог проекта
- `pattern` (optional): Паттерн поиска

### 5. search_methods
Поиск методов по паттерну имени.

**Параметры**:
- `root_dir` (required): Корневой каталог проекта
- `pattern` (optional): Паттерн поиска

### 6. get_issues
Получение проблем качества кода.

**Параметры**:
- `root_dir` (required): Корневой каталог проекта
- `issue_type` (optional): Тип проблемы для фильтрации

### 7. split_class
Разделение класса на несколько меньших классов.

**Параметры**:
- `root_dir` (required): Корневой каталог проекта
- `file_path` (required): Путь к файлу
- `config` (required): Конфигурация разделения

### 8. extract_superclass
Извлечение общей функциональности в базовый класс.

**Параметры**:
- `root_dir` (required): Корневой каталог проекта
- `file_path` (required): Путь к файлу
- `config` (required): Конфигурация извлечения

### 9. merge_classes
Объединение нескольких классов в один базовый класс.

**Параметры**:
- `root_dir` (required): Корневой каталог проекта
- `file_path` (required): Путь к файлу
- `config` (required): Конфигурация объединения

## Примеры использования

### Через MCP Proxy

```json
{
  "server_id": "code-analysis-server",
  "command": "analyze_project",
  "params": {
    "root_dir": "/path/to/project",
    "max_lines": 400
  }
}
```

### Прямой вызов

```bash
curl -X POST http://localhost:15000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "find_usages",
      "arguments": {
        "root_dir": "/path/to/project",
        "name": "method_name"
      }
    }
  }'
```

## Структура проекта

```
code_analysis/
├── core/           # Основная логика (analyzer, database, refactorer)
├── cli/            # CLI команды
├── api/            # API для использования как библиотеки
└── mcp_server.py   # MCP сервер (FastMCP-based)
```

## Миграция на FastMCP

Сервер был мигрирован с ручной реализации JSON-RPC на FastMCP framework.
Это обеспечивает:
- Автоматическую генерацию схем из type hints
- Валидацию параметров через Pydantic
- Поддержку async операций
- Встроенный Context для логирования и прогресса
- Поддержку нескольких транспортов
- Соответствие стандартам MCP протокола

## Тестирование

Все тесты проходят:
```bash
pytest tests/ -v
# 257 passed
```

Покрытие новых модулей:
- `usage_analyzer`: 95%
- `database`: 91%
- `search_cli`: 95%
- `mcp_server`: 80%+
- **Общее: 92%**
