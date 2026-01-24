/**
 * Global composable for document uploads with background notifications
 * Shows notifications only when documents reach final processing states
 * Works across all dashboard pages
 */

import { useToast } from '#ui/composables/useToast'
import { useDocuments } from './useDocuments'

interface UploadInProgress {
  id: string
  filename: string
  toastId: string
}

const uploadsInProgress = ref<Map<string, UploadInProgress>>(new Map())

export function useDocumentUploadNotifications() {
  const toast = useToast()
  const { uploadDocument, pollDocumentStatus } = useDocuments()

  /**
   * Upload a document and show notification only when it reaches a final state
   */
  async function uploadAndNotify(file: File, groupId?: string): Promise<string | null> {
    try {
      // Upload file
      const response = await uploadDocument(file, groupId)

      // Show processing notification (will be replaced when done)
      const toastId = crypto.randomUUID()
      const progressToast = toast.add({
        id: toastId,
        title: 'Processing…',
        description: `${file.name} is being processed`,
        color: 'info',
        icon: 'i-lucide-hourglass',
        timeout: 0, // Don't auto-dismiss
      })

      // Track this upload
      uploadsInProgress.value.set(response.id, {
        id: response.id,
        filename: file.name,
        toastId,
      })

      // Poll in background (don't await, let it run)
      pollAndNotify(response.id, file.name, toastId)

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
   * Poll document status and show notification when ready/failed
   */
  async function pollAndNotify(docId: string, filename: string, toastId: string) {
    try {
      const finalStatus = await pollDocumentStatus(docId, undefined, 300, 2000)

      // Replace processing toast with final status
      if (finalStatus.status === 'ready') {
        toast.add({
          id: toastId,
          title: 'Processing complete',
          description: `${filename} is ready to use`,
          color: 'success',
          icon: 'i-lucide-check-circle',
        })
      } else if (finalStatus.status === 'failed') {
        toast.add({
          id: toastId,
          title: 'Processing failed',
          description: `${filename} could not be processed`,
          color: 'error',
          icon: 'i-lucide-alert-circle',
        })
      }

      uploadsInProgress.value.delete(docId)
    } catch (err: any) {
      toast.add({
        id: toastId,
        title: 'Error',
        description: `Failed to monitor ${filename}`,
        color: 'error',
        icon: 'i-lucide-alert-circle',
      })

      uploadsInProgress.value.delete(docId)
    }
  }

  /**
   * Upload multiple documents with notifications for each
   */
  async function uploadMultipleAndNotify(files: File[], groupId?: string): Promise<string[]> {
    const uploadPromises = files.map(file => uploadAndNotify(file, groupId))
    const results = await Promise.all(uploadPromises)
    return results.filter((id): id is string => id !== null)
  }

  return {
    uploadAndNotify,
    uploadMultipleAndNotify,
    uploadsInProgress: readonly(uploadsInProgress),
  }
}
