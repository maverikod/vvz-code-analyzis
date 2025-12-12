# Регистрация MCP сервера Code Analysis

## Запуск сервера

```bash
# Запустить сервер на localhost:15000
python -m code_analysis.mcp_server --host localhost --port 15000
```

## Регистрация в MCP Proxy

Сервер должен быть зарегистрирован в конфигурации MCP Proxy. Добавьте в конфигурацию:

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

## Использование через MCP Proxy

Все команды требуют параметр `root_dir` - корневой каталог проекта.

Пример вызова через MCP Proxy:

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

## Доступные команды

1. **analyze_project** - Анализ Python проекта
2. **find_usages** - Поиск использований методов/свойств
3. **full_text_search** - Полнотекстовый поиск в коде
4. **search_classes** - Поиск классов по паттерну
5. **search_methods** - Поиск методов по паттерну
6. **get_issues** - Получение проблем кода
7. **split_class** - Разделение класса на несколько
8. **extract_superclass** - Извлечение базового класса
9. **merge_classes** - Объединение классов
