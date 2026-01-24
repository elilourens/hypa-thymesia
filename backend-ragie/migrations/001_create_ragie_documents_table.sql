-- Migration: Create ragie_documents table
-- Description: Tracks documents uploaded to Ragie with metadata and status

CREATE TABLE IF NOT EXISTS ragie_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    group_id UUID REFERENCES app_groups(group_id) ON DELETE SET NULL,

    -- Ragie identifiers
    ragie_document_id UUID NOT NULL UNIQUE,

    -- File metadata
    filename TEXT NOT NULL,
    mime_type TEXT,
    file_size_bytes BIGINT,

    -- Processing status from Ragie
    -- Status: pending, partitioning, partitioned, refined, chunked, indexed,
    --         summary_indexed, keyword_indexed, ready, failed
    status TEXT NOT NULL DEFAULT 'pending',

    -- Counts from Ragie
    chunk_count INTEGER,
    page_count INTEGER,

    -- Organization
    source TEXT DEFAULT 'upload',  -- upload, google_drive, onedrive (future)
    external_id TEXT,              -- For cloud storage integrations

    -- Custom metadata stored in Ragie
    ragie_metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Indexes
    CONSTRAINT valid_status CHECK (status IN (
        'pending', 'partitioning', 'partitioned', 'refined', 'chunked',
        'indexed', 'summary_indexed', 'keyword_indexed', 'ready', 'failed'
    ))
);

-- Create indexes for performance
CREATE INDEX idx_ragie_docs_user ON ragie_documents(user_id);
CREATE INDEX idx_ragie_docs_group ON ragie_documents(group_id);
CREATE INDEX idx_ragie_docs_status ON ragie_documents(status);
CREATE INDEX idx_ragie_docs_ragie_id ON ragie_documents(ragie_document_id);
CREATE INDEX idx_ragie_docs_created ON ragie_documents(created_at DESC);

-- Enable Row Level Security
ALTER TABLE ragie_documents ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view their own documents"
    ON ragie_documents FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own documents"
    ON ragie_documents FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own documents"
    ON ragie_documents FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own documents"
    ON ragie_documents FOR DELETE
    USING (auth.uid() = user_id);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION ragie_documents_update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update updated_at
CREATE TRIGGER ragie_documents_update_updated_at_trigger
    BEFORE UPDATE ON ragie_documents
    FOR EACH ROW
    EXECUTE FUNCTION ragie_documents_update_updated_at();
