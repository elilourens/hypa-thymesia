# Hypa-Thymesia (SmartQuery) Project Context

## Overview
Hypa-Thymesia (SmartQuery) is a production-ready multimodal RAG (Retrieval-Augmented Generation) system for knowledge management and intelligent document retrieval. Users upload documents and images (or import from Google Drive/OneDrive), which are processed, embedded, and stored for semantic search and AI-powered chat interactions. The system features automatic image tagging using CLIP and OWL-ViT models, multi-modal search capabilities, and an intelligent RAG chat interface powered by LangGraph.

## Tech Stack

### Backend (Python/FastAPI)
- **Framework**: FastAPI 0.116.1 with Uvicorn 0.35.0
- **Python Version**: >=3.12, <3.13.8
- **Database**: Supabase (PostgreSQL + Auth + Storage)
- **Vector Database**: Pinecone 7.3.0 (3 separate indexes)
- **LLM Orchestration**: LangChain 0.3.26 + LangGraph 0.5.3
- **LLM**: Ollama 0.5.1 (Mistral model, local inference)
- **Embeddings**:
  - Text: all-MiniLM-L12-v2 via sentence-transformers 2.7.0 (384D)
  - Images: CLIP ViT-B-32 via sentence-transformers 3.0.0 (512D)
  - Cross-modal: CLIP text encoder (512D)
- **Image Tagging**:
  - CLIP ViT-B-32 (candidate generation)
  - OWL-ViT via transformers 4.44.2 (zero-shot object detection)
  - 650 curated object labels across 14 categories
- **Document Processing**:
  - PyMuPDF (fitz) 1.26.3 (PDF)
  - python-docx 1.2.0 (DOCX)
  - python-pptx (PowerPoint conversion)
  - Pillow 11.3.0 (images)
  - NLTK 3.9.1 (text processing)
- **Search**: rank-bm25 0.2.2 for hybrid search
- **OAuth**: Google Drive + OneDrive integration with token refresh
- **Utilities**: python-jose 3.5.0, PyJWT 2.10.1, cryptography 45.0.6

### Frontend (Vue/Nuxt)
- **Framework**: Nuxt 4.1.2 + Vue 3.5.18
- **UI**: Nuxt UI 4.0.0 + Tailwind CSS 4.1.12
- **Icons**: @nuxt/icon 2.0.0 + @iconify-json/lucide 1.2.68
- **Auth**: @nuxtjs/supabase 1.6.0
- **AI Chat**: @ai-sdk/vue 2.0.60
- **Dev Tools**: @nuxt/eslint 1.8.0

## Architecture

### Data Flow
```
Upload (Direct/GDrive/OneDrive) → Extract Text/Images → Chunk (800 chars, 20 overlap) → Embed → Store (Pinecone + Supabase)
  ↓ (for uploaded images only)
  Auto-Tag (CLIP → OWL-ViT) → Store Tags

Query → Embed → Pinecone Search (with filters) → BM25 Rerank (optional) → Highlight → Return Results

Chat → LangGraph: list_groups → decide_params → retrieve → answer → Stream Response
```

### Directory Structure
```
backend/
├── main.py                         # FastAPI app entry point with CORS
├── pyproject.toml                  # Poetry dependencies
├── .env                            # Environment configuration
├── routers/                        # API endpoints (13 routers)
│   ├── upload.py                  # File ingestion (/api/v1/ingest/upload-text-and-images)
│   ├── query.py                   # Semantic search (/api/v1/ingest/query)
│   ├── chat.py                    # AI chat interface (/api/v1/chat)
│   ├── groups.py                  # Document organization (/api/v1/groups)
│   ├── files.py                   # File management (/api/v1/files)
│   ├── gdrive.py                  # Google Drive OAuth (/api/v1/google-*)
│   ├── addFromGoogleDrive.py      # GDrive file import (/api/v1/ingest-google-drive-file)
│   ├── onedrive.py                # OneDrive OAuth support
│   ├── addFromOneDrive.py         # OneDrive file import
│   ├── storage.py                 # Storage operations (/api/v1/storage/signed-url)
│   ├── delete.py                  # Deletion operations (/api/v1/ingest/delete-document)
│   ├── tagging.py                 # Image tagging (/api/v1/tag-upload, /images/{id}/tags)
│   ├── user_settings.py           # User settings management
│   └── health.py                  # Health check (/api/v1/health)
├── ingestion/                     # Document processing
│   ├── ingest_common.py           # Unified ingestion logic (handles all file types)
│   └── text/
│       ├── extract_text.py        # Text extraction + chunking (PDF/DOCX/TXT)
│       └── extract_pptx.py        # PowerPoint to PDF conversion
├── embed/                         # Embedding generation
│   ├── text_embedder.py           # Text embeddings (all-MiniLM-L12-v2, 384D)
│   ├── image_embedder.py          # Image embeddings (CLIP ViT-B-32, 512D)
│   ├── clip_text_embedder.py      # CLIP text embeddings (512D)
│   └── embeddings.py              # Unified embedding interface
├── tagging/                       # Image auto-tagging system
│   ├── tag_pipeline.py            # Two-stage CLIP + OWL-ViT pipeline
│   ├── label_embedder.py          # CLIP candidate generation
│   ├── owlvit_detector.py         # OWL-ViT verification
│   ├── background_tasks.py        # Async tagging tasks
│   └── document_tagger.py         # Document-level tagging
├── rag/
│   └── graph.py                   # LangGraph RAG pipeline (4 nodes)
├── data_upload/                   # Storage services
│   ├── pinecone_services.py       # Vector DB operations (upsert, query, delete)
│   ├── supabase_text_services.py  # Text chunk storage
│   ├── supabase_image_services.py # Image storage
│   └── supabase_deep_embed_services.py # Extracted image storage
├── core/
│   ├── security.py                # JWT authentication with JWKS
│   ├── config.py                  # Pydantic settings (env vars)
│   ├── deps.py                    # Dependency injection
│   ├── token_encryption.py        # OAuth token encryption/decryption
│   └── user_limits.py             # Upload quota enforcement
├── schemas/                       # Pydantic request/response models
└── config/
    └── object_labels.json         # 650 curated labels (14 categories)

frontend/
├── nuxt.config.ts                 # Nuxt configuration
├── package.json                   # npm dependencies
├── pages/
│   ├── index.vue                  # Landing page (redirects)
│   ├── login.vue                  # Supabase authentication
│   └── dashboard/
│       ├── index.vue              # Redirects to query
│       ├── query.vue              # Search interface (3 modes: text/image/extracted_image)
│       ├── upload.vue             # File upload with group assignment
│       ├── files.vue              # File browser with filters/sorting/bulk actions
│       ├── ai.vue                 # RAG chat interface
│       ├── link.vue               # Google Drive OAuth + file browser
│       ├── groups.vue             # Group management CRUD
│       └── settings.vue           # User settings
├── components/
│   ├── Header.vue                 # Navigation header
│   ├── BodyCard.vue               # Page layout wrapper
│   ├── GroupSelect.vue            # Group dropdown (all/none/specific)
│   ├── ResultList.vue             # Search results display (text highlights, image tags)
│   ├── GoogleDriveLinkCard.vue    # Google Drive OAuth UI
│   └── OneDriveLinkCard.vue       # OneDrive OAuth UI
├── composables/
│   ├── useIngest.ts               # Upload, query, delete operations
│   ├── useFiles.ts                # File listing with filters
│   ├── useGroups.ts               # Group CRUD
│   ├── useGoogleDrive.ts          # OAuth + Drive file listing
│   ├── useOneDrive.ts             # OneDrive OAuth support
│   ├── useChat.ts                 # Chat message handling
│   └── useQuota.ts                # Quota management
└── middleware/
    └── auth.global.ts             # Protects dashboard routes
```

## Core Features

### 1. Document Ingestion
- **Supported formats**: PDF, DOCX, TXT, MD, PPT, PPTX, PNG, JPEG, JPG, WEBP
- **PowerPoint support**: Converts PPT/PPTX to PDF for processing
- **Deep embedding**: Extracts images from PDFs/DOCX and embeds separately in dedicated index
- **Chunking**: 800 character chunks with 20 character overlap
- **Metadata**: Page numbers, character positions, text previews (180 chars)
- **Google Drive & OneDrive**: OAuth-based import with auto token refresh (downloads to Supabase storage)
- **Auto-tagging**: ONLY for directly uploaded images (disabled for extracted images from documents)
  - Two-stage pipeline: CLIP candidate generation → OWL-ViT verification
  - 650 object labels across 14 categories
  - Stores bounding boxes and confidence scores
- **Quota enforcement**: User upload limits configurable per user

### 2. Multi-Modal Search (3 Modes)
- **Text Search** (`route: "text"`): Semantic text-to-text using all-MiniLM-L12-v2 (384D)
  - BM25 hybrid reranking (configurable weight)
  - Text highlighting with span matching
  - Keyword search mode option
- **Image Search** (`route: "image"`): Text-to-image search using CLIP (512D)
  - Searches uploaded images only
  - Returns auto-detected tags
- **Extracted Image Search** (`route: "extracted_image"`): Text-to-image for document images
  - Searches images extracted from PDFs/DOCX
  - Returns parent document info
- **Tag-Based Search**: Search images by detected tags
  - Filter by minimum confidence
  - Popular tags endpoint for autocomplete
- **Filtering**: By group_id (Pinecone metadata filter)
- **Configurable**: Top-K results (1-50), BM25 weight (0-1)

### 3. AI Chat Assistant (RAG)
- **Agent-based**: LangGraph orchestrates 4-node workflow
  1. **list_groups**: Fetch available groups from API
  2. **decide_params**: LLM selects query_text, top_k, group_id, bm25_weight
  3. **retrieve**: Call query endpoint with selected parameters
  4. **answer**: Generate response using Ollama (Mistral)
- **Query simplification**: Removes filler words for better retrieval
- **BM25 re-ranking**: Improves retrieval quality
- **Context windowing**: 50,000 char preview limit
- **Streaming**: Real-time responses via Ollama

### 4. Image Auto-Tagging System
- **Two-Stage Pipeline**:
  1. **CLIP Filtering** (fast):
     - Embed 650 object labels using CLIP text encoder
     - Cosine similarity with image embedding
     - Top-15 candidates (min confidence: 0.15)
  2. **OWL-ViT Verification** (precise):
     - Zero-shot object detection for each candidate
     - Returns bounding boxes + confidence scores
     - Min confidence: 0.15
     - Only verified detections stored
- **Label Categories** (650 labels):
  - People & Animals, Furniture, Electronics, Office Items
  - Charts & Diagrams, Nature, Buildings, UI Elements
  - Food & Drink, Transportation, Clothing, Sports
  - Household Items, Medical, Tools, Art, Music
- **Storage**: app_image_tags table with chunk_id, tag_name, confidence, bbox
- **Search**: Tag-based search endpoint (`/search/by-tags`)
- **IMPORTANT**: Auto-tagging is ONLY enabled for directly uploaded images
  - Disabled for images extracted from PDFs/DOCX (performance optimization)

### 5. Organization
- **Groups**: Create, rename, delete document collections
- **Assignment**: Assign/clear document groups via PUT endpoint
- **Metadata sync**: Updates both Supabase (app_doc_meta) and Pinecone metadata
- **Namespacing**: Multi-tenant isolation by user_id
- **Cascade behavior**: ON DELETE SET NULL for group deletion

### 6. Storage Architecture
- **Supabase Storage**: 3 buckets
  - `documents`: PDFs, DOCX, TXT, MD, PPT, PPTX files
  - `images`: Directly uploaded images
  - `extracted-images`: Images extracted from PDFs/DOCX
- **Pinecone Indexes**: 3 separate indexes (avoids dimension conflicts)
  - Text index (384D): all-MiniLM-L12-v2 embeddings
  - Image index (512D): CLIP embeddings for uploaded images
  - Extracted image index (512D): CLIP embeddings for document images
- **Database Tables**:
  - `app_docs`: Document metadata (doc_id, user_id, filename, created_at)
  - `app_doc_meta`: Extended metadata with group_id (FK to app_groups ON DELETE SET NULL)
  - `app_chunks`: Text/image chunks (modality, storage_path, bucket, mime_type, size_bytes)
  - `app_vector_registry`: Maps vector_id to chunk_id (CASCADE DELETE)
  - `app_groups`: User-defined groups (group_id, user_id, name, sort_index)
  - `app_image_tags`: Auto-detected tags (chunk_id, tag_name, confidence, verified, bbox)
  - `user_oauth_tokens`: Google/OneDrive OAuth tokens (provider, access_token, refresh_token, expires_at)
  - `user_settings`: User quotas and preferences (max_files, current_count)
- **Database Views**:
  - `app_docs_with_group`: Joins chunks with doc_meta for efficient file listing

### 7. Security
- **Authentication**: Supabase JWT with JWKS validation
- **User isolation**: All data namespaced by user_id (Pinecone namespace + DB filters)
- **OAuth**: Secure Google/OneDrive token storage with automatic refresh (5-minute buffer)
- **Token encryption**: OAuth tokens encrypted in database
- **CORS**: Configured for Nuxt frontend in main.py
- **Signed URLs**: 1-hour expiry for storage access

## Key Implementation Details

### Embedding Strategy
- **Text chunks**: all-MiniLM-L12-v2 (sentence-transformers) for semantic text search
- **Uploaded images**: CLIP ViT-B-32 image encoder for image-to-image similarity
- **Extracted document images**: CLIP ViT-B-32 for cross-modal text-to-image search
- **Multi-index**: 3 separate Pinecone indexes prevent dimension conflicts (384D vs 512D)

### Chunking Strategy
```python
chunk_size = 800  # characters
overlap = 20      # characters
# Metadata: page_number, char_start, char_end, preview (180 chars)
```

### Search Modes (3 Routes)
1. **text**: Search text chunks with text query (all-MiniLM embeddings)
   - BM25 hybrid reranking
   - Text highlighting with span matching
   - Keyword search mode option
2. **image**: Search uploaded images with text query (CLIP text→image)
   - Returns auto-detected tags
3. **extracted_image**: Search document-extracted images with text query (CLIP)
   - Returns parent document info

### RAG Pipeline (LangGraph)
```
State: {
  messages: List[BaseMessage]
  group_names: List[str]
  parameters: Dict  # query_text, top_k, group_id, bm25_weight
  document_preview: str
  answer: str
}

Nodes:
  list_groups → decide_params → retrieve → answer

Tools:
  - groups_tool: GET /api/v1/groups
  - retriever_tool: POST /api/v1/ingest/query
```

### Highlight Algorithm
Custom text span matching algorithm to highlight relevant portions in search results:
- Finds word boundaries
- Matches query terms
- Returns character spans (start, end)

### Google Drive Integration
- **OAuth 2.0 flow**: Frontend handles redirect, backend stores tokens
- **Token refresh**: Automatic refresh using refresh_token (5-minute expiry buffer)
- **File listing**: Public folder only, non-recursive
- **Download flow**: Multiple fallback methods for large files (handles virus scan confirmation)
- **Storage**: Downloads to Supabase storage, then standard ingestion pipeline

### OneDrive Integration
- **OAuth 2.0 flow**: Similar to Google Drive implementation
- **Token storage**: Encrypted in user_oauth_tokens table with provider field
- **Token refresh**: Automatic refresh before API calls

### Auto-Tagging Configuration
- **CLIP thresholds**: 0.15 min confidence (lowered for better recall)
- **OWL-ViT thresholds**: 0.15 min confidence
- **Top-K candidates**: 15
- **Background processing**: asyncio.create_task() for non-blocking
- **Scope**: ONLY uploaded images (not extracted images from documents)

## API Routes (All under /api/v1/)

### Ingestion & Upload
- `POST /ingest/upload-text-and-images`: Upload and ingest files
  - Parameters: file, group_id (optional), extract_deep_embeds (bool)
- `POST /ingest-google-drive-file`: Import from Google Drive
  - Parameters: google_drive_id, google_drive_url, filename, mime_type, size_bytes, group_id, extract_deep_embeds

### Search & Query
- `POST /ingest/query`: Semantic search (3 modes)
  - Parameters: query_text OR image_b64, route (text/image/extracted_image), top_k, group_id, bm25_weight

### Chat
- `POST /chat`: RAG chat with LangGraph
  - Parameters: question
  - Returns: answer, sources

### Files
- `GET /files`: List files with pagination/filters/sorting
  - Filters: filename, modality, date range, size range, group
  - Sorting: name, size, created_at
- `DELETE /ingest/delete-document`: Delete document
  - Deletes from 3 Pinecone indexes, Supabase storage, and database

### Groups
- `GET /groups`: List all user groups
- `POST /groups`: Create new group
- `PATCH /groups/{group_id}`: Rename group
- `DELETE /groups/{group_id}`: Delete group (sets doc group_id to NULL)
- `PUT /docs/{doc_id}/group`: Assign/clear document group
  - Syncs to Pinecone metadata

### Storage
- `GET /storage/signed-url`: Generate 1-hour signed URL
  - Parameters: bucket, path

### Google Drive
- `POST /save-google-token`: Save OAuth tokens
- `GET /google-linked`: Check if Google account is linked
- `GET /google-drive-files`: List files from public folder (with pagination)
- `DELETE /unlink-google`: Unlink Google account and revoke tokens

### Tagging
- `POST /tag-upload`: Manually trigger auto-tagging
  - Parameters: file (image)
- `GET /images/{chunk_id}/tags`: Get tags for an image
- `POST /search/by-tags`: Search images by tags
  - Parameters: tags (list), min_confidence, limit
- `GET /tags/popular`: Get most frequent tags
  - Parameters: limit, verified_only

### User Settings
- User quota and preference management endpoints

### Health
- `GET /health`: Health check endpoint

## Environment Variables

### Backend (.env)
```bash
# Supabase
SUPABASE_URL=
SUPABASE_KEY=

# Pinecone
PINECONE_API_KEY=
PINECONE_ENVIRONMENT=
PINECONE_TEXT_INDEX_NAME=
PINECONE_IMAGE_INDEX_NAME=
PINECONE_EXTRACTED_IMAGE_INDEX_NAME=

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# OneDrive OAuth (optional)
ONEDRIVE_CLIENT_ID=
ONEDRIVE_CLIENT_SECRET=

# Ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=mistral

# Embedding Dimensions
TEXT_EMBED_DIM=384
IMAGE_EMBED_DIM=512
DEEP_IMAGE_EMBED_DIM=512

# Buckets
TEXT_BUCKET=documents
EXTRACTED_IMAGES_BUCKET=extracted-images

# RAG Settings
RETRIEVER_URL=http://localhost:8000/api/v1/ingest/query
GROUPS_URL=http://localhost:8000/api/v1/groups
DOC_PREVIEW_CHARS=50000

# Pinecone Settings
PINECONE_MAX_BATCH=100

# User Limits
USER_UPLOAD_LIMIT=1000
```

### Frontend (.env)
```bash
SUPABASE_URL=
SUPABASE_KEY=
NUXT_PUBLIC_API_BASE=http://127.0.0.1:8000/api/v1
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
Managed via Supabase MCP server tools (available in Claude Code)

### Model Loading
- Embedding models loaded on-demand in routers (cached in memory)
- Ollama must be running locally for chat (`ollama serve`)
- CLIP and OWL-ViT models downloaded from HuggingFace on first use

## Common Workflows

### File Upload Flow (Direct)
1. User uploads file via `/dashboard/upload.vue`
2. Frontend sends FormData to `/api/v1/ingest/upload-text-and-images`
3. Backend determines file type (image vs document)
4. Upload to Supabase storage (images/ or documents/ bucket)
5. **IF IMAGE**:
   - Generate CLIP embedding (512D)
   - Store in app_chunks, app_doc_meta, app_vector_registry
   - Upsert to Pinecone image index
   - **Trigger background auto-tagging**:
     - CLIP generates top-15 candidate labels
     - OWL-ViT verifies and localizes objects
     - Store verified tags in app_image_tags
6. **IF DOCUMENT**:
   - Extract text chunks (800 chars, 20 overlap)
   - Optionally extract images (if extract_deep_embeds=true)
   - Generate text embeddings (all-MiniLM, 384D)
   - Generate image embeddings (CLIP, 512D) for extracted images
   - Store chunks and metadata in database
   - Upsert text vectors to Pinecone text index
   - Upsert image vectors to Pinecone extracted_image index
   - **NO auto-tagging for extracted images**
7. Return doc_id and ingestion stats

### File Upload Flow (Google Drive/OneDrive)
1. User links account via OAuth (frontend handles redirect)
2. Frontend saves tokens via `/api/v1/save-google-token`
3. User browses files → `/api/v1/google-drive-files`
4. Backend fetches files (auto-refreshes expired tokens)
5. User selects file → `/api/v1/ingest-google-drive-file`
6. Backend:
   - Download file from cloud storage
   - Upload to Supabase storage
   - Follow standard ingestion pipeline (same as direct upload)

### Search Flow (All Modalities)
1. User enters query in `/dashboard/query.vue`
2. Select route (text/image/extracted_image) and optional group filter
3. Frontend calls `POST /api/v1/ingest/query`
4. Backend:
   - **IF route=text**:
     - Generate text embedding (all-MiniLM, 384D)
     - Query Pinecone text index
     - BM25 reranking based on text content (if enabled)
     - Add highlighting spans
   - **IF route=image**:
     - Generate CLIP text embedding (512D)
     - Query Pinecone image index
     - Fetch tags from app_image_tags
   - **IF route=extracted_image**:
     - Generate CLIP text embedding (512D)
     - Query Pinecone extracted_image index
     - Return with parent doc info
   - Apply group_id filter (Pinecone metadata)
5. Return matches with metadata
6. Frontend displays results:
   - Text: Highlighted snippets
   - Images: Preview + auto-detected tags
   - Extracted images: Preview + parent doc info

### Chat Flow
1. User sends message in `/dashboard/ai.vue`
2. Frontend calls `POST /api/v1/chat`
3. Backend LangGraph pipeline:
   - **Node 1: list_groups** → Fetch user's groups from `/api/v1/groups`
   - **Node 2: decide_params** → LLM analyzes question + available groups
     - Selects: query_text, top_k, group_id, bm25_weight
     - Cleans query (removes filler words)
   - **Node 3: retrieve** → Call `/api/v1/ingest/query` with selected params
   - **Node 4: answer** → LLM generates answer using retrieved context
     - Prompt: Use context only if relevant
4. Return: { answer: "...", sources: {...} }
5. Frontend displays answer with streaming

### Group Management Flow
1. Create group in `/dashboard/groups.vue` → `POST /api/v1/groups`
2. Assign documents to group → `PUT /api/v1/docs/{doc_id}/group`
3. Backend:
   - Update app_doc_meta table (group_id)
   - Update Pinecone metadata for all vectors (across all 3 indexes)
4. Use group filter in search/chat (Pinecone metadata filter)

### Tagging Flow (Auto)
1. Image uploaded (direct upload only)
2. Ingestion completes → `asyncio.create_task(tag_image_background)`
3. Background task:
   - **Stage 1: CLIP Filtering**
     - Load 650 object labels from config/object_labels.json
     - Embed labels using CLIP text encoder
     - Cosine similarity with image embedding
     - Select top-15 candidates (confidence > 0.15)
   - **Stage 2: OWL-ViT Verification**
     - Download image from Supabase storage
     - Run OWL-ViT zero-shot detection for each candidate
     - Keep detections with confidence > 0.15
     - Extract bounding boxes
   - Store verified tags in app_image_tags
4. Tags available for:
   - Search results display
   - Tag-based search (`/search/by-tags`)
   - Popular tags autocomplete

## Known Patterns

### Smart Variable Names
Use descriptive variable names (e.g., `embed_text_vectors`, `chunk_id`)

### Multi-Index Strategy
- 3 separate Pinecone indexes: Text (384D) + Image (512D) + Extracted Image (512D)
- Prevents dimension conflicts
- Enables modality-specific search

### User Isolation
- All queries filtered by user_id from JWT token
- Pinecone namespace = user_id
- Database queries always include user_id filter

### Error Handling
- FastAPI HTTPException with appropriate status codes
- Try-except blocks with logging
- Graceful degradation (e.g., continue if tagging fails)

### CORS
Configured for Nuxt frontend in main.py

### Group Metadata Sync
- Groups stored in Supabase (app_groups)
- group_id synced to Pinecone metadata for filtering
- ON DELETE SET NULL for group deletion (documents remain)

### Background Processing
- Image tagging: asyncio.create_task() for non-blocking
- Token refresh: synchronous before API calls

## Architectural Decisions

### 1. Three Separate Pinecone Indexes
**Rationale**: Avoids dimension mismatch issues (384D vs 512D), better organization, enables modality-specific search

### 2. Dual Storage (Supabase + Pinecone)
**Rationale**:
- Supabase: Source of truth for metadata, file storage, user data
- Pinecone: Vector search with metadata filtering
- app_vector_registry: Links the two systems

### 3. Background Tagging (Uploaded Images Only)
**Rationale**:
- Non-blocking user experience
- Disabled for extracted images to reduce processing time
- Two-stage pipeline ensures high precision (OWL-ViT verification)

### 4. Group Metadata Sync
**Rationale**:
- Groups stored in Supabase for easy CRUD
- group_id synced to Pinecone for efficient filtering during search
- ON DELETE SET NULL prevents cascading deletions

### 5. LangGraph for RAG
**Rationale**:
- Agent-based query planning
- Automatic group selection based on user question
- Query simplification for better retrieval

### 6. Cloud Storage → Supabase Flow
**Rationale**:
- Download file from cloud storage, upload to Supabase storage
- Ensures data ownership and persistence
- Standard ingestion pipeline (not direct cloud references)

### 7. CLIP + OWL-ViT Two-Stage Tagging
**Rationale**:
- CLIP: Fast candidate generation (650 labels in <100ms)
- OWL-ViT: Precise verification with localization (bounding boxes)
- Balances speed and accuracy

### 8. PowerPoint Conversion
**Rationale**:
- Converts PPT/PPTX to PDF for consistent processing
- Reuses existing PDF extraction pipeline
- Maintains original file reference

## Future Context Tips

1. **When modifying search**: Check all 3 embedding types + BM25 logic in [query.py](backend/routers/query.py)
2. **When adding file types**: Update SUPPORTED_TEXT/SUPPORTED_IMAGES in [ingest_common.py](backend/ingestion/ingest_common.py)
3. **When changing chunking**: Update [extract_text.py](backend/ingestion/text/extract_text.py) + re-ingest all documents
4. **When modifying chat**: Check [rag/graph.py](backend/rag/graph.py) LangGraph state machine (4 nodes)
5. **When adding routes**: Add to respective router + register in [main.py](backend/main.py)
6. **Security**: Always validate JWT and filter by user_id
7. **Embeddings**: Match dimensions to Pinecone index (384D for text, 512D for images)
8. **Cloud storage**: Handle token refresh in [gdrive.py](backend/routers/gdrive.py) and onedrive.py (5-minute buffer)
9. **Auto-tagging**: Only enabled for uploaded images (configurable in [ingest_common.py](backend/ingestion/ingest_common.py))
10. **Database schema changes**: Use Supabase MCP tools for migrations
11. **PowerPoint files**: Automatically converted to PDF, then processed as PDFs

## Recent Changes (Last 5 Commits)

1. **f37653f**: "formatting?"
   - Code formatting improvements

2. **141eafe**: "docka"
   - Docker configuration updates

3. **5b81bfa**: "security fixes"
   - Security improvements and patches

4. **9fe7c5f**: "check if image is entirely one color"
   - Image validation improvements

5. **fe5371b**: "ppt support"
   - PowerPoint file support implementation

## Current Status
- ✅ Core functionality complete and production-ready
- ✅ Multi-modal search working (3 modes)
- ✅ RAG chat implemented with LangGraph
- ✅ Google Drive + OneDrive integration active with OAuth
- ✅ Group management functional with Pinecone sync
- ✅ Auto-tagging system (CLIP + OWL-ViT) for uploaded images
- ✅ PowerPoint support with PDF conversion
- ⚠️ Auto-tagging disabled for extracted images from PDFs/DOCX
- 📝 Modified files: [backend/ingestion/text/extract_text.py](backend/ingestion/text/extract_text.py) (uncommitted changes)

## Known Limitations

1. **Google Drive**: Only public folder access (non-recursive)
2. **Auto-tagging**: Disabled for images extracted from documents (performance optimization)
3. **LLM**: Requires local Ollama server running
4. **Token limits**: RAG context limited to 50,000 chars
5. **File size**: No explicit size limits configured (handled by Supabase)
6. **PowerPoint**: Requires conversion to PDF (may lose some formatting)
