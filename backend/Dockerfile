# Use Python 3.12 slim image for smaller size
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies including LibreOffice
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libreoffice-writer \
    libreoffice-calc \
    libreoffice-impress \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Copy Poetry configuration files (but not poetry.toml which forces venv)
COPY pyproject.toml poetry.lock ./

# Configure Poetry to not create virtual env (we're already in a container)
RUN poetry config virtualenvs.create false && \
    poetry config virtualenvs.in-project false

# Install dependencies without dev packages and cache
RUN poetry install --no-interaction --no-ansi --no-root --only main && \
    pip cache purge && \
    rm -rf /root/.cache/pypoetry && \
    rm -rf /root/.cache/pip

# Verify uvicorn is available
RUN python -m pip list | grep uvicorn

# Copy application code
COPY . .

# Expose the port FastAPI will run on
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run the application with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
