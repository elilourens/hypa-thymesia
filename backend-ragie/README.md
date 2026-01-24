# Ragie Backend - Lean Document Management API

A FastAPI-based backend for document management using **Ragie.ai** for intelligent document processing and retrieval, with **Supabase** for authentication and metadata storage, and **Stripe** for subscription management.

## Overview

This is a leaner reimplementation of the original backend, replacing:
- **Pinecone** → **Ragie.ai** (handles embeddings, indexing, and retrieval)
- **Redis/Celery** → Ragie's async processing
- **Multiple embedding models** → Ragie's built-in models
- **Custom chunking logic** → Ragie's automatic chunking

## Quick Start

### Prerequisites
- Python 3.12+
- Poetry (package manager)
- Supabase account and project
- Ragie.ai account and API key
- Stripe account (for payments)

### Setup

1. **Clone and navigate to the backend directory:**
```bash
cd backend-ragie
```

2. **Copy environment file and configure:**
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. **Install dependencies:**
```bash
poetry install
```

4. **Apply Supabase migration:**
- Open your Supabase project
- Go to SQL Editor
- Copy and execute the SQL from `migrations/001_create_ragie_documents_table.sql`

5. **Run the server:**
```bash
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000/api/v1`

## Directory Structure

```
backend-ragie/
├── main.py                           # FastAPI app entry point
├── pyproject.toml                    # Dependencies and project config
├── Dockerfile                        # Container setup
├── .env.example                      # Environment template
├── README.md                         # This file
├── migrations/
│   └── 001_create_ragie_documents_table.sql
├── core/
│   ├── config.py                     # Environment configuration
│   ├── deps.py                       # Dependency injection
│   ├── security.py                   # JWT authentication
│   ├── user_limits.py                # Quota management
│   └── __init__.py
├── services/
│   ├── ragie_service.py              # Ragie API wrapper
│   ├── supabase_service.py           # Supabase helper methods
│   └── __init__.py
├── routers/
│   ├── health.py                     # Health check
│   ├── documents.py                  # Document CRUD operations
│   ├── search.py                     # Semantic search endpoint
│   ├── groups.py                     # Document group management
│   ├── user_settings.py              # User quota and settings
│   ├── stripe_payments.py            # Stripe integration
│   └── __init__.py
├── schemas/
│   ├── document.py                   # Document request/response models
│   ├── search.py                     # Search models
│   ├── user.py                       # User and group models
│   └── __init__.py
└── utils/
    └── __init__.py
```

## API Endpoints

### Health Check
- `GET /api/v1/health` - Server health status

### Documents
- `POST /api/v1/documents/upload` - Upload a document
- `GET /api/v1/documents/list` - List user's documents
- `GET /api/v1/documents/{doc_id}` - Get document details
- `GET /api/v1/documents/{doc_id}/status` - Check processing status
- `DELETE /api/v1/documents/{doc_id}` - Delete document

### Search
- `POST /api/v1/search/retrieve` - Semantic search
  - **Query Parameters:**
    - `query` (string): Search query
    - `top_k` (int, default 8): Max results
    - `rerank` (bool, default True): Enable reranking
    - `group_id` (string, optional): Filter by group
    - `max_chunks_per_document` (int, default 0): Limit chunks per doc

### Groups
- `POST /api/v1/groups/create` - Create document group
- `GET /api/v1/groups/list` - List user's groups
- `GET /api/v1/groups/{group_id}` - Get group details
- `PUT /api/v1/groups/{group_id}` - Update group
- `DELETE /api/v1/groups/{group_id}` - Delete group

### User Settings
- `GET /api/v1/user-settings` - Get user settings
- `GET /api/v1/user-settings/quota-status` - Get quota usage

### Stripe
- `POST /api/v1/stripe/create-checkout-session` - Create payment session
- `GET /api/v1/stripe/subscription-status` - Check subscription
- `POST /api/v1/stripe/cancel-subscription` - Cancel subscription
- `POST /api/v1/stripe/webhook` - Stripe webhook handler

## Database Schema

### ragie_documents
Tracks documents uploaded to Ragie with metadata and processing status.

**Key Fields:**
- `id` - Internal document ID
- `ragie_document_id` - Ragie's document ID
- `user_id` - User who uploaded the document
- `group_id` - Optional document group
- `status` - Processing status (pending → ready)
- `filename` - Original filename
- `mime_type` - File type
- `file_size_bytes` - File size
- `chunk_count` - Number of chunks (from Ragie)
- `page_count` - Number of pages (from Ragie)
- `ragie_metadata` - Custom metadata stored in Ragie

**Status Values:**
- `pending` - Awaiting processing
- `partitioning` - Being partitioned
- `partitioned` - Partitioning complete
- `refined` - Text refined
- `chunked` - Document chunked
- `indexed` - Vector indexed
- `summary_indexed` - Summary created
- `keyword_indexed` - Keywords indexed
- `ready` - Ready for retrieval
- `failed` - Processing failed

## Authentication

The API uses JWT tokens from Supabase Authentication.

**All protected endpoints require:**
```
Authorization: Bearer <jwt_token>
```

The JWT should be obtained from Supabase Auth after user login.

## Configuration

### Environment Variables

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=sb_secret_key_here

# Ragie
RAGIE_API_KEY=tnt_your_api_key

# Stripe
STRIPE_SECRET_KEY=sk_test_key
STRIPE_PUBLISHABLE_KEY=pk_test_key
STRIPE_WEBHOOK_SECRET=whsec_secret
STRIPE_PRICE_ID=price_id

# JWT
JWT_ALGORITHM=HS256
JWT_SECRET_KEY=your_secret_key_min_32_chars

# App
API_PREFIX=/api/v1
DEBUG=false
```

## Features

### Document Management
- Upload documents (supports all file types Ragie supports)
- Automatic chunking and embedding via Ragie
- Track processing status
- Delete documents
- Organize with groups/folders

### Search & Retrieval
- Semantic search with Ragie
- Built-in reranking for relevance
- Metadata filtering (by user, group)
- Hybrid search (semantic + keyword)

### User Management
- JWT-based authentication
- Quota tracking (50 files free, 100 premium)
- User settings and preferences
- Group organization

### Subscription
- Stripe integration for payments
- Webhook handling for subscription events
- Automatic quota updates on subscription changes

## Supported File Types

**Text:** eml, html, json, md, msg, rst, rtf, txt, xml
**Images:** png, webp, jpg, jpeg, tiff, bmp, heic
**Documents:** csv, doc, docx, epub, odt, pdf, ppt, pptx, tsv, xlsx, xls
**Audio/Video:** mp3, wav, m4a, mp4, mov, avi, mkv, flv, wmv

## Development

### Running Tests
```bash
poetry run pytest
```

### Code Formatting
```bash
poetry run black .
```

### Type Checking
```bash
poetry run mypy .
```

### Linting
```bash
poetry run flake8 .
```

## Deployment

### Docker

1. **Build image:**
```bash
docker build -t ragie-backend .
```

2. **Run container:**
```bash
docker run -d \
  --name ragie-backend \
  -p 8000:8000 \
  --env-file .env \
  ragie-backend
```

### Production Checklist

- [ ] Set `DEBUG=false`
- [ ] Use strong `JWT_SECRET_KEY`
- [ ] Configure CORS for your frontend domain
- [ ] Set up Stripe webhook in Stripe dashboard
- [ ] Test Stripe webhook endpoint
- [ ] Enable HTTPS/SSL
- [ ] Set up monitoring/logging
- [ ] Configure rate limiting (if needed)
- [ ] Test user quotas and limits

## Troubleshooting

### Ragie Document Not Processing
- Check Ragie dashboard for status
- Verify file type is supported
- Check Ragie API key is valid
- Review Ragie logs for errors

### Authentication Failures
- Verify JWT token is valid
- Check Supabase URL and key
- Ensure token includes required claims (sub, exp, iat)

### Stripe Webhook Not Working
- Verify webhook URL is correct in Stripe dashboard
- Check webhook secret is configured
- Review Stripe webhook logs
- Ensure endpoint is publicly accessible

### Database Connection Issues
- Verify Supabase URL and key
- Check network connectivity
- Review Supabase logs
- Ensure RLS policies are correct

## Future Enhancements

- [ ] Google Drive/OneDrive integration
- [ ] Webhook notifications for processing completion
- [ ] Advanced filtering with Ragie entities
- [ ] Document summarization display
- [ ] Recency bias in search results
- [ ] Partition-based multi-tenancy
- [ ] Batch document processing

## Resources

- [Ragie Documentation](https://docs.ragie.ai)
- [Ragie Python SDK](https://docs.ragie.ai/docs/ragie-python)
- [Supabase Documentation](https://supabase.com/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [Stripe API Documentation](https://stripe.com/docs/api)

## License

[Add your license here]

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review Ragie, Supabase, or Stripe documentation
3. Check application logs for errors
4. Open an issue with details about the problem
