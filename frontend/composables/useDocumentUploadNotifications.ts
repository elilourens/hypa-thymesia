/**
 * Global composable for document and video uploads with background notifications
 * Shows notifications only when files reach final processing states
 * Works across all dashboard pages
 */

import { useToast } from '#ui/composables/useToast'
import { useDocuments } from './useDocuments'
import { useVideos } from './useVideos'

interface UploadInProgress {
  id: string
  filename: string
  toastId: string
  type: 'document' | 'video'
}

// Global state
const uploadsInProgress = ref<Map<string, UploadInProgress>>(new Map())

// Simple event emitter for upload completion
type UploadCompleteCallback = (fileId: string, filename: string, success: boolean) => void
const uploadCompleteCallbacks = new Set<UploadCompleteCallback>()

export function useDocumentUploadNotifications() {
  const toast = useToast()
  const { uploadDocument, pollDocumentStatus } = useDocuments()
  const { uploadVideo, pollVideoStatus } = useVideos()

  /**
   * Detect if file is a video based on extension
   */
  function isVideoFile(file: File): boolean {
    return /\.(mp4|avi|mov|mkv)$/i.test(file.name)
  }

  /**
   * Upload a file (document or video) and show notification when it reaches a final state
   */
  async function uploadAndNotify(file: File, groupId?: string): Promise<string | null> {
    try {
      const isVideo = isVideoFile(file)

      // Upload file to appropriate endpoint
      const response = isVideo
        ? await uploadVideo(file, groupId)
        : await uploadDocument(file, groupId)

      // Show processing notification (will be replaced when done)
      const toastId = crypto.randomUUID()
      const fileType = isVideo ? 'video' : 'document'
      toast.add({
        id: toastId,
        title: 'Processing…',
        description: `${file.name} is being ${isVideo ? 'uploaded' : 'processed'}`,
        color: 'info',
        icon: 'i-lucide-hourglass',
        timeout: 0, // Don't auto-dismiss
      })

      // Track this upload
      uploadsInProgress.value.set(response.id, {
        id: response.id,
        filename: file.name,
        toastId,
        type: fileType,
      })

      // Poll in background (don't await, let it run)
      pollAndNotify(response.id, file.name, toastId, fileType)

      return response.id
    } catch (err: any) {
      toast.add({
        title: 'Upload failed',
        description: err?.message || `Failed to upload ${file.name}`,
        color: 'error',
        icon: 'i-lucide-alert-circle',
      })
      return null
    }
  }

  /**
   * Poll file status and show notification when ready/failed
   */
  async function pollAndNotify(fileId: string, filename: string, toastId: string, fileType: 'document' | 'video') {
    let success = false

    try {
      const finalStatus = fileType === 'video'
        ? await pollVideoStatus(fileId, undefined, 300, 2000)
        : await pollDocumentStatus(fileId, undefined, 300, 2000)

      const statusField = fileType === 'video' ? 'processing_status' : 'status'
      const finalStatusValue = (finalStatus as any)[statusField]

      // Replace processing toast with final status
      if (finalStatusValue === 'ready' || finalStatusValue === 'completed') {
        toast.add({
          id: toastId,
          title: 'Processing complete',
          description: `${filename} is ready${fileType === 'video' ? ' to watch' : ' to use'}`,
          color: 'success',
          icon: 'i-lucide-check-circle',
        })
        success = true
      } else if (finalStatusValue === 'failed') {
        toast.add({
          id: toastId,
          title: 'Processing failed',
          description: `${filename} could not be processed`,
          color: 'error',
          icon: 'i-lucide-alert-circle',
        })
      }

      uploadsInProgress.value.delete(fileId)
    } catch (err: any) {
      toast.add({
        id: toastId,
        title: 'Error',
        description: `Failed to monitor ${filename}`,
        color: 'error',
        icon: 'i-lucide-alert-circle',
      })

      uploadsInProgress.value.delete(fileId)
    }

    // Notify all listeners that upload completed
    uploadCompleteCallbacks.forEach(callback => {
      try {
        callback(fileId, filename, success)
      } catch (e) {
        console.error('Error in upload complete callback:', e)
      }
    })
  }

  /**
   * Upload multiple documents with notifications for each
   */
  async function uploadMultipleAndNotify(files: File[], groupId?: string): Promise<string[]> {
    const uploadPromises = files.map(file => uploadAndNotify(file, groupId))
    const results = await Promise.all(uploadPromises)
    return results.filter((id): id is string => id !== null)
  }

  /**
   * Register a callback to be called when any upload completes
   * Returns an unsubscribe function
   */
  function onUploadComplete(callback: UploadCompleteCallback): () => void {
    uploadCompleteCallbacks.add(callback)
    return () => {
      uploadCompleteCallbacks.delete(callback)
    }
  }

  /**
   * Poll status of synced documents (e.g., from Google Drive)
   * Automatically fetches page_count and chunks as Ragie processes them
   */
  async function pollSyncedDocuments(documentIds: string[]): Promise<void> {
    // Poll each synced document in background
    documentIds.forEach(docId => {
      pollAndNotify(docId, `Synced document ${docId}`, crypto.randomUUID(), 'document')
    })
  }

  return {
    uploadAndNotify,
    uploadMultipleAndNotify,
    uploadsInProgress: readonly(uploadsInProgress),
    onUploadComplete,
    pollSyncedDocuments,
  }
}
