<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { useSearch } from '@/composables/useSearch'
import { useDocuments, type DocumentItem } from '@/composables/useDocuments'
import { useGroupsCache } from '@/composables/useGroupsCache'
import { NO_GROUP_VALUE } from '@/composables/useGroups'
import { useDocumentUploadNotifications } from '@/composables/useDocumentUploadNotifications'
import GroupSelect from '@/components/GroupSelect.vue'
import BodyCard from '@/components/BodyCard.vue'
import ResultList from '@/components/ResultList.vue'
import FileGrid, { type ContextMenuItem } from '@/components/FileGrid.vue'
import { useFilesApi } from '@/composables/useFiles'


const { search } = useSearch()
const { listDocuments, getDocument, deleteDocument, updateDocumentGroup } = useDocuments()
const { groups: cachedGroups } = useGroupsCache()
const { getSignedUrl, getVideoInfo } = useFilesApi()
const { onUploadComplete } = useDocumentUploadNotifications()
const toast = useToast()

// ========== Dual Search State ==========
const queryTextInput = ref('')
const selectedGroup = ref<string | null>(null)
const hasSearched = ref(false)
const loading = ref(false)
const semanticLoading = ref(false)
const error = ref<string | null>(null)

// ========== View Mode State ==========
const viewMode = ref<'grid' | 'list'>(
  typeof window !== 'undefined'
    ? (localStorage.getItem('fileViewMode') as 'grid' | 'list') || 'grid'
    : 'grid'
)

watch(viewMode, (newMode) => {
  if (typeof window !== 'undefined') {
    localStorage.setItem('fileViewMode', newMode)
  }
})

// ========== Results State ==========
const filenameMatches = ref<DocumentItem[]>([])
const semanticMatches = ref<DocumentItem[]>([])
const results = ref<any[]>([]) // Semantic chunks
const chunkMap = ref<Map<string, any>>(new Map())

// ========== Bulk Selection State ==========
const selectedFileIds = ref<string[]>([])

// ========== Group Update State ==========
const updatingGroupIds = ref<Set<string>>(new Set())
const selectedGroupForBulk = ref<string | null>(null)

// ========== Filtering State ==========
const selectedFileType = ref<string | null>(null)
const fileTypeOptions = [
  { label: 'All', value: null },
  { label: 'PDFs', value: 'application/pdf' },
  { label: 'Images', value: 'image/' },
  { label: 'Videos', value: 'video/' },
  { label: 'Word Docs', value: 'wordprocessingml' },
  { label: 'Excel', value: 'spreadsheetml' },
  { label: 'PowerPoint', value: 'presentationml' },
  { label: 'Audio', value: 'audio/' },
  { label: 'Text', value: 'text/' },
]

const selectedPageCount = ref<string | null>(null)
const pageCountOptions = [
  { label: 'All Pages', value: null },
  { label: '1-10 pages', value: '1-10' },
  { label: '11-50 pages', value: '11-50' },
  { label: '51-100 pages', value: '51-100' },
  { label: '100+ pages', value: '100+' },
]

// Pagination state for default file list
const filesPage = ref(1)
const filesHasMore = ref(false)
const filesTotal = ref(0)

// Group colors state (computed from cached groups)
const groupColors = computed(() =>
  Object.fromEntries(cachedGroups.value.map(g => [g.id, g.color]))
)

// ========== Helper: Page Count Filter ==========
function matchesPageCountFilter(pageCount?: number | null): boolean {
  if (!selectedPageCount.value || !pageCount) return true

  const range = selectedPageCount.value
  if (range === '1-10') return pageCount >= 1 && pageCount <= 10
  if (range === '11-50') return pageCount >= 11 && pageCount <= 50
  if (range === '51-100') return pageCount >= 51 && pageCount <= 100
  if (range === '100+') return pageCount > 100

  return true
}

// ========== Computed: Filtered Results ==========
const filteredFilenameMatches = computed(() => {
  let filtered = filenameMatches.value

  // Filter by file type
  if (selectedFileType.value) {
    filtered = filtered.filter((f: DocumentItem) =>
      f.mime_type?.includes(selectedFileType.value!) ?? false
    )
  }

  // Filter by page count
  if (selectedPageCount.value) {
    filtered = filtered.filter((f: DocumentItem) =>
      matchesPageCountFilter(f.page_count)
    )
  }

  return filtered
})

const filteredSemanticMatches = computed(() => {
  let filtered = semanticMatches.value

  // Filter by file type
  if (selectedFileType.value) {
    filtered = filtered.filter((f: DocumentItem) =>
      f.mime_type?.includes(selectedFileType.value!) ?? false
    )
  }

  // Filter by page count
  if (selectedPageCount.value) {
    filtered = filtered.filter((f: DocumentItem) =>
      matchesPageCountFilter(f.page_count)
    )
  }

  return filtered
})

const filteredChunks = computed(() => {
  let filtered = results.value

  // Filter by file type
  if (selectedFileType.value) {
    filtered = filtered.filter(chunk => {
      const mime = chunk.metadata?.mime_type || ''
      return mime.includes(selectedFileType.value!)
    })
  }

  // Filter by page count
  if (selectedPageCount.value) {
    filtered = filtered.filter(chunk => {
      const pageCount = chunk.metadata?.page_count
      return matchesPageCountFilter(pageCount)
    })
  }

  return filtered
})

// ========== Dual Search & File Loading ==========

async function loadDefaultFiles() {
  loading.value = true
  error.value = null
  filesPage.value = 1
  hasSearched.value = false
  filenameMatches.value = []
  semanticMatches.value = []
  results.value = []

  try {
    const response = await listDocuments({
      sort: 'created_at',
      dir: 'desc',
      page: 1,
      page_size: 20,
      group_id: selectedGroup.value || undefined,
    })

    filenameMatches.value = response.items
    chunkMap.value.clear()
    filesHasMore.value = response.has_more ?? false
    filesTotal.value = response.total ?? 0
  } catch (e: any) {
    error.value = e?.message ?? 'Failed to load files'
  } finally {
    loading.value = false
  }
}

// Fast filename search (150ms debounce - instant results)
async function searchFilesOnly() {
  if (!queryTextInput.value.trim()) {
    await loadDefaultFiles()
    return
  }

  hasSearched.value = true
  loading.value = true
  error.value = null

  try {
    const filenameResults = await listDocuments({
      search: queryTextInput.value,
      group_id: selectedGroup.value || undefined,
      sort: 'created_at',
      dir: 'desc',
      page: 1,
      page_size: 20,
    })

    filenameMatches.value = filenameResults.items
  } catch (e: any) {
    error.value = e?.message ?? 'Filename search failed'
  } finally {
    loading.value = false
  }
}

// Delayed semantic search (500ms debounce - lazy results)
async function searchSemantic() {
  if (!queryTextInput.value.trim()) {
    semanticMatches.value = []
    results.value = []
    semanticLoading.value = false
    return
  }

  semanticLoading.value = true

  try {
    const semanticResults = await search({
      query: queryTextInput.value,
      top_k: 20,
      rerank: true,
      group_id: selectedGroup.value || undefined,
      max_chunks_per_document: 0, // Get all chunks
    })

    // Extract unique doc IDs from semantic chunks
    const semanticDocIds = new Set<string>()
    for (const chunk of semanticResults.scored_chunks) {
      semanticDocIds.add(chunk.document_id)
    }

    // Fetch full document metadata for semantic matches
    const semanticDocs = await Promise.all(
      Array.from(semanticDocIds).map(async (docId) => {
        try {
          return await getDocument(docId)
        } catch (err) {
          console.error('Failed to fetch document:', docId, err)
          return null
        }
      })
    )

    semanticMatches.value = semanticDocs.filter((d): d is DocumentItem => d !== null)

    // Store chunks for ResultList
    results.value = semanticResults.scored_chunks.map((chunk: any) => {
      let modality = 'text'
      const mimeType = chunk.metadata?.mime_type || ''
      const source = chunk.metadata?.source || ''

      if (source === 'video_frame') {
        modality = 'video_frame'
      } else if (source === 'video_transcript') {
        modality = 'video_transcript'
      } else if (mimeType.includes('image')) {
        modality = 'image'
      }

      return {
        id: chunk.chunk_id,
        score: chunk.score,
        metadata: {
          title: chunk.metadata?.title || chunk.metadata?.filename || 'Document',
          text: chunk.text,
          document_id: chunk.document_id,
          chunk_id: chunk.chunk_id,
          modality,
          ...chunk.metadata,
        },
      }
    })
  } catch (e: any) {
    error.value = e?.message ?? 'Semantic search failed'
  } finally {
    semanticLoading.value = false
  }
}

async function loadMoreFiles() {
  if (!filesHasMore.value || loading.value || queryTextInput.value.trim()) {
    return
  }

  filesPage.value += 1
  loading.value = true

  try {
    const response = await listDocuments({
      sort: 'created_at',
      dir: 'desc',
      page: filesPage.value,
      page_size: 20,
      group_id: selectedGroup.value || undefined,
    })

    filenameMatches.value = [...filenameMatches.value, ...response.items]
    filesHasMore.value = response.has_more ?? false
    filesTotal.value = response.total ?? 0
  } catch (e: any) {
    error.value = e?.message ?? 'Failed to load more files'
  } finally {
    loading.value = false
  }
}

// Debounced searches
const debouncedSearchFiles = useDebounceFn(searchFilesOnly, 150) // Fast filename search
const debouncedSearchSemantic = useDebounceFn(searchSemantic, 500) // Delayed semantic search

// ========== Auto-Refresh on Upload Complete ==========

/**
 * Refresh results when a file finishes processing
 */
function refreshAfterUpload(fileId: string, filename: string, success: boolean) {
  if (!success) return // Only refresh on successful uploads

  // If user is searching, re-run search to include new file
  if (queryTextInput.value.trim()) {
    searchFilesOnly()
    searchSemantic()
  } else {
    // Otherwise reload default file list
    loadDefaultFiles()
  }
}

// ========== Lifecycle & Watchers ==========

let unsubscribeUploadComplete: (() => void) | null = null

onMounted(() => {
  loadDefaultFiles()

  // Listen for upload completion events
  unsubscribeUploadComplete = onUploadComplete(refreshAfterUpload)
})

onBeforeUnmount(() => {
  // Clean up event listener
  if (unsubscribeUploadComplete) {
    unsubscribeUploadComplete()
  }
})

watch(selectedGroup, () => {
  if (queryTextInput.value.trim()) {
    debouncedSearchFiles()
    debouncedSearchSemantic()
  } else {
    loadDefaultFiles()
  }
})

// ========== File Opening ==========

async function handleOpenFile(file: DocumentItem) {
  try {
    const mime = file.mime_type || ''
    let url: string

    // For videos, fetch from Supabase storage (cheaper egress than Ragie)
    if (mime.startsWith('video/')) {
      const info = await getVideoInfo(file.id)
      url = await getSignedUrl(info.bucket, info.storage_path, false)
    } else {
      url = await getSignedUrl('ragie', file.ragie_document_id || file.id, false)
    }

    if (!url) throw new Error('No URL returned')

    if (mime.includes('application/pdf')) {
      window.open(`${url}#page=1`, '_blank')
    } else if (mime.includes('officedocument.wordprocessingml.document')) {
      window.open(`https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(url)}`, '_blank')
    } else {
      window.open(url, '_blank')
    }
  } catch (err: any) {
    toast.add({
      title: 'Could not open file',
      description: err.message || 'Error opening file',
      color: 'error',
    })
  }
}

// ========== Copy Results ==========

const copyFeedback = ref(false)

// ========== Context Menu ==========

const fileToDelete = ref<DocumentItem | null>(null)
const showDeleteConfirm = ref(false)

const fileContextMenuItems: ContextMenuItem[] = [
  {
    label: 'Open',
    icon: 'i-heroicons-arrow-top-right-on-square',
    action: (file) => handleOpenFile(file),
  },
  {
    label: 'Copy filename',
    icon: 'i-heroicons-clipboard-document',
    action: async (file) => {
      await navigator.clipboard.writeText(file.filename)
      toast.add({ title: 'Copied filename', color: 'success' })
    },
  },
  {
    label: 'Delete',
    icon: 'i-heroicons-trash',
    separator: true,
    action: (file) => {
      fileToDelete.value = file
      showDeleteConfirm.value = true
    },
  },
]

async function confirmDelete() {
  if (!fileToDelete.value) return
  try {
    await deleteDocument(fileToDelete.value.id)
    // Remove from local lists
    const id = fileToDelete.value.id
    filenameMatches.value = filenameMatches.value.filter(f => f.id !== id)
    semanticMatches.value = semanticMatches.value.filter(f => f.id !== id)
    toast.add({ title: 'File deleted', color: 'success' })
  } catch (e: any) {
    toast.add({ title: 'Delete failed', description: e.message, color: 'error' })
  } finally {
    showDeleteConfirm.value = false
    fileToDelete.value = null
  }
}

async function copyAllChunks() {
  const allText = results.value
    .map((result: any) => result.metadata?.text || '')
    .filter(Boolean)
    .join('\n\n---\n\n')

  try {
    await navigator.clipboard.writeText(allText)
    copyFeedback.value = true
    setTimeout(() => {
      copyFeedback.value = false
    }, 2000)
  } catch (err) {
    console.error('Failed to copy:', err)
  }
}

// ========== Bulk Delete State ==========
const showBulkDeleteConfirm = ref(false)
const deletingIds = ref<Set<string>>(new Set())

// ========== Bulk Group Update ==========

async function updateSelectedFilesGroup() {
  if (selectedFileIds.value.length === 0) {
    toast.add({ title: 'No files selected', color: 'warning' })
    return
  }

  if (selectedGroupForBulk.value === null) {
    toast.add({ title: 'Please select a group', color: 'warning' })
    return
  }

  updatingGroupIds.value = new Set(selectedFileIds.value)

  try {
    // Convert NO_GROUP_VALUE sentinel to null
    const groupId = selectedGroupForBulk.value === NO_GROUP_VALUE
      ? null
      : selectedGroupForBulk.value

    // Update each file
    for (const id of selectedFileIds.value) {
      await updateDocumentGroup(id, groupId)

      // Update local state in both arrays
      const filenameFile = filenameMatches.value.find(f => f.id === id)
      if (filenameFile) {
        filenameFile.group_id = groupId
        filenameFile.group_name = null
      }

      const semanticFile = semanticMatches.value.find(f => f.id === id)
      if (semanticFile) {
        semanticFile.group_id = groupId
        semanticFile.group_name = null
      }
    }

    toast.add({
      title: `Updated ${selectedFileIds.value.length} file(s)`,
      color: 'success',
      icon: 'i-heroicons-check'
    })

    // Clear selections
    selectedGroupForBulk.value = null
    selectedFileIds.value = []

  } catch (e: any) {
    toast.add({
      title: e?.message ?? 'Failed to update files',
      color: 'error',
      icon: 'i-heroicons-exclamation-triangle'
    })
  } finally {
    updatingGroupIds.value.clear()
  }
}

// ========== Bulk Delete ==========

async function confirmBulkDelete() {
  deletingIds.value = new Set(selectedFileIds.value)

  try {
    // Delete each file
    for (const id of selectedFileIds.value) {
      await deleteDocument(id)

      // Remove from local state
      filenameMatches.value = filenameMatches.value.filter(f => f.id !== id)
      semanticMatches.value = semanticMatches.value.filter(f => f.id !== id)
    }

    toast.add({
      title: `Deleted ${selectedFileIds.value.length} file(s)`,
      color: 'success',
      icon: 'i-heroicons-check'
    })

    // Clear selections
    selectedFileIds.value = []
    showBulkDeleteConfirm.value = false

  } catch (e: any) {
    toast.add({
      title: e?.message ?? 'Failed to delete files',
      color: 'error',
      icon: 'i-heroicons-exclamation-triangle'
    })
  } finally {
    deletingIds.value.clear()
  }
}
</script>

<template>
  <BodyCard>
    <div class="space-y-6 max-w-4xl mx-auto">
      <h1 class="font-semibold text-xl">Search Documents</h1>

      <!-- Search bar and filters -->
      <div class="flex flex-col gap-4">
        <div class="flex gap-4">
          <UInput
            v-model="queryTextInput"
            size="xl"
            placeholder="Search files and content..."
            class="w-full text-lg"
            @keyup.enter="debouncedSearchFiles(); debouncedSearchSemantic()"
            @input="debouncedSearchFiles(); debouncedSearchSemantic()"
          />
        </div>

        <div class="flex gap-4 flex-wrap">
          <GroupSelect v-model="selectedGroup" includeAll />
          <USelectMenu
            v-model="selectedFileType"
            :items="fileTypeOptions"
            value-key="value"
            placeholder="Filter by file type…"
            icon="i-heroicons-document"
            clearable
            class="w-64"
          />
          <USelectMenu
            v-model="selectedPageCount"
            :items="pageCountOptions"
            value-key="value"
            placeholder="Filter by page count…"
            icon="i-heroicons-document-text"
            clearable
            class="w-64"
          />
        </div>
      </div>

      <p v-if="error" class="text-red-500 text-sm">
        {{ error }}
      </p>
    </div>
  </BodyCard>

  <!-- Results Section -->
  <BodyCard class="glass-bg">
    <div class="py-8">
      <!-- Filename Matches Section -->
      <div v-if="filteredFilenameMatches.length > 0" class="space-y-8">
        <div class="space-y-3">
          <div class="flex items-center justify-between mb-3 px-2">
            <div class="flex items-center gap-2">
              <UIcon name="i-heroicons-document-text" class="w-5 h-5" />
              <h2 class="text-lg font-semibold">Filename Matches</h2>
              <span class="text-sm text-foreground/60">({{ filteredFilenameMatches.length }})</span>
            </div>
            <div class="flex gap-1 bg-neutral-800/50 rounded-lg p-1">
              <UButton
                icon="i-heroicons-squares-2x2"
                :variant="viewMode === 'grid' ? 'solid' : 'ghost'"
                :color="viewMode === 'grid' ? 'primary' : 'neutral'"
                size="sm"
                @click="viewMode = 'grid'"
                aria-label="Grid view"
              />
              <UButton
                icon="i-heroicons-list-bullet"
                :variant="viewMode === 'list' ? 'solid' : 'ghost'"
                :color="viewMode === 'list' ? 'primary' : 'neutral'"
                size="sm"
                @click="viewMode = 'list'"
                aria-label="List view"
              />
            </div>
          </div>
          <FileGrid
            :files="filteredFilenameMatches"
            :loading="loading"
            :enable-hover-preview="true"
            :chunk-map="chunkMap"
            :context-menu-items="fileContextMenuItems"
            :enable-selection="true"
            :group-colors="groupColors"
            :view-mode="viewMode"
            v-model:selected-ids="selectedFileIds"
            @open-file="handleOpenFile"
          />
        </div>
      </div>

      <!-- Semantic Matches Section -->
      <div v-if="filteredSemanticMatches.length > 0 || semanticLoading" class="space-y-8">
        <div v-if="filteredFilenameMatches.length > 0" class="border-t border-foreground/10 my-4" />
        <div class="space-y-3">
          <div class="flex items-center justify-between mb-3 px-2">
            <div class="flex items-center gap-2">
              <UIcon :name="semanticLoading ? 'i-heroicons-arrow-path' : 'i-heroicons-cpu-chip'" :class="semanticLoading ? 'w-5 h-5 animate-spin' : 'w-5 h-5'" />
              <h2 class="text-lg font-semibold">Semantic Matches</h2>
              <span class="text-sm text-foreground/60">({{ filteredSemanticMatches.length }})</span>
            </div>
            <div class="flex gap-1 bg-neutral-800/50 rounded-lg p-1">
              <UButton
                icon="i-heroicons-squares-2x2"
                :variant="viewMode === 'grid' ? 'solid' : 'ghost'"
                :color="viewMode === 'grid' ? 'primary' : 'neutral'"
                size="sm"
                @click="viewMode = 'grid'"
                aria-label="Grid view"
              />
              <UButton
                icon="i-heroicons-list-bullet"
                :variant="viewMode === 'list' ? 'solid' : 'ghost'"
                :color="viewMode === 'list' ? 'primary' : 'neutral'"
                size="sm"
                @click="viewMode = 'list'"
                aria-label="List view"
              />
            </div>
          </div>
          <div v-if="semanticLoading && filteredSemanticMatches.length === 0" class="text-center py-8">
            <UIcon name="i-heroicons-arrow-path" class="w-6 h-6 mx-auto animate-spin text-foreground/50 mb-2" />
            <p class="text-sm text-foreground/60">Analyzing content...</p>
          </div>
          <FileGrid
            v-if="filteredSemanticMatches.length > 0"
            :files="filteredSemanticMatches"
            :loading="semanticLoading"
            :enable-hover-preview="true"
            :chunk-map="chunkMap"
            :context-menu-items="fileContextMenuItems"
            :enable-selection="true"
            :group-colors="groupColors"
            :view-mode="viewMode"
            v-model:selected-ids="selectedFileIds"
            @open-file="handleOpenFile"
          />
        </div>
      </div>

      <!-- Chunks Section -->
      <div v-if="filteredChunks.length > 0 || semanticLoading" class="space-y-8">
        <div v-if="filteredFilenameMatches.length > 0 || filteredSemanticMatches.length > 0" class="border-t border-foreground/10 my-4" />
        <div class="space-y-3">
          <div class="flex items-center gap-2 px-2">
            <UIcon :name="semanticLoading ? 'i-heroicons-arrow-path' : 'i-heroicons-sparkles'" :class="semanticLoading ? 'w-5 h-5 animate-spin' : 'w-5 h-5'" />
            <h2 class="text-lg font-semibold">Relevant Content</h2>
            <span class="text-sm text-foreground/60">({{ filteredChunks.length }})</span>
          </div>
          <div class="flex justify-end mb-4" v-if="filteredChunks.length > 0">
            <UButton
              icon="i-heroicons-clipboard-document"
              color="primary"
              variant="soft"
              @click="copyAllChunks"
            >
              {{ copyFeedback ? 'Copied!' : 'Copy all chunks' }}
            </UButton>
          </div>
          <div v-if="semanticLoading && filteredChunks.length === 0" class="text-center py-8">
            <UIcon name="i-heroicons-arrow-path" class="w-6 h-6 mx-auto animate-spin text-foreground/50 mb-2" />
            <p class="text-sm text-foreground/60">Extracting relevant content...</p>
          </div>
          <ResultList v-if="filteredChunks.length > 0" :results="filteredChunks" />
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="loading && !filteredFilenameMatches.length && !filteredSemanticMatches.length && !filteredChunks.length" class="text-center py-12">
        <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 mx-auto animate-spin text-foreground/50" />
        <p class="mt-4 text-foreground/60">Searching...</p>
      </div>

      <!-- Empty State -->
      <div
        v-if="!loading && !filteredFilenameMatches.length && !filteredSemanticMatches.length && !filteredChunks.length"
        class="text-center py-12 text-foreground/50"
      >
        <UIcon name="i-heroicons-folder-open" class="w-12 h-12 mx-auto mb-4" />
        <p class="text-lg">
          {{ hasSearched ? 'No results found' : 'Start typing to search files and content' }}
        </p>
      </div>

      <!-- Load More Button (only for default file list) -->
      <div v-if="filesHasMore && !queryTextInput" class="text-center mt-8">
        <UButton
          @click="loadMoreFiles"
          :loading="loading"
          variant="outline"
          color="primary"
        >
          Load More ({{ filenameMatches.length }} / {{ filesTotal }})
        </UButton>
      </div>
    </div>
  </BodyCard>

  <!-- Delete Confirmation Modal -->
  <UModal v-model:open="showDeleteConfirm">
    <template #content>
      <div class="p-6 space-y-4">
        <h3 class="text-lg font-semibold">Delete file</h3>
        <p class="text-foreground/70">
          Are you sure you want to delete <strong>{{ fileToDelete?.filename }}</strong>? This action cannot be undone.
        </p>
        <div class="flex justify-end gap-3">
          <UButton variant="ghost" @click="showDeleteConfirm = false">Cancel</UButton>
          <UButton color="error" @click="confirmDelete">Delete</UButton>
        </div>
      </div>
    </template>
  </UModal>

  <!-- Bulk Actions Popup (Bottom of Screen) -->
  <Transition
    enter-active-class="transition-all duration-300"
    enter-from-class="translate-y-full opacity-0"
    enter-to-class="translate-y-0 opacity-100"
    leave-active-class="transition-all duration-300"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="translate-y-full opacity-0"
  >
    <div v-if="selectedFileIds.length > 0" class="fixed bottom-0 left-0 right-0 z-40 bg-black/80 backdrop-blur-sm border-t border-foreground/10 shadow-2xl">
      <div class="max-w-6xl mx-auto px-6 py-4">
        <div class="flex flex-wrap gap-4 items-center justify-between">
          <div class="text-sm font-medium text-foreground">
            {{ selectedFileIds.length }} file(s) selected
          </div>

          <div class="flex flex-wrap gap-4 items-center">
            <div class="flex items-center gap-2">
              <label class="text-sm font-medium">Set Group:</label>
              <GroupSelect
                v-model="selectedGroupForBulk"
                :include-no-group="true"
              />
            </div>

            <UButton
              color="primary"
              icon="i-heroicons-check"
              variant="outline"
              size="sm"
              :disabled="!selectedFileIds.length || !selectedGroupForBulk || updatingGroupIds.size > 0"
              :loading="updatingGroupIds.size > 0"
              @click="updateSelectedFilesGroup"
            >
              Apply to Selected
            </UButton>

            <UButton
              variant="outline"
              color="neutral"
              size="sm"
              @click="selectedFileIds = []"
            >
              Clear Selection
            </UButton>

            <div class="border-l border-foreground/10" />

            <UButton
              color="error"
              icon="i-heroicons-trash"
              variant="outline"
              size="sm"
              @click="showBulkDeleteConfirm = true"
            >
              Delete Selected
            </UButton>
          </div>
        </div>
      </div>
    </div>
  </Transition>

  <!-- Bulk Delete Confirmation Modal -->
  <UModal v-model:open="showBulkDeleteConfirm">
    <template #content>
      <div class="p-6 space-y-4">
        <h3 class="text-lg font-semibold">Delete files</h3>
        <p class="text-foreground/70">
          Are you sure you want to delete <strong>{{ selectedFileIds.length }} file(s)</strong>? This action cannot be undone.
        </p>
        <div class="flex justify-end gap-3">
          <UButton variant="ghost" @click="showBulkDeleteConfirm = false">Cancel</UButton>
          <UButton
            color="error"
            :loading="deletingIds.size > 0"
            @click="confirmBulkDelete"
          >
            Delete
          </UButton>
        </div>
      </div>
    </template>
  </UModal>
</template>
