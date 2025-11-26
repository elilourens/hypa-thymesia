# Hypa-Thymesia Project Context

## Overview
Hypa-Thymesia is a multimodal AI-powered knowledge management and retrieval system. Users upload documents and images, which are processed, embedded, and stored for semantic search and AI-powered chat interactions. The name references "hyperthymesia" - exceptional autobiographical memory.

## Tech Stack

### Backend (Python/FastAPI)
- **Framework**: FastAPI 0.116.1 with Uvicorn
- **Database**: Supabase (PostgreSQL + Auth + Storage)
- **Vector Database**: Pinecone (separate indexes for text, images, CLIP)
- **LLM Orchestration**: LangChain 0.3.26 + LangGraph 0.5.3
- **LLM**: Ollama (Mistral model, local inference)
- **Embeddings**:
  - Text: sentence-transformers (384D)
  - Images: torchvision (512D)
  - Cross-modal: CLIP via open-clip-torch (512D)
- **Document Processing**: PyMuPDF (PDF), python-docx (DOCX), NLTK
- **Search**: rank-bm25 for hybrid search
- **OAuth**: Google Drive integration with token refresh

### Frontend (Vue/Nuxt)
- **Framework**: Nuxt 4.1.2 + Vue 3.5.18
- **UI**: Nuxt UI 4.0.0 + Tailwind CSS 4.1.12
- **Auth**: @nuxtjs/supabase 1.6.0
- **AI Chat**: @ai-sdk/vue 2.0.60

## Architecture

### Data Flow
```
Upload → Extract Text/Images → Chunk (800 chars) → Embed → Store (Pinecone + Supabase)
Query → Embed → Pinecone Search → BM25 Rerank → Highlight → Return Results
Chat → Agent Plans Query → Retrieve Context → LLM Generate → Stream Response
```

### Directory Structure
```
backend/
├── main.py                    # FastAPI app entry point
├── routers/                   # API endpoints
│   ├── upload.py             # File ingestion
│   ├── query.py              # Semantic search
│   ├── chat.py               # AI chat interface
│   ├── groups.py             # Document organization
│   ├── files.py              # File management
│   ├── gdrive.py             # Google Drive OAuth
│   ├── addFromGoogleDrive.py # GDrive file import
│   ├── storage.py            # Storage operations
│   └── delete.py             # Deletion operations
├── ingestion/                # Document processing
│   ├── ingest_common.py      # Unified ingestion logic
│   └── text/extract_text.py  # Text extraction + chunking
├── embed/                    # Embedding generation
│   ├── text_embedder.py      # Text embeddings (384D)
│   ├── image_embedder.py     # Image embeddings (512D)
│   ├── clip_text_embedder.py # CLIP text embeddings (512D)
│   └── embeddings.py         # Unified interface
├── rag/
│   └── graph.py              # LangGraph RAG pipeline
├── data_upload/              # Storage services
│   ├── pinecone_services.py  # Vector DB operations
│   ├── supabase_text_services.py
│   ├── supabase_image_services.py
│   └── supabase_deep_embed_services.py
└── core/
    ├── security.py           # JWT authentication
    ├── config.py             # Environment config
    └── deps.py               # Dependency injection

frontend/
├── pages/dashboard/
│   ├── query.vue             # Search interface (3 modes)
│   ├── ai.vue                # Chat interface
│   ├── upload.vue            # File upload
│   ├── files.vue             # File management
│   ├── groups.vue            # Group organization
│   ├── link.vue              # Google Drive linking
│   └── settings.vue          # User settings
├── components/
│   ├── GroupSelect.vue       # Group dropdown
│   ├── ResultList.vue        # Search results with highlighting
│   ├── BodyCard.vue          # Layout wrapper
│   └── header.vue            # Navigation
└── composables/
    ├── useIngest.ts          # Query/upload operations
    ├── useChat.ts            # Chat handling
    └── useGroups.ts          # Group management
```

## Core Features

### 1. Document Ingestion
- **Supported formats**: PDF, DOCX, TXT, MD, PNG, JPEG, WEBP
- **Deep embedding**: Extracts images from PDFs/DOCX and embeds separately
- **Chunking**: 800 character chunks with 20 character overlap
- **Metadata**: Page numbers, character positions, text previews
- **Google Drive**: OAuth-based import with auto token refresh

### 2. Multi-Modal Search (3 Modes)
- **Text Search**: Semantic text-to-text (384D embeddings)
- **Image Search**: Image-to-image similarity (512D embeddings)
- **Document Images**: Search extracted images from docs (CLIP 512D)
- **Hybrid**: Combines vector similarity + BM25 keyword matching
- **Highlighting**: Finds and highlights matching text spans
- **Filtering**: Search within specific groups
- **Configurable**: Top-K results (1-5)

### 3. AI Chat Assistant (RAG)
- **Agent-based**: LangGraph orchestrates multi-step workflow
  1. Lists available groups
  2. Agent decides query parameters
  3. Retrieves relevant documents
  4. Generates answer with Ollama
- **Query simplification**: Removes filler words
- **BM25 re-ranking**: Improves retrieval quality
- **Context windowing**: 50,000 char preview limit
- **Streaming**: Real-time responses

### 4. Organization
- **Groups**: Create, rename, delete document collections
- **Assignment**: Add/remove documents from groups
- **Metadata sync**: Updates both Supabase + Pinecone
- **Namespacing**: Multi-tenant by user_id

### 5. Storage Architecture
- **Supabase Storage**: Primary file storage buckets
- **Pinecone Indexes**:
  - Text index (384D)
  - Image index (512D)
  - Extracted image index (512D, CLIP)
- **Database Tables**:
  - `app_docs`: Document metadata
  - `app_chunks`: Text/image chunks
  - `app_vector_registry`: Vector ID tracking
  - `app_groups`: User-defined groups
  - `app_doc_meta`: Document-group associations
  - `user_oauth_tokens`: Google OAuth tokens

### 6. Security
- **Authentication**: Supabase JWT with JWKS validation
- **User isolation**: All data namespaced by user_id
- **OAuth**: Secure Google token storage with refresh

## Key Implementation Details

### Embedding Strategy
- **Text chunks**: Use sentence-transformers for semantic text search
- **Uploaded images**: Use torchvision ResNet for image similarity
- **Extracted document images**: Use CLIP for cross-modal text-to-image search
- **Multi-index**: Separate Pinecone indexes prevent dimension conflicts

### Chunking Strategy
```python
chunk_size = 800  # characters
overlap = 20      # characters
```

### Search Modes
1. **text**: Search text chunks with text query
2. **image**: Search uploaded images with image query
3. **extracted_image**: Search document-extracted images with text query (CLIP)

### RAG Pipeline (LangGraph)
```
State: messages, group_names, parameters, document_preview, answer
Steps: list_groups → agent_decide → retrieve_chunks → generate_answer
```

### Highlight Algorithm
Custom text span matching to highlight relevant portions in search results

### Google Drive Integration
- OAuth 2.0 flow with offline access
- Token storage in Supabase
- Auto-refresh on expiry
- File metadata caching

## API Routes (All under /api/v1/)

- `POST /upload`: Upload and ingest files
- `POST /query`: Semantic search
- `POST /chat`: Chat with AI
- `GET /groups`: List groups
- `POST /groups`: Create group
- `PATCH /groups/{id}`: Rename group
- `DELETE /groups/{id}`: Delete group
- `POST /groups/{id}/docs`: Add doc to group
- `DELETE /groups/{id}/docs/{doc_id}`: Remove doc from group
- `GET /files`: List files
- `DELETE /delete/{doc_id}`: Delete document
- `GET /gdrive/authorize`: Start OAuth flow
- `GET /gdrive/callback`: OAuth callback
- `POST /gdrive/add`: Import from Drive
- `GET /storage/buckets`: List buckets
- `GET /health`: Health check

## Environment Variables
```
SUPABASE_URL
SUPABASE_KEY
SUPABASE_JWT_SECRET
PINECONE_API_KEY
PINECONE_ENVIRONMENT
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
FRONTEND_URL
```

## Development Notes

### Running Backend
```bash
cd backend
poetry install
poetry run uvicorn main:app --reload
```

### Running Frontend
```bash
cd frontend
npm install
npm run dev
```

### Database Migrations
Managed via Supabase MCP server tools

### Model Loading
- Embedding models loaded on-demand in routers
- Ollama must be running locally for chat
- Models cached in memory after first load

## Common Workflows

### File Upload Flow
1. User uploads file via `/upload.vue`
2. Backend extracts text + images
3. Chunks text (800 chars)
4. Generates embeddings
5. Stores in Pinecone + Supabase
6. Returns doc_id

### Search Flow
1. User enters query in `/query.vue`
2. Select mode (text/image/extracted_image)
3. Backend embeds query
4. Searches Pinecone
5. BM25 re-ranks results
6. Highlights matching spans
7. Returns ranked results

### Chat Flow
1. User sends message in `/ai.vue`
2. LangGraph agent analyzes query
3. Retrieves relevant chunks from Pinecone
4. Formats context (50k char limit)
5. Ollama generates streaming response
6. Frontend displays with markdown

### Group Management Flow
1. Create group in `/groups.vue`
2. Assign documents to group
3. Metadata updated in Supabase + Pinecone
4. Use group filter in search/chat

## Known Patterns

### Smart Variable Names
Per CLAUDE.md: Use descriptive variable names

### Multi-Index Strategy
Text (384D) + Image (512D) + CLIP (512D) in separate Pinecone indexes

### User Isolation
All queries filtered by user_id from JWT token

### Error Handling
FastAPI HTTPException with appropriate status codes

### CORS
Configured for Nuxt frontend in main.py

## Future Context Tips

1. **When modifying search**: Check all 3 embedding types + BM25 logic
2. **When adding file types**: Update ingestion/ingest_common.py
3. **When changing chunking**: Update extract_text.py + re-ingest
4. **When modifying chat**: Check rag/graph.py LangGraph state machine
5. **When adding routes**: Add to respective router + update main.py
6. **Security**: Always validate JWT and filter by user_id
7. **Embeddings**: Match dimensions to Pinecone index (384D/512D)
8. **Google Drive**: Handle token refresh in gdrive.py

## Current Status
- ✅ Core functionality complete
- ✅ Multi-modal search working
- ✅ RAG chat implemented
- ✅ Google Drive integration active
- ✅ Group management functional
- 📝 Untracked: `.claude/` directory (per git status)
