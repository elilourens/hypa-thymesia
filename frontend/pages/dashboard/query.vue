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

// ========== Search Mode Toggle ==========
const searchMode = ref<'files' | 'content'>('files')

// ========== Common State ==========
const queryTextInput = ref('')
const selectedGroup = ref<string | null>(null)
const hasSearched = ref(false)

// ========== Mode 1: Files Search State ==========
const filesLoading = ref(false)
const filesError = ref<string | null>(null)
const filesResults = ref<DocumentItem[]>([])
const filenameMatches = ref<DocumentItem[]>([])
const semanticMatches = ref<DocumentItem[]>([])
const chunkMap = ref<Map<string, any>>(new Map())

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

// ========== Mode 2: Content Search State ==========
const loading = ref(false)
const error = ref<string | null>(null)
const results = ref<any[]>([])
const selectedModality = ref<string | null>(null)

const modalityOptions = [
  { label: 'All', value: null },
  { label: 'Text', value: 'text' },
  { label: 'Images', value: 'image' },
  { label: 'Videos', value: 'video' },
]

// ========== Computed: Filtered Results ==========
const filteredFilenameMatches = computed(() => {
  if (!selectedFileType.value) return filenameMatches.value
  return filenameMatches.value.filter(f =>
    f.mime_type?.includes(selectedFileType.value!) ?? false
  )
})

const filteredSemanticMatches = computed(() => {
  if (!selectedFileType.value) return semanticMatches.value
  return semanticMatches.value.filter(f =>
    f.mime_type?.includes(selectedFileType.value!) ?? false
  )
})

// ========== Mode 1: File Loading & Search ==========

async function loadDefaultFiles() {
  filesLoading.value = true
  filesError.value = null
  filesPage.value = 1
  hasSearched.value = false

  try {
    const response = await listDocuments({
      sort: 'created_at',
      dir: 'desc',
      page: 1,
      page_size: 20,
      group_id: selectedGroup.value || undefined,
    })

    filesResults.value = response.items
    filenameMatches.value = response.items
    semanticMatches.value = []
    chunkMap.value.clear()
    filesHasMore.value = response.has_more ?? false
    filesTotal.value = response.total ?? 0
  } catch (e: any) {
    filesError.value = e?.message ?? 'Failed to load files'
  } finally {
    filesLoading.value = false
  }
}

async function searchFilesOnly() {
  if (!queryTextInput.value.trim()) {
    await loadDefaultFiles()
    return
  }

  hasSearched.value = true
  filesLoading.value = true
  filesError.value = null

  try {
    const filenameResults = await listDocuments({
      search: queryTextInput.value,
      group_id: selectedGroup.value || undefined,
      sort: 'created_at',
      dir: 'desc',
    })

    // Show filename matches immediately
    filenameMatches.value = filenameResults.items

    // Trigger lazy semantic search
    debouncedSearchSemantic()
  } catch (e: any) {
    filesError.value = e?.message ?? 'Search failed'
  } finally {
    filesLoading.value = false
  }
}

async function searchSemantic() {
  if (!queryTextInput.value.trim() || !hasSearched.value) {
    return
  }

  try {
    const semanticResults = await search({
      query: queryTextInput.value,
      top_k: 20,
      rerank: true,
      group_id: selectedGroup.value || undefined,
      max_chunks_per_document: 1,
    })

    chunkMap.value.clear()

    // Process semantic results: collect unique documents and store chunks
    const semanticDocMap = new Map<string, DocumentItem>()
    const filenameDocMap = new Map(filenameMatches.value.map(d => [d.id, d]))
    const docsToFetch = new Set<string>()

    // Collect document IDs we need to fetch
    for (const chunk of semanticResults.scored_chunks) {
      const docId = chunk.document_id

      // Store chunk for hover preview
      if (!chunkMap.value.has(docId)) {
        chunkMap.value.set(docId, chunk)
      }

      // Check if we already have it from filename search
      if (filenameDocMap.has(docId)) {
        semanticDocMap.set(docId, filenameDocMap.get(docId)!)
      } else {
        // Mark for fetching
        docsToFetch.add(docId)
      }
    }

    // Fetch full document details for semantic-only matches
    if (docsToFetch.size > 0) {
      const fetchPromises = Array.from(docsToFetch).map(docId =>
        getDocument(docId)
          .then(doc => {
            semanticDocMap.set(docId, doc)
            // Also update chunkMap with the correct internal id for hover preview
            const chunk = chunkMap.value.get(docId)
            if (chunk) {
              chunkMap.value.set(doc.id, chunk)
            }
          })
          .catch(() => {
            // If fetch fails, create minimal document from chunk metadata
            const chunk = Array.from(semanticResults.scored_chunks).find(
              c => c.document_id === docId
            )
            if (chunk) {
              const fallbackDoc = {
                id: docId,
                filename: chunk.metadata?.title || 'Document',
                mime_type: '',
                file_size_bytes: null,
                status: 'ready' as const,
                chunk_count: null,
                page_count: chunk.metadata?.end_page || null,
                group_id: null,
                group_name: null,
                user_id: '',
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              }
              semanticDocMap.set(docId, fallbackDoc)
              // Store with internal id for hover preview lookup
              chunkMap.value.set(fallbackDoc.id, chunk)
            }
          })
      )
      await Promise.all(fetchPromises)
    }

    semanticMatches.value = Array.from(semanticDocMap.values())
  } catch (e: any) {
    console.error('Semantic search failed:', e)
  }
}

async function loadMoreFiles() {
  if (!filesHasMore.value || filesLoading.value || queryTextInput.value.trim()) {
    return
  }

  filesPage.value += 1
  filesLoading.value = true

  try {
    const response = await listDocuments({
      sort: 'created_at',
      dir: 'desc',
      page: filesPage.value,
      page_size: 20,
      group_id: selectedGroup.value || undefined,
    })

    filesResults.value = [...filesResults.value, ...response.items]
    filenameMatches.value = [...filenameMatches.value, ...response.items]
    filesHasMore.value = response.has_more ?? false
    filesTotal.value = response.total ?? 0
  } catch (e: any) {
    filesError.value = e?.message ?? 'Failed to load more files'
  } finally {
    filesLoading.value = false
  }
}

// Debounced versions: fast filename search + lazy semantic search
const debouncedSearchFiles = useDebounceFn(searchFilesOnly, 150)
const debouncedSearchSemantic = useDebounceFn(searchSemantic, 500)

// ========== Mode 2: Content Search ==========

async function run() {
  error.value = null
  results.value = []

  if (!queryTextInput.value.trim()) {
    error.value = 'Enter a search query'
    return
  }

  try {
    loading.value = true

    const response = await search({
      query: queryTextInput.value,
      top_k: 10,
      rerank: true,
      group_id: selectedGroup.value || undefined,
      modality: selectedModality.value || undefined,
    })

    // Transform Ragie response to match ResultList format
    results.value = response.scored_chunks.map((chunk: any) => {
      // Determine modality based on mime_type or source
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
          title: chunk.metadata?.filename || 'Document',
          text: chunk.text,
          document_id: chunk.document_id,
          chunk_id: chunk.chunk_id,
          modality,
          ...chunk.metadata,
        },
      }
    })
  } catch (e: any) {
    error.value = e?.message ?? 'Search failed'
  } finally {
    loading.value = false
  }
}

// ========== Lifecycle & Watchers ==========

onMounted(() => {
  if (searchMode.value === 'files') {
    loadDefaultFiles()
  }
})

watch(searchMode, (newMode) => {
  if (newMode === 'files' && !filesResults.value.length) {
    loadDefaultFiles()
  }
})

watch(selectedGroup, () => {
  if (searchMode.value === 'files') {
    if (queryTextInput.value.trim()) {
      debouncedSearchFiles()
    } else {
      loadDefaultFiles()
    }
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
    // Remove from all local lists
    const id = fileToDelete.value.id
    filenameMatches.value = filenameMatches.value.filter(f => f.id !== id)
    semanticMatches.value = semanticMatches.value.filter(f => f.id !== id)
    filesResults.value = filesResults.value.filter(f => f.id !== id)
    toast.add({ title: 'File deleted', color: 'success' })
  } catch (e: any) {
    toast.add({ title: 'Delete failed', description: e.message, color: 'error' })
  } finally {
    showDeleteConfirm.value = false
    fileToDelete.value = null
  }
}

// ========== Copy Results ==========

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

      <!-- Mode Toggle -->
      <UTabs
        v-model="searchMode"
        :items="[
          { label: 'Search Files', value: 'files', icon: 'i-lucide-folder' },
          { label: 'Search Content', value: 'content', icon: 'i-lucide-search' }
        ]"
        class="w-full"
      />

      <!-- Search bar and filters -->
      <div class="flex flex-col gap-4">
        <div class="flex gap-4">
          <UInput
            v-model="queryTextInput"
            size="xl"
            :placeholder="searchMode === 'files'
              ? 'Search by filename or content...'
              : 'Search across all your documents...'"
            class="w-full text-lg"
            @keyup.enter="searchMode === 'files' ? debouncedSearchFiles() : run()"
            @input="searchMode === 'files' ? debouncedSearchFiles() : null"
          />
          <UButton
            v-if="searchMode === 'content'"
            :disabled="loading || !queryTextInput.trim()"
            @click="run"
          >
            {{ loading ? 'Searching…' : 'Search' }}
          </UButton>
        </div>

        <div class="flex gap-4">
          <GroupSelect v-model="selectedGroup" includeAll />

          <!-- File type filter (Mode 1) -->
          <USelectMenu
            v-if="searchMode === 'files'"
            v-model="selectedFileType"
            :items="fileTypeOptions"
            value-key="value"
            placeholder="Filter by file type…"
            icon="i-lucide-file"
            clearable
            class="w-full"
          />

          <!-- Modality filter (Mode 2) -->
          <USelectMenu
            v-else
            v-model="selectedModality"
            :items="modalityOptions"
            value-key="value"
            placeholder="Filter by type…"
            :search-input="{ placeholder: 'Search types…' }"
            icon="i-lucide-layers"
            clearable
            class="w-full"
          />
        </div>
      </div>

      <p v-if="filesError || error" class="text-red-500 text-sm">
        {{ filesError || error }}
      </p>
    </div>
  </BodyCard>

  <!-- Results Section -->
  <BodyCard>
    <div class="py-8">
      <!-- Mode 1: Files Search -->
      <div v-if="searchMode === 'files'" class="space-y-8">
        <!-- Filename Matches / Default Files Section -->
        <div v-if="filteredFilenameMatches.length > 0">
          <div v-if="hasSearched" class="flex items-center gap-2 mb-4 px-2">
            <UIcon name="i-lucide-file-search" class="w-5 h-5" />
            <h2 class="text-lg font-semibold">
              Filename Matches ({{ filteredFilenameMatches.length }})
            </h2>
          </div>
          <FileGrid
            :files="filteredFilenameMatches"
            :loading="filesLoading"
            :enable-hover-preview="true"
            :chunk-map="chunkMap"
            :context-menu-items="fileContextMenuItems"
            @open-file="handleOpenFile"
          />
        </div>

        <!-- Divider -->
        <div v-if="hasSearched && filteredFilenameMatches.length > 0 && filteredSemanticMatches.length > 0" class="border-t border-foreground/10 my-4" />

        <!-- Semantic Matches Section (only show after search) -->
        <div v-if="hasSearched && filteredSemanticMatches.length > 0">
          <div class="flex items-center gap-2 mb-4 px-2">
            <UIcon name="i-lucide-sparkles" class="w-5 h-5" />
            <h2 class="text-lg font-semibold">
              Semantic Matches ({{ filteredSemanticMatches.length }})
            </h2>
          </div>
          <FileGrid
            :files="filteredSemanticMatches"
            :loading="filesLoading"
            :enable-hover-preview="true"
            :chunk-map="chunkMap"
            :context-menu-items="fileContextMenuItems"
            @open-file="handleOpenFile"
          />
        </div>

        <!-- Loading State -->
        <div v-if="filesLoading && !filteredFilenameMatches.length && !filteredSemanticMatches.length" class="text-center py-12">
          <UIcon name="i-lucide-loader-2" class="w-8 h-8 mx-auto animate-spin text-foreground/50" />
          <p class="mt-4 text-foreground/60">Loading files...</p>
        </div>

        <!-- Empty State -->
        <div
          v-if="!filesLoading && !filteredFilenameMatches.length && !filteredSemanticMatches.length"
          class="text-center py-12 text-foreground/50"
        >
          <UIcon name="i-lucide-folder-open" class="w-12 h-12 mx-auto mb-4" />
          <p class="text-lg">
            {{ hasSearched ? 'No files found' : 'No files yet' }}
          </p>
        </div>

        <!-- Load More Button (only for default file list) -->
        <div v-if="filesHasMore && !queryTextInput" class="text-center mt-8">
          <UButton
            @click="loadMoreFiles"
            :loading="filesLoading"
            variant="outline"
            color="primary"
          >
            Load More ({{ filesResults.length }} / {{ filesTotal }})
          </UButton>
        </div>
      </div>

      <!-- Mode 2: Content Search -->
      <div v-if="searchMode === 'content'" class="space-y-4">
        <div v-if="results.length > 0" class="flex justify-end">
          <UButton
            icon="i-lucide-copy"
            color="primary"
            variant="soft"
            @click="copyAllChunks"
          >
            {{ copyFeedback ? 'Copied!' : 'Copy all chunks' }}
          </UButton>
        </div>
        <ResultList :results="results" />
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
