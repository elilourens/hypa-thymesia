<script setup lang="ts">
import { ref, watch } from 'vue'
import { useFilesApi } from '~/composables/useFiles'
const { getSignedUrl, getThumbnailUrl } = useFilesApi()
const toast = useToast()

const props = defineProps<{ results: any[], deleting?: boolean }>()

// ========== Utility Functions ==========

function getFileName(title?: string) {
  return title || '(unknown file)'
}

// Builds URLs for deep linking
function buildDeepLink(baseUrl: string, r: any) {
  const mime = r.metadata?.mime_type || ''
  if (mime.includes('application/pdf') && r.metadata?.page_number) {
    return `${baseUrl}#page=${r.metadata.page_number}`
  }
  if (mime.includes('officedocument.wordprocessingml.document')) {
    return `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(baseUrl)}`
  }
  return baseUrl
}

// ========== Actions ==========

async function handleOpen(r: any) {
  try {
    const url = await getSignedUrl(r.metadata.bucket, r.metadata.storage_path)
    if (!url) throw new Error('No URL returned')
    window.open(buildDeepLink(url, r), '_blank')
  } catch (err: any) {
    toast.add({
      title: 'Could not open file',
      description: err.message || 'Error generating signed URL',
      color: 'error'
    })
  }
}

async function handleDownload(r: any) {
  try {
    const url = await getSignedUrl(r.metadata.bucket, r.metadata.storage_path)
    if (!url) throw new Error('No URL returned')
    window.open(url, '_blank')
  } catch (err: any) {
    toast.add({
      title: 'Download failed',
      description: err.message || 'Error generating signed URL',
      color: 'error'
    })
  }
}

async function handleOpenParentDoc(r: any) {
  try {
    // Get parent bucket and storage path
    let parentBucket = r.metadata.parent_bucket
    let parentPath = r.metadata.parent_storage_path

    // Determine file extension from parent path
    const isImage = parentPath?.match(/\.(png|jpeg|jpg|webp)$/i)

    // Infer bucket if not provided
    if (!parentBucket && parentPath) {
      // Check if path starts with a known prefix
      if (parentPath.startsWith('google-drive/')) {
        parentBucket = 'google-drive'
        // Keep the full path including google-drive/ prefix
      } else {
        // For paths like "uploads/file.pdf" stored in texts/images bucket
        // Bucket depends on file type: images go to 'images', docs go to 'texts'
        parentBucket = isImage ? 'images' : 'texts'
        // Keep the full path including uploads/ prefix
      }
    }

    // Create a temporary result object with parent document info
    const parentResult = {
      metadata: {
        bucket: parentBucket,
        storage_path: parentPath, // Use the full storage path as-is
        mime_type: r.metadata.parent_storage_path?.endsWith('.pdf')
          ? 'application/pdf'
          : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        page_number: r.metadata.page_number
      }
    }

    // Reuse the existing handleOpen logic
    const url = await getSignedUrl(parentResult.metadata.bucket, parentResult.metadata.storage_path)
    if (!url) throw new Error('No URL returned')
    window.open(buildDeepLink(url, parentResult), '_blank')
  } catch (err: any) {
    toast.add({
      title: 'Could not open parent document',
      description: err.message || 'Error generating signed URL',
      color: 'error'
    })
  }
}

// ========== Auto Fetch Thumbnail URLs for Images ==========

// whenever results change, populate missing thumbnail URLs
watch(
  () => props.results,
  async (newResults) => {
    if (!newResults?.length) return
    for (const r of newResults) {
      const modality = (r.metadata?.modality || '').toLowerCase()

      // For images, fetch thumbnail URL
      if (modality === 'image' && !r.metadata?.signed_url) {
        try {
          const url = await getThumbnailUrl(
            r.metadata.bucket,
            r.metadata.storage_path
          )
          if (url) r.metadata.signed_url = url
        } catch (err) {
          console.error('Failed to get thumbnail URL for', r.metadata.storage_path, err)
        }
      }
    }
  },
  { immediate: true, deep: true }
)
</script>

<template>
  <div
    v-if="results?.length"
    class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4 gap-4"
  >
    <UCard
      v-for="r in results"
      :key="r.id"
      class="flex flex-col justify-between"
    >
      <div class="flex-1 space-y-2">
        <p class="text-xs text-gray-500">
          Score: {{ (r.score * 100).toFixed(1) }}%
        </p>

        <!-- File info row -->
        <div class="flex items-center justify-between gap-4 text-xs text-gray-500">
          <!-- Show parent document name for extracted images -->
          <span v-if="r.metadata?.source === 'extracted' && r.metadata?.parent_filename" class="flex-1 min-w-0">
            File: <strong>{{ r.metadata.parent_filename }}</strong>
            <span v-if="r.metadata?.page_number" class="ml-1">(Page {{ r.metadata.page_number }})</span>
          </span>
          <!-- Show regular title for other results -->
          <span v-else class="flex-1 min-w-0">
            File: <strong>{{ getFileName(r.metadata?.title) }}</strong>
          </span>

          <div class="flex items-center gap-2 flex-shrink-0">
            <!-- For extracted images, show "Open Document" button to open parent -->
            <UButton
              v-if="r.metadata?.source === 'extracted' && r.metadata?.parent_storage_path"
              size="xs"
              color="primary"
              variant="soft"
              icon="i-heroicons-document-text"
              @click="handleOpenParentDoc(r)"
            >
              Open Document
            </UButton>
            <!-- For regular results, show "Open" button -->
            <UButton
              v-else
              size="xs"
              color="primary"
              variant="soft"
              icon="i-heroicons-eye"
              @click="handleOpen(r)"
            >
              Open
            </UButton>

            <UButton
              v-if="(r.metadata?.mime_type || '').includes('officedocument.wordprocessingml.document')"
              size="xs"
              color="primary"
              variant="soft"
              icon="i-heroicons-arrow-down-tray"
              @click="handleDownload(r)"
            >
              Download
            </UButton>
          </div>
        </div>

        <USeparator orientation="horizontal" class="h-auto self-stretch" size="lg" />

        <!-- Render text hits -->
        <div v-if="(r.metadata?.modality || '').toLowerCase() === 'text'">
          <p>{{ r.metadata?.text }}</p>

          <!-- Display document tags if available -->
          <div v-if="r.metadata?.tags && r.metadata.tags.length > 0" class="mt-3 space-y-2">
            <p class="text-xs font-semibold text-gray-600">Document Tags:</p>
            <div class="flex flex-wrap gap-1.5">
              <UBadge
                v-for="tag in r.metadata.tags"
                :key="tag.tag_name"
                variant="soft"
                color="primary"
                size="xs"
              >
                {{ tag.tag_name }} ({{ (tag.confidence * 100).toFixed(0) }}%)
              </UBadge>
            </div>
          </div>
        </div>

        <!-- Render image hits -->
        <div v-else-if="(r.metadata?.modality || '').toLowerCase() === 'image'">
          <img
            v-if="r.metadata?.signed_url"
            :src="r.metadata.signed_url"
            :alt="r.metadata?.title || 'image result'"
            class="object-contain mx-auto p-2 rounded-md border border-gray-200"
          />
          <p v-else class="text-sm text-gray-400 italic">
            (Image loading...)
          </p>

          <!-- Display tags if available -->
          <div v-if="r.metadata?.tags && r.metadata.tags.length > 0" class="mt-2 flex flex-wrap gap-1">
            <UBadge
              v-for="tag in r.metadata.tags"
              :key="tag.tag_name"
              variant="soft"
              color="primary"
              size="xs"
            >
              {{ tag.tag_name }} ({{ (tag.confidence * 100).toFixed(0) }}%)
            </UBadge>
          </div>
        </div>

        <!-- Inline PDF preview -->
        <div v-else-if="(r.metadata?.mime_type || '').includes('application/pdf')">
          <iframe
            v-if="r.metadata?.signed_url"
            :src="buildDeepLink(r.metadata.signed_url, r)"
            width="100%"
            height="400"
            style="border: none;"
          ></iframe>
        </div>

        <!-- Inline DOCX preview -->
        <div v-else-if="(r.metadata?.mime_type || '').includes('officedocument.wordprocessingml.document')">
          <iframe
            v-if="r.metadata?.signed_url"
            :src="`https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(r.metadata.signed_url)}`"
            width="100%"
            height="400"
            frameborder="0"
          ></iframe>
        </div>

        <!-- Fallback -->
        <p v-else>{{ r.metadata?.title || '(unknown modality)' }}</p>
      </div>
    </UCard>
  </div>

  <div v-else class="text-gray-400 text-sm italic text-center py-8">
    No results found.
  </div>
</template>