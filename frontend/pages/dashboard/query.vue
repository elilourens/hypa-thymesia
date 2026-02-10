<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { useSearch } from '@/composables/useSearch'
import { useDocuments, type DocumentItem } from '@/composables/useDocuments'
import GroupSelect from '@/components/GroupSelect.vue'
import BodyCard from '@/components/BodyCard.vue'
import ResultList from '@/components/ResultList.vue'
import FileGrid, { type ContextMenuItem } from '@/components/FileGrid.vue'
import { useFilesApi } from '@/composables/useFiles'


const { search } = useSearch()
const { listDocuments, getDocument, deleteDocument } = useDocuments()
const { getSignedUrl, getVideoInfo } = useFilesApi()
const toast = useToast()

// ========== Dual Search State ==========
const queryTextInput = ref('')
const selectedGroup = ref<string | null>(null)
const hasSearched = ref(false)
const loading = ref(false)
const semanticLoading = ref(false)
const error = ref<string | null>(null)

// ========== Results State ==========
const filenameMatches = ref<DocumentItem[]>([])
const semanticMatches = ref<DocumentItem[]>([])
const results = ref<any[]>([]) // Semantic chunks
const chunkMap = ref<Map<string, any>>(new Map())

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

// Pagination state for default file list
const filesPage = ref(1)
const filesHasMore = ref(false)
const filesTotal = ref(0)

// ========== Computed: Filtered Results ==========
const filteredFilenameMatches = computed(() => {
  if (!selectedFileType.value) return filenameMatches.value
  return filenameMatches.value.filter((f: DocumentItem) =>
    f.mime_type?.includes(selectedFileType.value!) ?? false
  )
})

const filteredSemanticMatches = computed(() => {
  if (!selectedFileType.value) return semanticMatches.value
  return semanticMatches.value.filter((f: DocumentItem) =>
    f.mime_type?.includes(selectedFileType.value!) ?? false
  )
})

const filteredChunks = computed(() => {
  if (!selectedFileType.value) return results.value
  return results.value.filter(chunk => {
    const mime = chunk.metadata?.mime_type || ''
    return mime.includes(selectedFileType.value!)
  })
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

// ========== Lifecycle & Watchers ==========

onMounted(() => {
  loadDefaultFiles()
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
    icon: 'i-lucide-external-link',
    action: (file) => handleOpenFile(file),
  },
  {
    label: 'Copy filename',
    icon: 'i-lucide-copy',
    action: async (file) => {
      await navigator.clipboard.writeText(file.filename)
      toast.add({ title: 'Copied filename', color: 'success' })
    },
  },
  {
    label: 'Delete',
    icon: 'i-lucide-trash-2',
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

        <div class="flex gap-4">
          <GroupSelect v-model="selectedGroup" includeAll />
          <USelectMenu
            v-model="selectedFileType"
            :items="fileTypeOptions"
            value-key="value"
            placeholder="Filter by file type…"
            icon="i-lucide-file"
            clearable
            class="w-full"
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
          <div class="flex items-center gap-2 px-2">
            <UIcon name="i-lucide-file-text" class="w-5 h-5" />
            <h2 class="text-lg font-semibold">Filename Matches</h2>
            <span class="text-sm text-foreground/60">({{ filteredFilenameMatches.length }})</span>
          </div>
          <FileGrid
            :files="filteredFilenameMatches"
            :loading="loading"
            :enable-hover-preview="true"
            :chunk-map="chunkMap"
            :context-menu-items="fileContextMenuItems"
            @open-file="handleOpenFile"
          />
        </div>
      </div>

      <!-- Semantic Matches Section -->
      <div v-if="filteredSemanticMatches.length > 0 || semanticLoading" class="space-y-8">
        <div v-if="filteredFilenameMatches.length > 0" class="border-t border-foreground/10 my-4" />
        <div class="space-y-3">
          <div class="flex items-center gap-2 px-2">
            <UIcon :name="semanticLoading ? 'i-lucide-loader-2' : 'i-lucide-brain'" :class="semanticLoading ? 'w-5 h-5 animate-spin' : 'w-5 h-5'" />
            <h2 class="text-lg font-semibold">Semantic Matches</h2>
            <span class="text-sm text-foreground/60">({{ filteredSemanticMatches.length }})</span>
          </div>
          <div v-if="semanticLoading && filteredSemanticMatches.length === 0" class="text-center py-8">
            <UIcon name="i-lucide-loader-2" class="w-6 h-6 mx-auto animate-spin text-foreground/50 mb-2" />
            <p class="text-sm text-foreground/60">Analyzing content...</p>
          </div>
          <FileGrid
            v-if="filteredSemanticMatches.length > 0"
            :files="filteredSemanticMatches"
            :loading="semanticLoading"
            :enable-hover-preview="true"
            :chunk-map="chunkMap"
            :context-menu-items="fileContextMenuItems"
            @open-file="handleOpenFile"
          />
        </div>
      </div>

      <!-- Chunks Section -->
      <div v-if="filteredChunks.length > 0 || semanticLoading" class="space-y-8">
        <div v-if="filteredFilenameMatches.length > 0 || filteredSemanticMatches.length > 0" class="border-t border-foreground/10 my-4" />
        <div class="space-y-3">
          <div class="flex items-center gap-2 px-2">
            <UIcon :name="semanticLoading ? 'i-lucide-loader-2' : 'i-lucide-sparkles'" :class="semanticLoading ? 'w-5 h-5 animate-spin' : 'w-5 h-5'" />
            <h2 class="text-lg font-semibold">Relevant Content</h2>
            <span class="text-sm text-foreground/60">({{ filteredChunks.length }})</span>
          </div>
          <div class="flex justify-end mb-4" v-if="filteredChunks.length > 0">
            <UButton
              icon="i-lucide-copy"
              color="primary"
              variant="soft"
              @click="copyAllChunks"
            >
              {{ copyFeedback ? 'Copied!' : 'Copy all chunks' }}
            </UButton>
          </div>
          <div v-if="semanticLoading && filteredChunks.length === 0" class="text-center py-8">
            <UIcon name="i-lucide-loader-2" class="w-6 h-6 mx-auto animate-spin text-foreground/50 mb-2" />
            <p class="text-sm text-foreground/60">Extracting relevant content...</p>
          </div>
          <ResultList v-if="filteredChunks.length > 0" :results="filteredChunks" />
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="loading && !filteredFilenameMatches.length && !filteredSemanticMatches.length && !filteredChunks.length" class="text-center py-12">
        <UIcon name="i-lucide-loader-2" class="w-8 h-8 mx-auto animate-spin text-foreground/50" />
        <p class="mt-4 text-foreground/60">Searching...</p>
      </div>

      <!-- Empty State -->
      <div
        v-if="!loading && !filteredFilenameMatches.length && !filteredSemanticMatches.length && !filteredChunks.length"
        class="text-center py-12 text-foreground/50"
      >
        <UIcon name="i-lucide-folder-open" class="w-12 h-12 mx-auto mb-4" />
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
</template>
