FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 - \
 && ln -s /root/.local/bin/poetry /usr/local/bin/poetry

WORKDIR /app
COPY pyproject.toml poetry.lock ./
# disable Poetry venv creation (we'll use /app/.venv)
RUN poetry config virtualenvs.in-project true \
 && poetry install --no-root --no-interaction --no-ansi

COPY . .

RUN ollama pull deepseek-r1 || true

EXPOSE 8001