## Как начать
Запустить pgvector (postgres + vector) и redis
```bash
docker compose up
```

Скачать зависимости бэка (сначала поставить `uv`, если его нет)
```bash
cd backend
uv sync
source .venv/bin/activate
```

Скачать модель OpenCLIP в локальную папку из HuggingFace
Например:
```bash
hf download hf://timm/ViT-L-16-SigLIP2-256 --local-dir '/tmp/models/ViT-L-16-SigLIP2-256'
```

Заполнить `.env` по `.env.example`
```bash
cp .env.example .env
```

Запустить Celery
```bash
celery -A worker worker
```

Запустить FastAPI (в другом терминале)
```bash
uv run --env-file=.env fastapi dev src/app.py
```

## OCR-поиск

При индексации изображений Celery-воркер распознаёт текст через PaddleOCR и
сохраняет его в поле `images.ocr_text`. Модели OCR скачиваются автоматически
при первом запуске воркера в `~/.paddlex/official_models`.

Настройки OCR (`.env`):

```bash
PADDLEOCR_LANG=en                 # для русского текста используйте ru
# PADDLEOCR_DEVICE=gpu:0          # по умолчанию GPU 0, если доступен, иначе CPU
# PADDLEOCR_ENABLE_MKLDNN=false   # oneDNN отключён по умолчанию (падает на CPU)
```

Если изображения были проиндексированы раньше, запустите индексацию каталога
повторно — эмбеддинги переиспользуются, а OCR добавится к существующим записям.

Поиск:

```bash
GET /images/search?ocrQuery=invoice
GET /images/search?semanticQuery=кот&ocrQuery=invoice
```

`ocrQuery` поддерживает синтаксис в духе Kibana:

| Запрос | Значение |
| --- | --- |
| `invoice total` | `invoice AND total` |
| `invoice AND total` | оба слова |
| `invoice OR receipt` | любое из слов |
| `invoice AND NOT cancelled` | `invoice`, но не `cancelled` |
| `(invoice OR receipt) AND "total amount"` | группировка и точная фраза |
| `inv*` | подстановочный знак (`*`, `?`) |

Без кавычек слово ищется как подстрока, регистр не важен. Операторы `AND`,
`OR`, `NOT` можно писать в любом регистре. В ответе `matched_by` показывает,
каким способом найдено изображение (`semantic` и/или `ocr`); у OCR-результатов
`score` равен `null`.
