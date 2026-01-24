# Frontend Migration Guide: Old Backend → Backend-Ragie

This document describes the API changes required to migrate the frontend from the old backend to the new **backend-ragie** architecture.

## Overview

The new backend-ragie is significantly simpler and more unified:
- **Single upload endpoint** for all file types (text, images, videos, documents)
- **Unified semantic search** instead of separate search routes
- **No tagging system** (Ragie handles entity extraction internally)
- **Simplified file processing** (pending → ready status flow)
- **Same Supabase authentication**
- **Same Stripe integration**

## Key Changes

### 1. Upload Endpoints

**Old Backend:**
```javascript
// Different endpoints for different file types
uploadFile(file, groupId)           // POST /ingest/upload-text-and-images
uploadVideo(file, groupId)          // POST /ingest/upload-video
```

**New Backend (Backend-Ragie):**
```javascript
uploadDocument(file, groupId)       // POST /documents/upload (all file types)
```

All file types (text, images, videos, PDFs, audio, etc.) go to the same endpoint.

### 2. Search Endpoints

**Old Backend:**
```javascript
// Multiple routes for different content types
queryText(query, route, top_k, group_id)      // POST /ingest/query with route
queryImage(imageFile, top_k, group_id)        // POST /ingest/query with image
queryVideo(query, route, top_k, group_id)     // POST /ingest/query-video
queryByTags(tags, category, group_id)         // POST /tagging/search/by-document-tags
queryImagesByTags(tags, group_id)             // POST /tagging/search/by-tags
```

Routes available: `text`, `image`, `extracted_image`, `video_frames`, `video_transcript`, `video_combined`

**New Backend (Backend-Ragie):**
```javascript
search(query, top_k, rerank, group_id)        // POST /search/retrieve
```

Single unified endpoint. Ragie handles all content types in one search.

### 3. Processing Status

**Old Backend:**
```javascript
getProcessingStatus(docId)          // Returns: queued, processing, completed, failed
pollProcessingStatus(docId)         // With onUpdate callback
```

**New Backend (Backend-Ragie):**
```javascript
getDocumentStatus(docId)            // Returns: pending, partitioning, ..., ready, failed
pollDocumentStatus(docId)           // With onUpdate callback
```

Status values:
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

### 4. File Listing

**Old Backend:**
```javascript
listFiles(params: {
  q: string,              // search query
  modality: 'text' | 'image' | 'audio' | 'video',
  created_from: string,
  created_to: string,
  min_size: number,
  max_size: number,
  sort: 'created_at' | 'size' | 'name',
  dir: 'asc' | 'desc',
  page: number,
  page_size: number,
  recent: boolean,
  group_id: string,
  group_sort: 'none' | 'group_then_time'
})
```

**New Backend (Backend-Ragie):**
```javascript
listDocuments(params: {
  page: number,
  page_size: number,
  group_id: string,
  sort: 'created_at' | 'filename',
  dir: 'asc' | 'desc'
})
```

The new backend doesn't support filtering by:
- Text search (`q`)
- Modality type
- Date range
- File size
- Complex sorting

Use the search endpoint instead of client-side filtering.

### 5. File Storage

**Old Backend:**
- Files stored in Supabase Storage buckets
- Required getting signed URLs via `/storage/signed-url` endpoint
- Required `/storage/video-info` endpoint for video playback

**New Backend (Backend-Ragie):**
- Files stored by Ragie (no local storage)
- No signed URLs needed
- Content accessed through search results only

Remove usage of `getSignedUrl()` and `getThumbnailUrl()` from useFiles.ts.

### 6. Quota System

**Old Backend:**
```javascript
getQuota()                          // GET /user/quota
updateMaxFiles(maxFiles)            // PATCH /user/max-files
calculateVideoTokens(durationSeconds) // Video files use tokens, not file count
```

**New Backend (Backend-Ragie):**
```javascript
getQuota()                          // GET /user-settings/quota-status
// No updateMaxFiles - handled by Stripe webhook
// No video tokens - simple file count
```

Quota is now:
- Simple file count (not tokens)
- Updated automatically via Stripe webhook
- 50 files free tier, 100 files premium

### 7. Groups Management

**Old Backend:**
- Managed via Supabase directly in some cases
- Some group functionality in useGroups.ts

**New Backend (Backend-Ragie):**
```javascript
createGroup(name, sortIndex)        // POST /groups/create
listGroups()                         // GET /groups/list
getGroup(groupId)                   // GET /groups/{group_id}
updateGroup(groupId, name, sortIndex) // PUT /groups/{group_id}
deleteGroup(groupId)                // DELETE /groups/{group_id}
```

Use the new `useGroupsApi()` composable for all group operations.

### 8. Stripe Integration

**No changes** - Stripe endpoints remain the same:
- `POST /stripe/create-checkout-session`
- `GET /stripe/subscription-status`
- `POST /stripe/cancel-subscription`
- `POST /stripe/webhook` (backend only)

Updated `useStripe.ts` to use `API_BASE` environment variable instead of hardcoded URL.

### 9. Deleted Features

The following features are **not available** in backend-ragie:

1. **Tagging System**
   - No manual tags
   - No tag-based search
   - Ragie includes automatic entity extraction (internal)

2. **Search Filters**
   - No text search across all documents
   - No modality filtering
   - No date range filtering
   - No file size filtering

3. **Storage Integration**
   - No Google Drive sync (planned for future)
   - No OneDrive sync (planned for future)
   - No local file signed URLs

4. **Video-Specific Features**
   - No video token calculation
   - Videos processed like any other file
   - Single query endpoint covers video transcripts, frames, etc.

## Migration Steps

### Step 1: Update Environment Configuration

Update [.env](.env) with Supabase credentials:

```env
SUPABASE_URL=https://yfovsxfzlkzvfojukzdv.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

NUXT_PUBLIC_API_BASE=http://127.0.0.1:8000/api/v1
```

### Step 2: Replace Composables

**Create new composables** (already done for you):
- `useDocuments.ts` - Document upload, list, status
- `useSearch.ts` - Unified semantic search
- `useGroupsApi.ts` - Group management
- Updated `useStripe.ts` - Uses environment variable

**These are deprecated** and should be removed or updated:
- `useIngest.ts` - Old upload/search/tagging
- `useFiles.ts` - Old file listing and storage operations
- `useGroups.ts` - Replaced by useGroupsApi.ts

### Step 3: Update Components

#### Document Upload

**Old:**
```javascript
import { useIngest } from '@/composables/useIngest'
const { uploadFile, uploadVideo } = useIngest()

// Different calls for different types
await uploadFile(file, groupId)
await uploadVideo(videoFile, groupId)
```

**New:**
```javascript
import { useDocuments } from '@/composables/useDocuments'
const { uploadDocument, pollDocumentStatus } = useDocuments()

// Single call for all types
const doc = await uploadDocument(file, groupId)
await pollDocumentStatus(doc.id, (status) => {
  console.log('Status:', status.status)
})
```

#### Document Search

**Old:**
```javascript
import { useIngest } from '@/composables/useIngest'
const { queryText, queryImage, queryVideo } = useIngest()

// Different calls for different content types
const results = await queryText({
  query: 'search term',
  route: 'text',
  top_k: 10,
  group_id: groupId
})
```

**New:**
```javascript
import { useSearch } from '@/composables/useSearch'
const { search } = useSearch()

// Single call covers all content types
const results = await search({
  query: 'search term',
  top_k: 10,
  group_id: groupId,
  rerank: true
})
```

#### File Listing

**Old:**
```javascript
import { useFilesApi } from '@/composables/useFiles'
const { listFiles } = useFilesApi()

const files = await listFiles({
  q: 'search',
  modality: 'video',
  sort: 'created_at'
})
```

**New:**
```javascript
import { useDocuments } from '@/composables/useDocuments'
const { listDocuments } = useDocuments()

// Simple listing, use search() for filtering
const files = await listDocuments({
  page: 1,
  page_size: 20,
  sort: 'created_at'
})
```

#### Group Management

**Old:**
```javascript
import { useGroups } from '@/composables/useGroups'
const { createGroup, listGroups } = useGroups()
```

**New:**
```javascript
import { useGroupsApi } from '@/composables/useGroupsApi'
const { createGroup, listGroups } = useGroupsApi()
```

### Step 4: Update Pages

Update all pages that use document features:
- Search page - Use new `useSearch()` composable
- Upload page - Use new `useDocuments()` composable
- File browser - Use new `useDocuments()` for listing
- Settings - Groups still work but use new API

### Step 5: Test Integration

1. Start backend-ragie server:
   ```bash
   cd backend-ragie
   poetry run uvicorn main:app --reload
   ```

2. Start frontend:
   ```bash
   cd frontend
   npm run dev
   ```

3. Test core flows:
   - User login (unchanged)
   - Document upload (single endpoint)
   - Document search (unified endpoint)
   - Group management (new composable)
   - Stripe subscription (unchanged)

## API Endpoint Reference

### Documents
- `POST /documents/upload` - Upload file
- `GET /documents/list` - List user documents
- `GET /documents/{doc_id}` - Get document details
- `GET /documents/{doc_id}/status` - Check status
- `DELETE /documents/{doc_id}` - Delete document

### Search
- `POST /search/retrieve` - Semantic search

### Groups
- `POST /groups/create` - Create group
- `GET /groups/list` - List groups
- `GET /groups/{group_id}` - Get group
- `PUT /groups/{group_id}` - Update group
- `DELETE /groups/{group_id}` - Delete group

### User Settings
- `GET /user-settings` - Get settings
- `GET /user-settings/quota-status` - Get quota

### Stripe
- `POST /stripe/create-checkout-session` - Create checkout
- `GET /stripe/subscription-status` - Check subscription
- `POST /stripe/cancel-subscription` - Cancel subscription

## Troubleshooting

### "Search failed" after uploading

Make sure document status is `ready` before searching. Check with:
```javascript
const status = await getDocumentStatus(docId)
console.log(status.status) // Should be 'ready'
```

### No search results

Try using the search endpoint instead of filtering in listDocuments(). Ragie handles search better than client-side filtering.

### "Quota exceeded" error

Update your understanding of quotas:
- Free: 50 documents (not video tokens)
- Premium: 100 documents (not video tokens)

The Stripe webhook automatically updates quota on subscription change.

### Old endpoints returning 404

Removed endpoints:
- `/ingest/upload-text-and-images` → Use `/documents/upload`
- `/ingest/upload-video` → Use `/documents/upload`
- `/ingest/query` → Use `/search/retrieve`
- `/ingest/query-video` → Use `/search/retrieve`
- `/tagging/search/*` → No equivalent (use search)
- `/files` → Use `/documents/list`
- `/storage/signed-url` → Not needed (Ragie stores files)
- `/user/quota` → Use `/user-settings/quota-status`

## Future Enhancements

Backend-ragie supports these features for future implementation:
- Cloud storage integrations (Google Drive, OneDrive)
- Webhook notifications for processing completion
- Document summarization display
- Recency bias in search results
- Advanced entity-based filtering

See [backend-ragie/README.md](/backend-ragie/README.md) for more details.
