-- Add thumbnail support to ragie_documents table
-- This migration adds fields to track image thumbnails stored in Supabase Storage

ALTER TABLE ragie_documents
ADD COLUMN thumbnail_storage_path TEXT,
ADD COLUMN thumbnail_size_bytes BIGINT,
ADD COLUMN has_thumbnail BOOLEAN DEFAULT false;

-- Add index for efficient filtering of documents with thumbnails
CREATE INDEX idx_ragie_docs_has_thumbnail ON ragie_documents(has_thumbnail) WHERE has_thumbnail = true;

-- Add comments for clarity
COMMENT ON COLUMN ragie_documents.thumbnail_storage_path IS 'Path to thumbnail in Supabase Storage (e.g., thumbnails/{doc_id}.jpg)';
COMMENT ON COLUMN ragie_documents.thumbnail_size_bytes IS 'Size of thumbnail file in bytes';
COMMENT ON COLUMN ragie_documents.has_thumbnail IS 'Quick flag for filtering documents with thumbnails; enables efficient queries';
