# Supabase Database Backup & Configuration

**Created:** January 24, 2026
**Project URL:** https://yfovsxfzlkzvfojukzdv.supabase.co
**Purpose:** Complete documentation of current Supabase setup before migrating to Ragie.ai backend

---

## Overview

This document contains a complete backup of your Supabase database schema, including:
- All table definitions with columns and constraints
- All migrations with their SQL statements
- Row Level Security (RLS) policies
- Extensions enabled
- Views and functions
- TypeScript type definitions

You can use this to rebuild your database if needed or reference it while migrating to the new Ragie.ai architecture.

---

## Current Architecture

The current setup tracks document ingestion with:
- **Documents**: `app_doc_meta` (metadata for uploaded documents)
- **Chunks**: `app_chunks` (text/image chunks extracted from documents)
- **Vector Registry**: `app_vector_registry` (vector IDs for embeddings)
- **Tags**: `app_image_tags` (auto-detected tags for images and documents)
- **Groups**: `app_groups` (document organization)
- **OAuth Tokens**: `user_oauth_tokens` (for Google Drive, OneDrive integrations)
- **User Settings**: `user_settings` (subscription and file limits)

**Note**: When moving to Ragie.ai, you'll keep `user_oauth_tokens` and `user_settings` for auth/payments, but can remove the document ingestion tables.

---

## Enabled Extensions

The following PostgreSQL extensions are installed:

```sql
-- Core extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";        -- UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";         -- Cryptographic functions
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements"; -- Query monitoring
CREATE EXTENSION IF NOT EXISTS "pg_graphql";       -- GraphQL support
CREATE EXTENSION IF NOT EXISTS "supabase_vault";   -- Secret management
```

---

## Tables

### 1. app_doc_meta (Document Metadata)
Primary table tracking document information.

```sql
CREATE TABLE app_doc_meta (
    doc_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id),
    group_id UUID REFERENCES app_groups(group_id),
    processing_status TEXT DEFAULT 'completed'
        CHECK (processing_status IN ('queued', 'processing', 'completed', 'failed')),
    filename TEXT,
    mime_type TEXT,
    storage_path TEXT,
    text_chunks_count INTEGER DEFAULT 0,
    images_count INTEGER DEFAULT 0,
    error_message TEXT,
    celery_task_id TEXT,
    modality TEXT DEFAULT 'text',  -- 'text', 'image', 'video', etc.
    duration_seconds FLOAT,         -- For video files
    file_tokens INTEGER DEFAULT 1   -- For usage tracking
);

-- RLS Policies:
CREATE POLICY "Users can view own documents" ON app_doc_meta
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own documents" ON app_doc_meta
    FOR INSERT WITH CHECK (true);
CREATE POLICY "Users can update own documents" ON app_doc_meta
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own documents" ON app_doc_meta
    FOR DELETE USING (auth.uid() = user_id);
```

### 2. app_chunks (Document Chunks)
Stores individual chunks (text, images, video frames, transcripts) extracted from documents.

```sql
CREATE TABLE app_chunks (
    chunk_id UUID PRIMARY KEY,
    doc_id UUID NOT NULL REFERENCES app_doc_meta(doc_id) ON DELETE CASCADE,
    chunk_index INTEGER,
    modality TEXT,  -- 'text', 'image', 'video_frame', 'video_transcript'
    storage_path TEXT,
    bucket TEXT,
    mime_type TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    formatting_status TEXT DEFAULT 'unformatted'
        CHECK (formatting_status IN ('unformatted', 'formatting', 'formatted', 'failed')),
    formatted_at TIMESTAMP WITH TIME ZONE,
    formatting_error TEXT,
    size_bytes BIGINT,
    user_id UUID DEFAULT auth.uid() REFERENCES auth.users(id),
    source TEXT DEFAULT 'upload'
        CHECK (source IN ('upload', 'google_drive', 'onedrive')),
    external_id TEXT,
    external_url TEXT,
    converted_pdf_path TEXT,      -- For PowerPoint files converted to PDF
    original_filename TEXT
);

-- RLS Policies:
CREATE POLICY "users can view own chunks" ON app_chunks
    FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "users can insert own chunks" ON app_chunks
    FOR INSERT WITH CHECK (true);
CREATE POLICY "users can delete own chunks" ON app_chunks
    FOR DELETE USING (user_id = auth.uid());
```

### 3. app_groups (Document Groups)
Organize documents into groups/folders.

```sql
CREATE TABLE app_groups (
    user_id UUID,
    name TEXT,
    group_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sort_index INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- RLS Policies:
CREATE POLICY "Users can view own groups" ON app_groups
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own groups" ON app_groups
    FOR INSERT WITH CHECK (true);
CREATE POLICY "Users can update own groups" ON app_groups
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own groups" ON app_groups
    FOR DELETE USING (auth.uid() = user_id);
```

### 4. app_image_tags (Auto-detected Tags)
Stores tags for images (CLIP + OWL-ViT) and documents (LLM-based).

```sql
CREATE TABLE app_image_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID REFERENCES app_chunks(chunk_id) ON DELETE CASCADE,
    doc_id UUID NOT NULL REFERENCES app_doc_meta(doc_id) ON DELETE CASCADE,
    user_id TEXT,
    tag_name TEXT,
    confidence FLOAT CHECK (confidence >= 0.0 AND confidence <= 1.0),
    verified BOOLEAN DEFAULT false,  -- OWL-ViT verified
    bbox JSONB,  -- {x, y, width, height}
    category TEXT,
    reasoning TEXT,
    tag_type TEXT DEFAULT 'image' CHECK (tag_type IN ('image', 'document')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- RLS Policies:
CREATE POLICY "Users can view own image tags" ON app_image_tags
    FOR SELECT USING ((auth.uid())::text = user_id);
CREATE POLICY "Users can insert own image tags" ON app_image_tags
    FOR INSERT WITH CHECK (true);
CREATE POLICY "Users can update own image tags" ON app_image_tags
    FOR UPDATE USING ((auth.uid())::text = user_id);
CREATE POLICY "Users can delete own image tags" ON app_image_tags
    FOR DELETE USING ((auth.uid())::text = user_id);
```

### 5. app_vector_registry (Vector Embeddings)
Maps vector IDs to chunks for similarity search.

```sql
CREATE TABLE app_vector_registry (
    vector_id TEXT PRIMARY KEY,
    chunk_id UUID NOT NULL REFERENCES app_chunks(chunk_id) ON DELETE CASCADE,
    embedding_model TEXT,
    embedding_version INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- RLS Policies:
CREATE POLICY "users can insert vectors for their chunks" ON app_vector_registry
    FOR INSERT WITH CHECK (true);
CREATE POLICY "users can view vectors for their chunks" ON app_vector_registry
    FOR SELECT USING (EXISTS (
        SELECT 1 FROM app_chunks c
        WHERE c.chunk_id = app_vector_registry.chunk_id
        AND c.user_id = auth.uid()
    ));
CREATE POLICY "users can delete vectors for their chunks" ON app_vector_registry
    FOR DELETE USING (EXISTS (
        SELECT 1 FROM app_chunks c
        WHERE c.chunk_id = app_vector_registry.chunk_id
        AND c.user_id = auth.uid()
    ));
```

### 6. user_oauth_tokens (OAuth Token Storage)
Stores OAuth tokens for Google Drive and OneDrive integrations. **Keep this for auth.**

```sql
CREATE TABLE user_oauth_tokens (
    id BIGINT PRIMARY KEY DEFAULT nextval('user_oauth_tokens_id_seq'::regclass),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    provider TEXT,  -- 'google', 'microsoft', etc.
    access_token TEXT,
    refresh_token TEXT,
    id_token TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    scope TEXT,
    raw_data JSONB,
    token_type TEXT DEFAULT 'Bearer',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- RLS Policies:
CREATE POLICY "Users can access their own oauth tokens" ON user_oauth_tokens
    FOR ALL USING (auth.uid() = user_id);
```

### 7. user_settings (User Subscription & Limits)
Stores subscription and file limit information. **Keep this for payments.**

```sql
CREATE TABLE user_settings (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    stripe_subscription_status TEXT,  -- active, trialing, canceled, unpaid, etc.
    stripe_current_period_end BIGINT,
    stripe_cancel_at_period_end BOOLEAN DEFAULT false,
    max_files INTEGER DEFAULT 50,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- RLS Policies:
CREATE POLICY "Users can read their own settings" ON user_settings
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can update their own settings" ON user_settings
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Service role can insert settings" ON user_settings
    FOR INSERT WITH CHECK (true);
```

---

## Views

### app_docs
Aggregated view of documents with chunk counts.

```sql
CREATE VIEW app_docs AS
SELECT
    d.doc_id,
    d.user_id,
    d.filename,
    d.mime_type,
    d.storage_path,
    d.bucket,
    d.modality,
    d.created_at,
    d.size_bytes,
    COUNT(c.chunk_id) as chunk_count
FROM app_doc_meta d
LEFT JOIN app_chunks c ON d.doc_id = c.doc_id
GROUP BY d.doc_id, d.user_id, d.filename, d.mime_type, d.storage_path, d.bucket, d.modality, d.created_at, d.size_bytes;
```

### app_docs_with_group
Documents with their group information.

```sql
CREATE VIEW app_docs_with_group AS
SELECT
    d.doc_id,
    d.user_id,
    d.filename,
    d.mime_type,
    d.storage_path,
    d.bucket,
    d.modality,
    d.created_at,
    d.size_bytes,
    COUNT(c.chunk_id) as chunk_count,
    g.group_id,
    g.name as group_name,
    g.sort_index as group_sort_index,
    c.source as storage_provider
FROM app_doc_meta d
LEFT JOIN app_chunks c ON d.doc_id = c.doc_id
LEFT JOIN app_groups g ON d.group_id = g.group_id
GROUP BY d.doc_id, d.user_id, d.filename, d.mime_type, d.storage_path, d.bucket, d.modality, d.created_at, d.size_bytes, g.group_id, g.name, g.sort_index, c.source;
```

---

## Migration History

This is the complete migration history that created the current schema. These migrations are idempotent and can be re-applied.

### Migration 1: create_app_image_tags_table (20251130204256)
```sql
CREATE TABLE IF NOT EXISTS app_image_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL,
    doc_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tag_name TEXT NOT NULL,
    confidence FLOAT NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    verified BOOLEAN NOT NULL DEFAULT false,
    bbox JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT fk_chunk FOREIGN KEY (chunk_id) REFERENCES app_chunks(chunk_id) ON DELETE CASCADE,
    CONSTRAINT unique_chunk_tag UNIQUE (chunk_id, tag_name)
);

CREATE INDEX idx_image_tags_chunk_id ON app_image_tags(chunk_id);
CREATE INDEX idx_image_tags_user_id ON app_image_tags(user_id);
CREATE INDEX idx_image_tags_doc_id ON app_image_tags(doc_id);
CREATE INDEX idx_image_tags_tag_name ON app_image_tags(tag_name);
CREATE INDEX idx_image_tags_verified ON app_image_tags(verified);
CREATE INDEX idx_image_tags_confidence ON app_image_tags(confidence);
CREATE INDEX idx_image_tags_user_tag ON app_image_tags(user_id, tag_name) WHERE verified = true;
CREATE INDEX idx_image_tags_user_verified ON app_image_tags(user_id, verified, tag_name);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_app_image_tags_updated_at
    BEFORE UPDATE ON app_image_tags
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

### Migration 2: add_document_tagging_support (20251202180514)
```sql
ALTER TABLE app_image_tags
ADD COLUMN IF NOT EXISTS tag_type TEXT DEFAULT 'image' CHECK (tag_type IN ('image', 'document')),
ADD COLUMN IF NOT EXISTS category TEXT,
ADD COLUMN IF NOT EXISTS reasoning TEXT;

CREATE INDEX IF NOT EXISTS idx_app_image_tags_tag_type ON app_image_tags(tag_type);
CREATE INDEX IF NOT EXISTS idx_app_image_tags_category ON app_image_tags(category);
CREATE INDEX IF NOT EXISTS idx_app_image_tags_user_tag_type ON app_image_tags(user_id, tag_type);

UPDATE app_image_tags SET tag_type = 'image' WHERE tag_type IS NULL;
```

### Migration 3: make_chunk_id_nullable_for_document_tags (20251202181644)
```sql
ALTER TABLE app_image_tags ALTER COLUMN chunk_id DROP NOT NULL;

ALTER TABLE app_image_tags DROP CONSTRAINT IF EXISTS check_chunk_id_for_tag_type;
ALTER TABLE app_image_tags
ADD CONSTRAINT check_chunk_id_for_tag_type CHECK (
  (tag_type = 'image' AND chunk_id IS NOT NULL) OR
  (tag_type = 'document' AND chunk_id IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_app_image_tags_doc_tag_type ON app_image_tags(doc_id, tag_type);
```

### Migration 4: fix_unique_constraint_for_document_tags (20251202182016)
```sql
ALTER TABLE app_image_tags DROP CONSTRAINT IF EXISTS unique_chunk_tag;

CREATE UNIQUE INDEX unique_image_tag ON app_image_tags (chunk_id, tag_name) WHERE chunk_id IS NOT NULL;
CREATE UNIQUE INDEX unique_document_tag ON app_image_tags (doc_id, tag_name) WHERE chunk_id IS NULL AND tag_type = 'document';
```

### Migration 5: fix_image_tags_cascade_delete (20251202184655)
```sql
DELETE FROM app_image_tags WHERE NOT EXISTS (
    SELECT 1 FROM app_doc_meta d WHERE d.doc_id::text = app_image_tags.doc_id
);

ALTER TABLE app_image_tags ALTER COLUMN doc_id TYPE uuid USING doc_id::uuid;

ALTER TABLE app_image_tags
ADD CONSTRAINT fk_doc
FOREIGN KEY (doc_id)
REFERENCES app_doc_meta(doc_id)
ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_app_image_tags_doc_id ON app_image_tags(doc_id);
```

### Migration 6: create_user_settings_table (20251210170625)
```sql
CREATE TABLE IF NOT EXISTS public.user_settings (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    max_files INTEGER NOT NULL DEFAULT 50,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read their own settings" ON public.user_settings
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can update their own settings" ON public.user_settings
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Service role can insert settings" ON public.user_settings
    FOR INSERT WITH CHECK (true);

CREATE TRIGGER update_user_settings_updated_at
    BEFORE UPDATE ON public.user_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE INDEX idx_user_settings_user_id ON public.user_settings(user_id);
```

### Migration 7: add_onedrive_storage_provider (20251211153946)
```sql
ALTER TABLE app_chunks
DROP CONSTRAINT IF EXISTS app_chunks_storage_provider_check;

ALTER TABLE app_chunks
ADD CONSTRAINT app_chunks_storage_provider_check
CHECK (storage_provider = ANY (ARRAY['supabase'::text, 'google_drive'::text, 'onedrive'::text]));
```

### Migration 8: rename_storage_provider_to_source (20251211154112)
```sql
ALTER TABLE app_chunks RENAME COLUMN storage_provider TO source;

ALTER TABLE app_chunks DROP CONSTRAINT IF EXISTS app_chunks_storage_provider_check;
ALTER TABLE app_chunks
ADD CONSTRAINT app_chunks_source_check
CHECK (source = ANY (ARRAY['supabase'::text, 'google_drive'::text, 'onedrive'::text]));
```

### Migration 9: change_supabase_source_to_upload_v3 (20251211154306)
```sql
ALTER TABLE app_chunks DROP CONSTRAINT IF EXISTS app_chunks_source_check;
ALTER TABLE app_chunks DROP CONSTRAINT IF EXISTS storage_provider_validation;

UPDATE app_chunks SET source = 'upload' WHERE source = 'supabase';

ALTER TABLE app_chunks ALTER COLUMN source SET DEFAULT 'upload'::text;

ALTER TABLE app_chunks
ADD CONSTRAINT app_chunks_source_check
CHECK (source = ANY (ARRAY['upload'::text, 'google_drive'::text, 'onedrive'::text]));

ALTER TABLE app_chunks
ADD CONSTRAINT storage_provider_validation CHECK (
  ((source = 'upload'::text) AND (storage_path IS NOT NULL) AND (bucket IS NOT NULL)) OR
  ((source = 'google_drive'::text) AND (external_id IS NOT NULL) AND (external_url IS NOT NULL)) OR
  ((source = 'onedrive'::text) AND (external_id IS NOT NULL) AND (external_url IS NOT NULL))
);
```

### Migration 10: add_converted_pdf_fields (20251213173207)
```sql
ALTER TABLE public.app_chunks
ADD COLUMN IF NOT EXISTS converted_pdf_path text,
ADD COLUMN IF NOT EXISTS original_filename text;
```

### Migration 11: add_stripe_subscription_fields (20251229230933)
```sql
ALTER TABLE user_settings
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT,
ADD COLUMN IF NOT EXISTS stripe_subscription_status TEXT,
ADD COLUMN IF NOT EXISTS stripe_current_period_end BIGINT,
ADD COLUMN IF NOT EXISTS stripe_cancel_at_period_end BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_user_settings_stripe_subscription_id
ON user_settings(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_user_settings_stripe_customer_id
ON user_settings(stripe_customer_id);
```

### Migration 12: add_processing_status_to_doc_meta (20251230203949)
```sql
ALTER TABLE app_doc_meta
ADD COLUMN IF NOT EXISTS processing_status TEXT DEFAULT 'completed',
ADD COLUMN IF NOT EXISTS filename TEXT,
ADD COLUMN IF NOT EXISTS mime_type TEXT,
ADD COLUMN IF NOT EXISTS storage_path TEXT,
ADD COLUMN IF NOT EXISTS text_chunks_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS images_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS error_message TEXT;

CREATE INDEX IF NOT EXISTS idx_app_doc_meta_processing_status
ON app_doc_meta(user_id, processing_status);

ALTER TABLE app_doc_meta
ADD CONSTRAINT valid_processing_status
CHECK (processing_status IN ('queued', 'processing', 'completed', 'failed'));
```

### Migration 13: add_chunk_formatting_status (20251230221309)
```sql
ALTER TABLE app_chunks
ADD COLUMN formatting_status TEXT DEFAULT 'unformatted' CHECK (formatting_status IN ('unformatted', 'formatting', 'formatted', 'failed')),
ADD COLUMN formatted_at TIMESTAMPTZ,
ADD COLUMN formatting_error TEXT;

CREATE INDEX idx_chunks_formatting_status ON app_chunks(formatting_status, user_id);
```

### Migration 14: create_video_tables (20260112174104)
```sql
-- These were later dropped but documented for reference
CREATE TABLE IF NOT EXISTS app_video_docs (
    video_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    bucket TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    duration_seconds FLOAT NOT NULL,
    fps FLOAT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    size_bytes BIGINT NOT NULL,
    group_id UUID,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app_video_frame_chunks (
    chunk_id UUID PRIMARY KEY,
    video_id UUID NOT NULL REFERENCES app_video_docs(video_id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    frame_index INTEGER NOT NULL,
    timestamp FLOAT NOT NULL,
    storage_path TEXT NOT NULL,
    bucket TEXT NOT NULL,
    scene_id INTEGER,
    modality TEXT DEFAULT 'video_frame'
);

CREATE TABLE IF NOT EXISTS app_video_transcript_chunks (
    chunk_id UUID PRIMARY KEY,
    video_id UUID NOT NULL REFERENCES app_video_docs(video_id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    text TEXT NOT NULL,
    modality TEXT DEFAULT 'video_transcript'
);

CREATE TABLE IF NOT EXISTS app_video_vector_registry (
    vector_id TEXT PRIMARY KEY,
    chunk_id UUID NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_version INTEGER NOT NULL,
    modality TEXT NOT NULL
);
```

### Migration 15: add_modality_column_to_app_doc_meta (20260113212816)
```sql
ALTER TABLE app_doc_meta
ADD COLUMN IF NOT EXISTS modality TEXT DEFAULT 'text';

CREATE INDEX IF NOT EXISTS idx_app_doc_meta_modality ON app_doc_meta(modality);
```

### Migration 16: drop_video_specific_tables (20260114211650)
```sql
DROP TABLE IF EXISTS app_video_frame_chunks CASCADE;
DROP TABLE IF EXISTS app_video_transcript_chunks CASCADE;
DROP TABLE IF EXISTS app_video_vector_registry CASCADE;
DROP TABLE IF EXISTS app_video_docs CASCADE;
```

### Migration 17: add_video_duration_and_file_tokens (20260117230007)
```sql
ALTER TABLE app_doc_meta
ADD COLUMN duration_seconds REAL NULL,
ADD COLUMN file_tokens INTEGER NOT NULL DEFAULT 1;
```

### Migration 18: add_cascade_delete_foreign_keys (20260117233020)
```sql
ALTER TABLE app_vector_registry DROP CONSTRAINT IF EXISTS fk_registry_chunk;
ALTER TABLE app_chunks DROP CONSTRAINT IF EXISTS fk_chunks_doc;

ALTER TABLE app_chunks
  ADD CONSTRAINT fk_chunks_doc
  FOREIGN KEY (doc_id)
  REFERENCES app_doc_meta(doc_id)
  ON DELETE CASCADE;

ALTER TABLE app_vector_registry
  ADD CONSTRAINT fk_registry_chunk
  FOREIGN KEY (chunk_id)
  REFERENCES app_chunks(chunk_id)
  ON DELETE CASCADE;

ALTER TABLE app_image_tags DROP CONSTRAINT IF EXISTS fk_chunk;
ALTER TABLE app_image_tags DROP CONSTRAINT IF EXISTS fk_doc;

ALTER TABLE app_image_tags
  ADD CONSTRAINT fk_chunk
  FOREIGN KEY (chunk_id)
  REFERENCES app_chunks(chunk_id)
  ON DELETE CASCADE;

ALTER TABLE app_image_tags
  ADD CONSTRAINT fk_doc
  FOREIGN KEY (doc_id)
  REFERENCES app_doc_meta(doc_id)
  ON DELETE CASCADE;
```

### Migration 19: add_celery_task_id_column (20260123191934)
```sql
ALTER TABLE app_doc_meta ADD COLUMN celery_task_id TEXT;
CREATE INDEX idx_celery_task_id ON app_doc_meta(celery_task_id);
```

---

## Row Level Security (RLS) Policies Summary

All data tables have RLS enabled with user-scoped policies:

| Table | Policy | Action | Condition |
|-------|--------|--------|-----------|
| app_doc_meta | Users can view own documents | SELECT | auth.uid() = user_id |
| app_doc_meta | Users can insert own documents | INSERT | true (service role sets user_id) |
| app_doc_meta | Users can update own documents | UPDATE | auth.uid() = user_id |
| app_doc_meta | Users can delete own documents | DELETE | auth.uid() = user_id |
| app_chunks | users can view own chunks | SELECT | user_id = auth.uid() |
| app_chunks | users can insert own chunks | INSERT | true |
| app_chunks | users can delete own chunks | DELETE | user_id = auth.uid() |
| app_groups | Users can view own groups | SELECT | auth.uid() = user_id |
| app_groups | Users can insert own groups | INSERT | true |
| app_groups | Users can update own groups | UPDATE | auth.uid() = user_id |
| app_groups | Users can delete own groups | DELETE | auth.uid() = user_id |
| app_image_tags | Users can view own image tags | SELECT | (auth.uid())::text = user_id |
| app_image_tags | Users can insert own image tags | INSERT | true |
| app_image_tags | Users can update own image tags | UPDATE | (auth.uid())::text = user_id |
| app_image_tags | Users can delete own image tags | DELETE | (auth.uid())::text = user_id |
| app_vector_registry | users can insert vectors for their chunks | INSERT | true |
| app_vector_registry | users can view vectors for their chunks | SELECT | Subquery: exists in user's chunks |
| app_vector_registry | users can delete vectors for their chunks | DELETE | Subquery: exists in user's chunks |
| user_oauth_tokens | Users can access their own oauth tokens | ALL | auth.uid() = user_id |
| user_settings | Users can read their own settings | SELECT | auth.uid() = user_id |
| user_settings | Users can update their own settings | UPDATE | auth.uid() = user_id |
| user_settings | Service role can insert settings | INSERT | true (service role only) |

Storage RLS policies for buckets `images`, `texts`, `extracted-images`:
- Users can upload, view, update, delete their own files (identified by folder structure)

---

## TypeScript Types

Generated from Supabase schema. Use these in your frontend application:

```typescript
export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  public: {
    Tables: {
      app_chunks: {
        Row: {
          bucket: string
          chunk_id: string
          chunk_index: number
          converted_pdf_path: string | null
          created_at: string | null
          doc_id: string
          external_id: string | null
          external_url: string | null
          formatted_at: string | null
          formatting_error: string | null
          formatting_status: string | null
          mime_type: string
          modality: string
          original_filename: string | null
          size_bytes: number | null
          source: string | null
          storage_path: string
          user_id: string
        }
      }
      app_doc_meta: {
        Row: {
          celery_task_id: string | null
          doc_id: string
          duration_seconds: number | null
          error_message: string | null
          file_tokens: number
          filename: string | null
          group_id: string | null
          images_count: number | null
          mime_type: string | null
          modality: string | null
          processing_status: string | null
          storage_path: string | null
          text_chunks_count: number | null
          user_id: string
        }
      }
      app_groups: {
        Row: {
          created_at: string
          group_id: string
          name: string
          sort_index: number
          updated_at: string
          user_id: string
        }
      }
      app_image_tags: {
        Row: {
          bbox: Json | null
          category: string | null
          chunk_id: string | null
          confidence: number
          created_at: string | null
          doc_id: string
          id: string
          reasoning: string | null
          tag_name: string
          tag_type: string | null
          updated_at: string | null
          user_id: string
          verified: boolean
        }
      }
      app_vector_registry: {
        Row: {
          chunk_id: string
          created_at: string | null
          embedding_model: string
          embedding_version: number
          vector_id: string
        }
      }
      user_oauth_tokens: {
        Row: {
          access_token: string
          created_at: string | null
          expires_at: string | null
          id: number
          id_token: string | null
          provider: string
          raw_data: Json | null
          refresh_token: string | null
          scope: string | null
          token_type: string | null
          updated_at: string | null
          user_id: string
        }
      }
      user_settings: {
        Row: {
          created_at: string
          max_files: number
          stripe_cancel_at_period_end: boolean | null
          stripe_current_period_end: number | null
          stripe_customer_id: string | null
          stripe_subscription_id: string | null
          stripe_subscription_status: string | null
          updated_at: string
          user_id: string
        }
      }
    }
    Views: {
      app_docs: {
        Row: {
          bucket: string | null
          chunk_count: number | null
          created_at: string | null
          doc_id: string | null
          filename: string | null
          mime_type: string | null
          modality: string | null
          size_bytes: number | null
          storage_path: string | null
          user_id: string | null
        }
      }
      app_docs_with_group: {
        Row: {
          bucket: string | null
          chunk_count: number | null
          created_at: string | null
          doc_id: string | null
          filename: string | null
          group_id: string | null
          group_name: string | null
          group_sort_index: number | null
          mime_type: string | null
          modality: string | null
          size_bytes: number | null
          storage_path: string | null
          storage_provider: string | null
          user_id: string | null
        }
      }
    }
  }
}
```

---

## Recovery Instructions

If something goes wrong with your Ragie.ai migration and you need to restore this database:

1. **Keep the auth and payments tables:**
   - `user_oauth_tokens` - for OAuth integrations
   - `user_settings` - for subscription management

2. **Drop document-related tables (if you need a clean start):**
   ```sql
   DROP TABLE IF EXISTS app_image_tags CASCADE;
   DROP TABLE IF EXISTS app_vector_registry CASCADE;
   DROP TABLE IF EXISTS app_chunks CASCADE;
   DROP TABLE IF EXISTS app_doc_meta CASCADE;
   DROP TABLE IF EXISTS app_groups CASCADE;
   ```

3. **Re-apply migrations from this document** in order, or apply them from Supabase migration system if still available.

4. **Verify RLS policies** are properly enabled on all tables after recreation.

---

## Key Tables for Ragie Migration

When migrating to Ragie.ai, you should:

**KEEP:**
- `user_oauth_tokens` - for OAuth authentication (can still use if needed)
- `user_settings` - for Stripe subscription tracking and file limits

**REMOVE:**
- `app_doc_meta` - Ragie.ai manages documents
- `app_chunks` - Ragie.ai manages chunks
- `app_vector_registry` - Ragie.ai manages embeddings
- `app_image_tags` - Ragie.ai handles tagging
- `app_groups` - Can be simplified in new architecture

**CREATE NEW TABLES (as needed):**
- Ragie sync status table (track which documents are synced to Ragie)
- Ragie usage/credit tracking (if needed)
- Any application-specific metadata

---

## Indexes Created

Comprehensive indexing strategy for performance:

```
app_doc_meta:
- idx_app_doc_meta_processing_status (user_id, processing_status)
- idx_app_doc_meta_modality (modality)

app_chunks:
- idx_chunks_formatting_status (formatting_status, user_id)

app_image_tags:
- idx_image_tags_chunk_id
- idx_image_tags_user_id
- idx_image_tags_doc_id
- idx_image_tags_tag_name
- idx_image_tags_verified
- idx_image_tags_confidence
- idx_image_tags_user_tag
- idx_image_tags_user_verified
- idx_app_image_tags_tag_type
- idx_app_image_tags_category
- idx_app_image_tags_user_tag_type
- idx_app_image_tags_doc_tag_type
- unique_image_tag
- unique_document_tag

app_vector_registry:
- (none, but foreign key on chunk_id)

user_settings:
- idx_user_settings_user_id
- idx_user_settings_stripe_subscription_id
- idx_user_settings_stripe_customer_id

user_oauth_tokens:
- (none)

app_groups:
- (none)
```

---

**Last Updated:** January 24, 2026
**Status:** Ready for migration backup
