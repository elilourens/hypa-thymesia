# Formatting Microservice

A standalone microservice for text chunk formatting using Ollama LLM.

## Overview

This microservice handles text formatting operations, converting raw text chunks into markdown-formatted text while preserving the exact wording and semantic meaning.

## Features

- Single chunk formatting via `/api/v1/formatting/format-chunk`
- Batch formatting via `/api/v1/formatting/batch-format`
- Health check endpoint at `/api/v1/formatting/health`
- Concurrent processing with configurable parallelism
- Ollama LLM integration for intelligent formatting

## Running Locally

### Prerequisites

- Python 3.11+
- Ollama running locally with the `mistral` model (or configure a different model)

### Installation

```bash
cd services
poetry install
```

### Running

```bash
# Copy environment file
cp .env.example .env

# Start the service
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

### Docker

```bash
docker build -t formatting-service .
docker run -p 8002:8002 -e OLLAMA_URL=http://host.docker.internal:11434 formatting-service
```

## API Endpoints

### Format Single Chunk

```bash
POST /api/v1/formatting/format-chunk
Content-Type: application/json

{
    "text": "Your text chunk to format here..."
}
```

### Batch Format

```bash
POST /api/v1/formatting/batch-format
Content-Type: application/json

{
    "chunks": [
        {"chunk_id": "chunk-1", "text": "First chunk text..."},
        {"chunk_id": "chunk-2", "text": "Second chunk text..."}
    ],
    "max_concurrent": 10
}
```

### Health Check

```bash
GET /api/v1/formatting/health
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `mistral` | Ollama model to use |
| `OLLAMA_TIMEOUT` | `30` | Request timeout in seconds |
| `OLLAMA_NUM_PARALLEL` | `10` | Max concurrent formatting requests |
| `SERVICE_PORT` | `8002` | Service port |
