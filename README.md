# My OpenCode — Локальный AI-агент на Ollama

**Ryzen 5 5600G + RTX 3060 12GB**

---

## 📁 Содержимое

| Файл | Назначение |
|------|-----------|
| `AI Desktop.exe` | Готовый десктопный AI-ассистент (Monaco Editor + чат + файлы + терминал) |
| `AI Desktop.bat` | Запускалка для exe |

## 🚀 Быстрый старт

### 1. Убедись что Ollama запущена
```bash
ollama list
```

### 2. Загрузи модели
```bash
ollama pull qwen3.5:9b       # ★ BEST BALANCE
ollama pull qwen2.5-coder:7b # ★ FAST CODING
ollama pull deepseek-r1:8b   # ★ REASONING
```

### 3. Запусти AI Desktop
Двойной клик по `AI Desktop.exe` или `AI Desktop.bat`

### 4. Или используй OpenCode CLI
```bash
opencode --provider ollama --model qwen3.5:9b
```

## ⚙️ Настройка в OpenCode Desktop

Провайдер уже настроен в `~\.config\opencode\opencode.jsonc`:
- Ollama подключён через `@ai-sdk/openai-compatible`
- Модели: qwen3.5:9b, qwen2.5-coder:7b, deepseek-r1:8b, qwen2.5-coder:14b, deepseek-coder:6.7b
- Агенты: `my-coder`, `my-coder-fast`, `my-coder-reason`

### Системный промпт (аналог DeepSeek V4 Flash)

В `opencode.jsonc` прописан агент `my-coder` с промптом:
> «Ты — эксперт по программированию. Твоя задача — помогать пользователю писать, анализировать и улучшать код. Отвечай чётко, структурированно, по делу. Если нужно — предлагай несколько вариантов решения с пояснениями. Стиль общения — профессиональный и дружелюбный. Всегда уточняй детали, если задача неоднозначна. Ты — аналог DeepSeek V4 Flash, но работаешь локально через Ollama.»

### Контекст

Для корректной работы OpenCode с локальными моделями рекомендуется запускать Ollama с увеличенным контекстом:
```bash
OLLAMA_CONTEXT_LENGTH=64000 ollama serve
```

## 📊 Модели и VRAM

| Модель | VRAM (Q4) | Скорость | Когда использовать |
|--------|-----------|----------|-------------------|
| qwen3.5:9b | ~7 GB | ~38 ток/с | ★ Лучший баланс |
| qwen2.5-coder:7b | ~5.5 GB | ~47 ток/с | ★ Самый быстрый |
| deepseek-r1:8b | ~5.5 GB | ~47 ток/с | Рассуждения |
| qwen2.5-coder:14b | ~9 GB | ~20 ток/с | Макс. качество |

## 🖥️ AI Desktop (собранный exe)

Свой аналог OpenCode Desktop:
- **Monaco Editor** — тот же редактор что в VS Code
- **Чат с ИИ** — через локальную Ollama (streaming)
- **Файловое дерево** — навигация по проекту
- **Терминал** — запуск команд
- **Смена модели** — на лету из интерфейса
