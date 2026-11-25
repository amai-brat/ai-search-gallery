# AI Search Gallery

Локальный поиск по изображениям: по смыслу (CLIP, SigLIP2) и по тексту на картинке (OCR, PP-OCRv5).
Русский и английский поддерживаются обеими моделями.

## Как начать

### Windows (PowerShell, через скрипты)

Нужны: Docker Desktop и Python 3.13 (`uv` скрипт поставит сам).

```powershell
.\scripts\setup.ps1     # один раз: .env, Docker (Postgres + Redis), зависимости, модели
.\scripts\start.ps1 -Open   # запустить всё и открыть сайт
.\scripts\stop.ps1      # остановить воркер, API и сайт
```

- `start.ps1` открывает три окна (воркер Celery, API и сайт). `-Hidden` — без окон, логи в `logs\`.
- `stop.ps1 -Docker` дополнительно останавливает контейнеры, `stop.ps1 -WipeData` ещё и стирает базу.
- Сайт: http://127.0.0.1:5180 (нужен Node.js; `setup.ps1` сам делает `npm install`)
- API: http://127.0.0.1:8000/docs

Postgres (pgvector) доступен на `localhost:5434`, Redis на `localhost:6380`
(нестандартные порты, чтобы не пересекаться с локальным Postgres и другими контейнерами;
меняются переменными `PG_PORT` / `REDIS_PORT` и в `backend/.env`).

### Вручную (Linux / macOS)

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

Модели (ONNX) скачаются сами при первом запуске в `backend/models`, см. раздел «Модели».

Заполнить `.env` по `.env.example`
```bash
cp .env.example .env
```

Запустить Celery (из папки `backend/src`)
```bash
celery -A worker worker
```

Запустить FastAPI (в другом терминале, из папки `backend`)
```bash
uv run --env-file=.env fastapi dev src/app.py
```

### Вручную (Windows, без скриптов)

```powershell
docker compose up -d --wait
cd backend
uv sync
Copy-Item .env.example .env
uv run --env-file .env python scripts/download_models.py

# окно 1 (воркер; --pool=solo обязателен на Windows)
cd src
uv run celery -A worker worker --pool=solo --loglevel=info

# окно 2 (API), из папки backend
uv run --env-file .env fastapi dev src/app.py
```

## Веб-интерфейс

Папка `frontend/`: React + TypeScript + Vite. Запускается вместе с остальным через `start.ps1`,
либо отдельно:

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5180
```

- **Поиск**: два поля (по смыслу и по тексту на картинке, можно заполнить оба), примеры запросов,
  просмотр картинки с распознанным текстом. Без запроса показывается вся библиотека.
- **Индексация**: выбор папки в проводнике (кнопка «Обзор…» открывает системный диалог на машине с API)
  или путь вручную, загрузка отдельных файлов перетаскиванием. Ниже очередь с прогрессом и список
  уже проиндексированных папок; «Обновить» подхватывает новые файлы в папке.

Количество результатов (`limit`, 10–100) и точность поиска по смыслу (`strictness`: `strict`, `balanced`,
`wide`, `off`) выбираются под строкой поиска. Поиск по смыслу всегда возвращает ближайшие картинки, даже
нерелевантные, поэтому результаты, заметно более далёкие от запроса, чем лучший, отсекаются; в ответе
`hidden_count` показывает, сколько скрыто. Размер окна настраивается `SEMANTIC_WINDOW_STRICT`,
`SEMANTIC_WINDOW_BALANCED` и `SEMANTIC_WINDOW_WIDE` в `backend/.env` (подобрано на тестовом наборе).

В dev-режиме Vite проксирует `/api` на FastAPI (`http://127.0.0.1:8000`, меняется переменной
`VITE_API_PROXY`). Для сборки (`npm run build`) с прямым адресом API задайте `VITE_API_URL`,
а в `backend/.env` добавьте адрес сайта в `CORS_ORIGINS`.

Для интерфейса бэкенд получил: `GET /images/index/jobs` (очередь и история), `POST /images/index/upload`,
`POST /fs/pick-directory`, `GET /images/{id}/thumbnail`, поля `ocr_text` и `total` в списках.
Загруженные файлы и миниатюры лежат в `backend/storage/` (в git не попадает, путь меняется `STORAGE_DIR`).

## Тестовые картинки

Чтобы быстро наполнить галерею, есть скрипт, который собирает тестовый набор (~42 файла) в папку
`test-images` в корне проекта (в git она не попадает):

```powershell
cd backend
uv run python scripts/fetch_test_images.py
```

В наборе: фото предметов (яблоко, кошка, велосипед, пицца и т.д.), фото вывесок и дорожных указателей
с русским текстом и «доски» с одним словом («Яблоко», «Кофе», «Apple»...). Фото скачиваются из
Wikimedia Commons (нужен интернет), доски рисуются локально. `--dry-run` только покажет список,
`--out <папка>` меняет место сохранения.

Затем проиндексируйте папку: `POST /images/index` с телом
`{"directory_path": "C:/путь/к/проекту/test-images"}`, и пробуйте, например:
`semanticQuery=яблоко`, `semanticQuery=дорожный знак`, `ocrQuery=двуречье`.

## Как проверить

1. `POST /images/index` с телом `{"directory_path": "C:/Users/<вы>/Pictures"}` — индексация идёт в фоне, смотрите окно воркера.
2. `GET /images/search?semanticQuery=собака на пляже`
3. `GET /images/search?ocrQuery=счёт`
4. `GET /images/{id}/file` — открыть найденную картинку.

## Модели

| Что | Модель | Размер | Где лежит |
| --- | --- | --- | --- |
| CLIP | `ViT-B-16-SigLIP2` (мультиязычная, вектор 768), ONNX-экспорт `immich-app/ViT-B-16-SigLIP2__webli` | ~1.5 ГБ | `backend\models\clip` |
| OCR | `PP-OCRv5_mobile_det` + `eslav_PP-OCRv5_mobile_rec` в ONNX (RapidOCR) | 13 МБ | `backend\models\rapidocr` |

Обе модели работают на ONNX Runtime, только CPU; torch и PaddlePaddle не нужны. Папка моделей меняется
переменной `MODELS_DIR`.

Скачать заранее (делает и `setup.ps1`):

```powershell
cd backend
uv run --env-file .env python scripts/download_models.py
```

Поменять модель — в `backend/.env`:

- `CLIP_MODEL_NAME` — имя модели, ONNX-экспорт берётся из `immich-app/<имя>__webli` (или задайте
  `CLIP_MODEL_REPO`). Например, `ViT-B-32-SigLIP2-256`: кодирует картинки в несколько раз быстрее при
  чуть меньшей точности (см. `bench/README.md`). После смены модели нужна полная переиндексация
  (`stop.ps1 -WipeData`), а если у модели другая размерность вектора, ещё и `VECTOR(768)` в
  `backend/src/migrations/001_init.sql`.

## OCR-поиск

При индексации изображений Celery-воркер распознаёт текст через RapidOCR (модели PP-OCRv5 на
ONNX Runtime) и сохраняет его в поле `images.ocr_text`.

Настройки OCR (`.env`):

```bash
# OCR_MAX_SIDE=960   # картинки больше уменьшаются перед распознаванием (0 — не уменьшать)
# OCR_THREADS=0      # потоков ONNX Runtime на модель, 0 — автоматически
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

Без кавычек слово ищется как подстрока, регистр не важен. Кроме того, находятся
другие формы слова (русские и английские): по `яблоки` найдётся «Яблоко», по
`apples` найдётся «Apple». Это стемминг средствами Postgres; для слов со
знаками `*` / `?` и для фраз в кавычках он не применяется, там совпадение
точное. Операторы `AND`,
`OR`, `NOT` можно писать в любом регистре. В ответе `matched_by` показывает,
каким способом найдено изображение (`semantic` и/или `ocr`); у OCR-результатов
`score` равен `null`. Если переданы оба запроса, результаты объединяются.
