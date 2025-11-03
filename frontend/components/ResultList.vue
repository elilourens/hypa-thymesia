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

function renderHighlightedText(
  text?: string,
  spans?: { start: number; end: number; term: string }[]
) {
  if (!text) return ''
  if (!spans?.length) return text

  let out = ''
  let last = 0
  for (const s of [...spans].sort((a, b) => a.start - b.start)) {
    out += text.slice(last, s.start)
    out += `<span class="bg-primary text-black rounded px-0.5">${text.slice(
      s.start,
      s.end
    )}</span>`
    last = s.end
  }
  out += text.slice(last)
  return out
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
    // Check if this is a Google Drive file
    if (r.metadata?.storage_provider === 'google_drive' && r.metadata?.external_id) {
      const viewUrl = `https://drive.google.com/file/d/${r.metadata.external_id}/preview`
      window.open(viewUrl, '_blank')
      return
    }

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
    // Check if this is a Google Drive file
    if (r.metadata?.storage_provider === 'google_drive' && r.metadata?.external_id) {
      const downloadUrl = `https://drive.google.com/uc?export=download&id=${r.metadata.external_id}`
      window.open(downloadUrl, '_blank')
      return
    }

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
            r.metadata.storage_path,
            r.metadata.mime_type
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
        <div class="flex items-center justify-between text-xs text-gray-500">
          <span>
            File: <strong>{{ getFileName(r.metadata?.title) }}</strong>
            <span v-if="r.metadata?.storage_provider === 'google_drive'" class="ml-1 inline-block">
              <UBadge variant="subtle" size="xs" color="primary">Google Drive</UBadge>
            </span>
          </span>

          <div class="flex items-center gap-2">
            <UButton
              size="xs"
              color="primary"
              variant="soft"
              icon="i-heroicons-eye"
              @click="handleOpen(r)"
            >
              Open
            </UButton>

            <UButton
              v-if="(r.metadata?.mime_type || '').includes('officedocument.wordprocessingml.document') || r.metadata?.storage_provider === 'google_drive'"
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
        <p v-if="(r.metadata?.modality || '').toLowerCase() === 'text'">
          <span
            v-html="renderHighlightedText(r.metadata?.text, r.metadata?.highlight_spans)"
          />
        </p>

        <!-- Render image hits -->
        <div v-else-if="(r.metadata?.modality || '').toLowerCase() === 'image'">
          <img
            v-if="r.metadata?.signed_url"
            :src="r.metadata.signed_url"
            :alt="r.metadata?.title || 'image result'"
            class="object-contain mx-auto p-2 rounded-md border border-gray-200"
            :title="r.metadata?.storage_provider === 'google_drive' ? 'Google Drive image' : 'Uploaded image'"
          />
          <p v-else class="text-sm text-gray-400 italic">
            (Image loading...)
          </p>
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