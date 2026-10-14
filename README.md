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