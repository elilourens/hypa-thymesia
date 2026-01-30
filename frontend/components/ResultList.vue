<script setup lang="ts">
import { watch, ref, nextTick } from 'vue'
import { marked } from 'marked'
import { useFilesApi } from '~/composables/useFiles'
const { getSignedUrl, getThumbnailUrl, getVideoInfo } = useFilesApi()
const toast = useToast()

const props = defineProps<{ results: any[], deleting?: boolean }>()

// ========== Video Player Modal State ==========
const videoModalOpen = ref(false)
const videoUrl = ref('')
const videoStartTime = ref(0)
const videoFilename = ref('')
const videoLoading = ref(false)
const videoPlayer = ref<HTMLVideoElement | null>(null)

// Track which results are showing formatted text (by result id)
const showFormatted = ref<Record<string, boolean>>({})

// Configure marked for safe rendering
marked.setOptions({
  breaks: true,
  gfm: true,
})

// Render markdown text to HTML
function renderMarkdown(text: string): string {
  if (!text) return ''
  return marked(text) as string
}

// Toggle between formatted and original text
function toggleTextDisplay(resultId: string) {
  // If undefined, it was showing formatted (default), so toggle to false
  if (showFormatted.value[resultId] === undefined) {
    showFormatted.value[resultId] = false
  } else {
    showFormatted.value[resultId] = !showFormatted.value[resultId]
  }
}

// Check if a result is currently showing formatted text
function isShowingFormatted(r: any): boolean {
  const hasFormatted = r.metadata?.is_formatted && r.metadata?.formatted_text

  // If no formatted text available, we're not showing formatted
  if (!hasFormatted) {
    return false
  }

  // If state is explicitly set, use that
  if (showFormatted.value[r.id] !== undefined) {
    return showFormatted.value[r.id] === true
  }

  // Default: show formatted if it exists
  return true
}

// Strip filename from the beginning of text
function stripFilename(text: string | undefined, filename?: string): string {
  if (!text || !filename) return text || ''

  const lines = text.split('\n')
  // Remove lines that contain just the filename or the filename without extension
  const filenameWithoutExt = filename.replace(/\.[^/.]+$/, '')

  while (lines.length > 0) {
    const firstLine = lines[0].trim()
    if (firstLine === filename || firstLine === filenameWithoutExt || firstLine === filename.replace(/\.pdf$/, '')) {
      lines.shift()
    } else {
      break
    }
  }

  return lines.join('\n').trim()
}

// Get the text to display based on toggle state
function getDisplayText(r: any): string {
  const hasFormatted = r.metadata?.is_formatted && r.metadata?.formatted_text
  let text = ''

  // If no formatted text available, always show original
  if (!hasFormatted) {
    text = r.metadata?.text || ''
  } else if (isShowingFormatted(r)) {
    // If showing formatted (default), return formatted_text
    text = r.metadata?.formatted_text || r.metadata?.text || ''
  } else {
    // Otherwise show original
    text = r.metadata?.original_text || r.metadata?.text || ''
  }

  // Strip filename from beginning
  return stripFilename(text, r.metadata?.title)
}

// ========== Utility Functions ==========

function getFileName(title?: string) {
  return title || '(unknown file)'
}

// Builds URLs for deep linking
function buildDeepLink(baseUrl: string, r: any) {
  const mime = r.metadata?.mime_type || ''

  // PDF deep linking (PowerPoint is stored as PDF, so this works for both)
  if (mime.includes('application/pdf')) {
    // Use start_page from search results, or fall back to page_number
    const pageNumber = r.metadata?.start_page || r.metadata?.page_number
    if (pageNumber) {
      return `${baseUrl}#page=${pageNumber}`
    }
  }

  // DOCX viewer with page support
  if (mime.includes('officedocument.wordprocessingml.document')) {
    const pageNumber = r.metadata?.start_page || r.metadata?.page_number
    const viewerUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(baseUrl)}`
    // Office viewer supports #page parameter
    if (pageNumber) {
      return `${viewerUrl}#page=${pageNumber}`
    }
    return viewerUrl
  }

  return baseUrl
}

// ========== Actions ==========

async function handleOpen(r: any) {
  try {
    // For PowerPoint files that have been converted to PDF, use the converted PDF for viewing
    let bucket = r.metadata.bucket
    let storagePath = r.metadata.storage_path
    let mime = r.metadata.mime_type || ''

    if (r.metadata.converted_pdf_path) {
      // Use the converted PDF for viewing (better browser support)
      bucket = 'texts' // Converted PDFs are stored in the texts bucket
      storagePath = r.metadata.converted_pdf_path
      mime = 'application/pdf' // Converted PDFs are always PDFs
    }

    // Infer mime type from title if not set
    if (!mime && r.metadata?.title) {
      const title = r.metadata.title
      if (title.endsWith('.pdf')) {
        mime = 'application/pdf'
      } else if (title.endsWith('.docx') || title.endsWith('.doc')) {
        mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      }
    }

    // Pass download=false to display inline in browser
    const url = await getSignedUrl(bucket, storagePath, false)
    if (!url) throw new Error('No URL returned')

    // Create a modified result object with the inferred mime type
    const resultForDeepLink = { ...r, metadata: { ...r.metadata, mime_type: mime } }
    window.open(buildDeepLink(url, resultForDeepLink), '_blank')
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
    // Pass download=true to force download instead of inline display
    const url = await getSignedUrl(r.metadata.bucket, r.metadata.storage_path, true)
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
    let parentBucket = r.metadata.parent_bucket
    let parentPath = r.metadata.parent_storage_path

    if (!parentBucket || !parentPath) {
      throw new Error('Parent document information missing')
    }

    // Check if parent document has a converted PDF (for PowerPoint files)
    if (r.metadata.converted_pdf_path) {
      parentBucket = 'texts'
      parentPath = r.metadata.converted_pdf_path
    }

    // Create a temporary result object with parent document info
    const parentResult = {
      metadata: {
        bucket: parentBucket,
        storage_path: parentPath,
        mime_type: r.metadata.converted_pdf_path || r.metadata.parent_storage_path?.endsWith('.pdf')
          ? 'application/pdf'
          : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        page_number: r.metadata.page_number
      }
    }

    // Reuse the existing handleOpen logic
    // Pass download=false to display inline in browser
    const url = await getSignedUrl(parentResult.metadata.bucket, parentResult.metadata.storage_path, false)
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

// ========== Video Player Functions ==========

async function handlePlayVideo(r: any, timestamp: number) {
  videoLoading.value = true
  videoModalOpen.value = true
  videoStartTime.value = timestamp

  try {
    let url: string | null = null

    // Check if this is a Ragie video chunk (from Supabase storage)
    if (r.metadata?.chunk_content_type === 'video' && r.metadata?.bucket === 'supabase') {
      // Get signed URL directly from Supabase
      url = await getSignedUrl(r.metadata.bucket, r.metadata.storage_path, false)
      videoFilename.value = r.metadata?.title || 'Video'
    } else {
      // Legacy video frame hit or other video sources
      const videoId = r.metadata?.video_id
      if (!videoId) {
        throw new Error('Video ID not found in result metadata')
      }

      const info = await getVideoInfo(videoId)
      videoFilename.value = info.filename || 'Video'

      // Get signed URL for the video
      url = await getSignedUrl(info.bucket, info.storage_path, false)
    }

    if (!url) throw new Error('No URL returned')

    videoUrl.value = url

    // Wait for next tick to ensure video element is rendered, then seek
    await nextTick()
    if (videoPlayer.value) {
      videoPlayer.value.currentTime = timestamp
    }
  } catch (err: any) {
    toast.add({
      title: 'Could not load video',
      description: err.message || 'Error loading video',
      color: 'error'
    })
    videoModalOpen.value = false
  } finally {
    videoLoading.value = false
  }
}

function handleVideoLoaded() {
  // Seek to the start time once metadata is loaded
  if (videoPlayer.value && videoStartTime.value > 0) {
    videoPlayer.value.currentTime = videoStartTime.value
  }
}

function closeVideoModal() {
  videoModalOpen.value = false
  videoUrl.value = ''
  videoStartTime.value = 0
  videoFilename.value = ''
}

// ========== Helper Functions ==========

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function truncateText(text: string, maxLen: number): string {
  if (!text) return ''
  return text.length > maxLen ? text.substring(0, maxLen) + '...' : text
}

// ========== Auto Fetch Thumbnail URLs for Images and PDFs ==========

// Cache to prevent duplicate fetches (key: bucket+path)
const urlCache = ref<Map<string, string>>(new Map())
const pendingFetches = ref<Set<string>>(new Set())

// whenever results change, populate missing thumbnail URLs
watch(
  () => props.results,
  async (newResults) => {
    if (!newResults?.length) return
    for (const r of newResults) {
      const modality = (r.metadata?.modality || '').toLowerCase()

      // For images, fetch thumbnail URL
      if (modality === 'image' && !r.metadata?.signed_url) {
        const cacheKey = `${r.metadata.bucket}:${r.metadata.storage_path}`

        // Check cache first
        if (urlCache.value.has(cacheKey)) {
          r.metadata.signed_url = urlCache.value.get(cacheKey)
          continue
        }

        // Skip if already fetching
        if (pendingFetches.value.has(cacheKey)) continue

        try {
          pendingFetches.value.add(cacheKey)
          const url = await getThumbnailUrl(
            r.metadata.bucket,
            r.metadata.storage_path
          )
          if (url) {
            r.metadata.signed_url = url
            urlCache.value.set(cacheKey, url)
          }
        } catch (err) {
          console.error('Failed to get thumbnail URL for', r.metadata.storage_path, err)
        } finally {
          pendingFetches.value.delete(cacheKey)
        }
      }

      // For text results with PDFs (including converted PowerPoint), fetch signed URL for preview
      if (modality === 'text' && (r.metadata?.mime_type || '').includes('application/pdf') && !r.metadata?.signed_url) {
        // Use converted PDF path if available (for PowerPoint files)
        const bucket = r.metadata.converted_pdf_path ? 'texts' : r.metadata.bucket
        const storagePath = r.metadata.converted_pdf_path || r.metadata.storage_path
        const cacheKey = `${bucket}:${storagePath}`

        // Check cache first
        if (urlCache.value.has(cacheKey)) {
          r.metadata.signed_url = urlCache.value.get(cacheKey)
          continue
        }

        // Skip if already fetching
        if (pendingFetches.value.has(cacheKey)) continue

        try {
          pendingFetches.value.add(cacheKey)
          // Pass download=false to display inline in iframe
          const url = await getSignedUrl(bucket, storagePath, false)
          if (url) {
            r.metadata.signed_url = url
            urlCache.value.set(cacheKey, url)
          }
        } catch (err) {
          console.error('Failed to get signed URL for PDF', r.metadata.storage_path, err)
        } finally {
          pendingFetches.value.delete(cacheKey)
        }
      }

      // For video frame results, fetch signed URL for frame image
      if (r.metadata?.source === 'video_frame' && !r.metadata?.signed_url) {
        const cacheKey = `${r.metadata.bucket}:${r.metadata.storage_path}`

        // Check cache first
        if (urlCache.value.has(cacheKey)) {
          r.metadata.signed_url = urlCache.value.get(cacheKey)
          continue
        }

        // Skip if already fetching
        if (pendingFetches.value.has(cacheKey)) continue

        try {
          pendingFetches.value.add(cacheKey)
          const url = await getThumbnailUrl(
            r.metadata.bucket,
            r.metadata.storage_path
          )
          if (url) {
            r.metadata.signed_url = url
            urlCache.value.set(cacheKey, url)
          }
        } catch (err) {
          console.error('Failed to get thumbnail URL for video frame', r.metadata.storage_path, err)
        } finally {
          pendingFetches.value.delete(cacheKey)
        }
      }

      // For Ragie video chunks from Supabase, pre-fetch signed URL for caching
      if (r.metadata?.chunk_content_type === 'video' && r.metadata?.bucket === 'supabase' && !r.metadata?.signed_url) {
        const cacheKey = `${r.metadata.bucket}:${r.metadata.storage_path}`

        // Check cache first
        if (urlCache.value.has(cacheKey)) {
          r.metadata.signed_url = urlCache.value.get(cacheKey)
          continue
        }

        // Skip if already fetching
        if (pendingFetches.value.has(cacheKey)) continue

        try {
          pendingFetches.value.add(cacheKey)
          const url = await getSignedUrl(
            r.metadata.bucket,
            r.metadata.storage_path,
            false
          )
          if (url) {
            r.metadata.signed_url = url
            urlCache.value.set(cacheKey, url)
          }
        } catch (err) {
          console.error('Failed to get signed URL for video chunk', r.metadata.storage_path, err)
        } finally {
          pendingFetches.value.delete(cacheKey)
        }
      }
    }
  },
  { immediate: true }
)
</script>

<template>
  <div
    v-if="results?.length"
    class="grid gap-4"
    style="grid-template-columns: repeat(auto-fit, minmax(550px, 1fr))"
  >
    <UCard
      v-for="r in results"
      :key="r.id"
      class="flex flex-col"
    >
      <template #header>
        <div class="flex items-center justify-between w-full">
          <h3 class="font-semibold truncate">
            <!-- Show parent document name for extracted images -->
            <span v-if="r.metadata?.source === 'extracted' && r.metadata?.parent_filename">
              {{ r.metadata.parent_filename }}
              <span v-if="r.metadata?.page_number" class="text-sm font-normal text-gray-500">(Page {{ r.metadata.page_number }})</span>
            </span>
            <!-- Show regular title for other results -->
            <span v-else>{{ getFileName(r.metadata?.title) }}</span>
          </h3>
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
      </template>

      <div class="flex-1 space-y-2">
        <p class="text-xs text-gray-500">
          Score: {{ (r.score * 100).toFixed(1) }}%
        </p>

        <USeparator orientation="horizontal" class="h-auto self-stretch" size="lg" />

        <!-- Render text hits -->
        <div v-if="(r.metadata?.modality || '').toLowerCase() === 'text'">
          <!-- Toggle button for formatted/original text (only show if formatted text exists) -->
          <div v-if="r.metadata?.is_formatted && r.metadata?.formatted_text" class="mb-2 flex items-center gap-2">
            <UButton
              size="xs"
              :color="isShowingFormatted(r) ? 'primary' : 'neutral'"
              variant="soft"
              icon="i-heroicons-sparkles"
              @click="toggleTextDisplay(r.id)"
            >
              {{ isShowingFormatted(r) ? 'Formatted' : 'Original' }}
            </UButton>
            <span class="text-xs text-gray-500">
              {{ isShowingFormatted(r) ? 'Showing formatted text' : 'Showing original text' }}
            </span>
          </div>

          <!-- Render markdown if available, otherwise show plain text -->
          <div
            v-html="renderMarkdown(getDisplayText(r))"
            class="prose prose-sm max-w-none dark:prose-invert prose-headings:mt-3 prose-headings:mb-2 prose-p:my-1 prose-ul:my-1 prose-li:my-0"
          ></div>

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
            class="object-contain mx-auto p-2 rounded-md border border-gray-200 max-w-full max-h-96"
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

        <!-- Render video frame hits -->
        <div v-else-if="r.metadata?.source === 'video_frame'">
          <img
            v-if="r.metadata?.signed_url"
            :src="r.metadata.signed_url"
            :alt="`Video frame at ${r.metadata?.timestamp?.toFixed(1)}s`"
            class="object-contain mx-auto p-2 rounded-md border border-gray-200 max-w-full max-h-96"
          />
          <p v-else class="text-sm text-gray-400 italic">
            (Frame loading...)
          </p>

          <div class="mt-2 space-y-1 text-sm text-gray-600">
            <p v-if="r.metadata?.timestamp">
              <strong>Timestamp:</strong> {{ Math.floor(r.metadata.timestamp / 60) }}:{{ (r.metadata.timestamp % 60).toFixed(1).padStart(4, '0') }}
            </p>
            <p v-if="r.metadata?.scene_id">
              <strong>Scene:</strong> {{ r.metadata.scene_id }}
            </p>
          </div>

          <!-- Play Video Button -->
          <div v-if="r.metadata?.video_id" class="mt-3">
            <UButton
              size="sm"
              color="primary"
              variant="soft"
              icon="i-heroicons-play"
              @click="handlePlayVideo(r, r.metadata?.timestamp || 0)"
            >
              Play from this frame
            </UButton>
          </div>
        </div>

        <!-- Render video transcript hits -->
        <div v-else-if="r.metadata?.source === 'video_transcript'">
          <div class="p-3">
            <p class="text-sm">"{{ r.metadata?.text }}"</p>
          </div>

          <div class="mt-2 space-y-1 text-sm text-gray-600">
            <p v-if="r.metadata?.start_time !== undefined && r.metadata?.end_time !== undefined">
              <strong>Time:</strong> {{ Math.floor(r.metadata.start_time / 60) }}:{{ (r.metadata.start_time % 60).toFixed(1).padStart(4, '0') }} - {{ Math.floor(r.metadata.end_time / 60) }}:{{ (r.metadata.end_time % 60).toFixed(1).padStart(4, '0') }}
            </p>
          </div>

          <!-- Play Video Button -->
          <div v-if="r.metadata?.video_id" class="mt-3">
            <UButton
              size="sm"
              color="primary"
              variant="soft"
              icon="i-heroicons-play"
              @click="handlePlayVideo(r, r.metadata?.start_time || 0)"
            >
              Play from this segment
            </UButton>
          </div>
        </div>

        <!-- Render Ragie video chunks (from Supabase storage) -->
        <div v-else-if="r.metadata?.chunk_content_type === 'video'">
          <!-- Time Range Badge -->
          <div class="mb-3 flex gap-2 items-center">
            <UBadge color="primary" variant="soft" size="sm">
              {{ formatTime(r.metadata?.start_time || 0) }} - {{ formatTime(r.metadata?.end_time || 0) }}
            </UBadge>
            <span class="text-xs text-gray-500">
              {{ ((r.metadata?.end_time || 0) - (r.metadata?.start_time || 0)).toFixed(0) }}s clip
            </span>
          </div>

          <!-- Transcription -->
          <div class="bg-gray-50 dark:bg-gray-900 p-3 rounded-md border border-gray-200 dark:border-gray-800 mb-3">
            <p class="text-sm text-gray-700 dark:text-gray-300">
              <strong>Transcript:</strong> "{{ truncateText(r.metadata?.audio_transcript || r.metadata?.text, 250) }}"
            </p>
          </div>

          <!-- Video Description -->
          <div v-if="r.metadata?.video_description" class="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-md border border-blue-200 dark:border-blue-800 mb-3">
            <p class="text-sm text-blue-700 dark:text-blue-300">
              <strong>Visual:</strong> {{ truncateText(r.metadata?.video_description, 250) }}
            </p>
          </div>

          <!-- Play Button -->
          <div class="flex gap-2">
            <UButton
              size="sm"
              color="primary"
              icon="i-heroicons-play"
              @click="handlePlayVideo(r, r.metadata?.start_time || 0)"
            >
              Play from {{ formatTime(r.metadata?.start_time || 0) }}
            </UButton>
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

  <!-- Video Player Modal -->
  <UModal v-model:open="videoModalOpen" :ui="{ content: 'w-[calc(100vw-2rem)] max-w-4xl' }">
    <template #content>
      <div class="p-4">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold">{{ videoFilename }}</h3>
          <UButton
            icon="i-heroicons-x-mark"
            color="neutral"
            variant="ghost"
            size="sm"
            @click="closeVideoModal"
          />
        </div>

        <div v-if="videoLoading" class="flex items-center justify-center h-64">
          <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin text-gray-400" />
        </div>

        <video
          v-else-if="videoUrl"
          ref="videoPlayer"
          :src="videoUrl"
          controls
          autoplay
          class="w-full rounded-lg"
          @loadedmetadata="handleVideoLoaded"
        >
          Your browser does not support video playback.
        </video>
      </div>
    </template>
  </UModal>
</template>