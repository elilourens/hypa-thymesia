/**
 * TypeScript types for Google Drive API responses
 */

/**
 * Sync status for Google Drive files
 */
export type SyncStatus = 'pending' | 'syncing' | 'ready' | 'failed'

/**
 * Google Drive file record from database
 */
export interface GoogleDriveFile {
  id: string
  sync_config_id: string
  user_id: string
  gdrive_file_id: string
  filename: string
  mime_type: string | null
  file_size_bytes: number | null
  ragie_document_id: string | null
  sync_status: SyncStatus
  sync_error: string | null
  last_synced_at: string | null
  created_at: string
  updated_at: string
}

/**
 * Google Drive sync configuration
 */
export interface GoogleDriveSyncConfig {
  id: string
  user_id: string
  folder_id: string
  folder_name: string
  access_token_encrypted: string
  refresh_token_encrypted: string | null
  token_expires_at: string
  page_token: string | null
  group_id: string | null
  last_sync_at: string | null
  last_sync_status: 'success' | 'error' | 'pending' | null
  last_error: string | null
  created_at: string
  updated_at: string
}

/**
 * Response from manual sync trigger
 */
export interface SyncResponse {
  status: 'success' | 'error'
  files_processed: number
  files_failed?: number
  total_files?: number
  message?: string
  failed_files?: Array<{
    name: string
    error: string
  }>
}

/**
 * Response from connect folder endpoint
 */
export interface ConnectFolderResponse {
  message: string
  sync_config_id: string
}

/**
 * Response from get sync config endpoint
 */
export interface GetSyncConfigResponse {
  folder_name: string
  folder_id: string
  last_sync_at: string | null
  last_sync_status: string | null
  group_id: string | null
}

/**
 * Response from check linked endpoint
 */
export interface CheckLinkedResponse {
  linked: boolean
}

/**
 * Response from check needs consent endpoint
 */
export interface CheckNeedsConsentResponse {
  needs_consent: boolean
}

/**
 * Error response from API
 */
export interface APIErrorResponse {
  detail: string
  status_code?: number
}
