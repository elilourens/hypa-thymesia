<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { RadioGroupItem } from '@nuxt/ui'
import { useIngest } from '@/composables/useIngest'
import { NO_GROUP_VALUE } from '@/composables/useGroups'
import GroupSelect from '@/components/GroupSelect.vue'
import BodyCard from '@/components/BodyCard.vue';
import ResultList from '@/components/ResultList.vue'

const { queryText, queryVideo, queryByTags, queryImagesByTags, getUserTags } = useIngest()

const queryRoute = ref<'text'|'image'|'extracted_image'|'video'|'tags'>('text') // UPDATED
const queryTextInput = ref('')
const loading = ref(false)
const error = ref<string|null>(null)
const results = ref<any[]>([])

// Group selection
const selectedGroup = ref<string | null>(null) // null = All groups

// Search mode for text search
const searchMode = ref<'smart' | 'keyword'>('smart') // NEW: smart or keyword search

// Tag-based search
const tagSearchMode = ref<'document' | 'image'>('document') // NEW: toggle between doc/image tags
const selectedTags = ref<string[]>([])
const selectedCategory = ref<string | undefined>(undefined)
const userTagCategories = ref<Record<string, string[]>>({})
const loadingTags = ref(false)

// Video search sub-route
const videoRoute = ref<'video_frames'|'video_transcript'|'video_combined'>('video_frames')

// Radio items for route selection - UPDATED
const routeItems: RadioGroupItem[] = [
  { value: 'text', label: 'Text' },
  { value: 'image', label: 'Uploaded Images' },
  { value: 'extracted_image', label: 'Document Images' },
  { value: 'video', label: 'Videos' }, // NEW
  { value: 'tags', label: 'By Tags' }
]

// Category options for dropdown
const categoryOptions = computed(() => {
  return Object.keys(userTagCategories.value).map((key) => ({
    label: key.replace(/_/g, ' '),
    value: key
  }))
})

// Tag options based on selected category (for documents) or all tags (for images)
const tagOptions = computed(() => {
  // For image tags, show all tags (no category filtering)
  if (tagSearchMode.value === 'image') {
    const allTags: string[] = []
    // Handle both null and string keys
    Object.entries(userTagCategories.value).forEach(([_, tags]) => {
      if (Array.isArray(tags)) {
        allTags.push(...tags)
      }
    })
    // Remove duplicates and sort
    const uniqueTags = [...new Set(allTags)].sort()
    return uniqueTags.map((tag: string) => ({
      label: tag.replace(/_/g, ' '),
      value: tag
    }))
  }

  // For document tags, filter by selected category
  if (!selectedCategory.value || !userTagCategories.value[selectedCategory.value]) {
    return []
  }
  const tags = userTagCategories.value[selectedCategory.value] || []
  return tags.map((tag: string) => ({
    label: tag.replace(/_/g, ' '),
    value: tag
  }))
})

// Load user's tags based on current mode
async function loadUserTags() {
  try {
    loadingTags.value = true
    const response = await getUserTags(tagSearchMode.value)
    userTagCategories.value = response.categories
    // Reset selections when switching modes
    selectedTags.value = []
    selectedCategory.value = undefined
  } catch (e: any) {
    console.error('Failed to load user tags:', e)
  } finally {
    loadingTags.value = false
  }
}

// Reload tags when switching between document/image mode
watch(tagSearchMode, () => {
  if (queryRoute.value === 'tags') {
    loadUserTags()
  }
})

// Load tags when switching to tags route
watch(queryRoute, (newRoute) => {
  if (newRoute === 'tags' && Object.keys(userTagCategories.value).length === 0) {
    loadUserTags()
  }
})

// ---- Actions ----
async function run() {
  error.value = null
  results.value = []

  try {
    loading.value = true

    const group_id =
      selectedGroup.value === NO_GROUP_VALUE
        ? '' // backend interprets "" as ungrouped
        : selectedGroup.value || undefined

    // Tag-based search
    if (queryRoute.value === 'tags') {
      if (!selectedTags.value.length) {
        error.value = 'Select at least one tag'
        return
      }

      // Document tag search
      if (tagSearchMode.value === 'document') {
        const r = await queryByTags({
          tags: selectedTags.value,
          category: selectedCategory.value || undefined,
          group_id,
          min_confidence: 0.5,
          limit: 50
        })

        // Transform results to match expected format for ResultList
        results.value = r.results.map((doc: any) => {
          // Get the first text chunk for storage info
          const firstChunk = doc.chunks?.find((c: any) => c.modality === 'text') || doc.chunks?.[0]

          return {
            id: doc.doc_id,
            score: doc.avg_confidence,
            metadata: {
              title: doc.filename || '(unknown file)',  // ResultList expects 'title' not 'filename'
              filename: doc.filename,
              doc_id: doc.doc_id,
              group_id: doc.group_id,
              tags: doc.tags,
              text_chunks: doc.text_chunks,
              image_chunks: doc.image_chunks,
              modality: 'text',
              // Add storage info from first chunk so ResultList can open/download
              bucket: firstChunk?.bucket,
              storage_path: firstChunk?.storage_path,
              mime_type: firstChunk?.mime_type
            }
          }
        })
      }
      // Image tag search
      else {
        const r = await queryImagesByTags({
          tags: selectedTags.value,
          group_id,
          min_confidence: 0.0,  // No filtering - return all tagged images
          limit: 50
        })

        console.log('Image search results:', r)

        // Transform image results to match expected format for ResultList
        results.value = r.results.map((img: any) => {
          return {
            id: img.chunk_id,
            score: img.avg_confidence,
            metadata: {
              title: 'Image',
              chunk_id: img.chunk_id,
              doc_id: img.doc_id,
              group_id: img.group_id,
              tags: img.tags,
              modality: 'image',
              bucket: img.bucket,
              storage_path: img.storage_path,
              mime_type: img.mime_type
            }
          }
        })
      }
    }
    // Video search
    else if (queryRoute.value === 'video') {
      if (!queryTextInput.value.trim()) {
        error.value = 'Enter a query'
        return
      }

      const r = await queryVideo({
        query: queryTextInput.value,
        route: videoRoute.value,
        top_k: 10,
        group_id
      })

      results.value = r.matches || []
    }
    // Text/image search
    else {
      if (!queryTextInput.value.trim()) {
        error.value = 'Enter a query'
        return
      }

      // Type assertion: we know it's not 'tags' or 'video' here due to the if blocks above
      const route = queryRoute.value as 'text' | 'image' | 'extracted_image'

      const r = await queryText({
        query: queryTextInput.value,
        route,
        top_k: 10,
        group_id,
        search_mode: searchMode.value // Pass search mode to backend
      })

      results.value = r.matches || []
    }
  } catch (e:any) {
    error.value = e?.message ?? 'Search failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <BodyCard>
    <div class="space-y-6 max-w-3xl mx-auto">
      <h1 class="font-semibold text-xl">Search</h1>

      <!-- Radio for search type -->
      <URadioGroup
        v-model="queryRoute"
        orientation="horizontal"
        variant="list"
        :items="routeItems"
      />

      <!-- Video sub-route selection -->
      <div v-if="queryRoute === 'video'" class="flex gap-2">
        <UButton
          :variant="videoRoute === 'video_frames' ? 'solid' : 'outline'"
          @click="videoRoute = 'video_frames'"
        >
          Visual
        </UButton>
        <UButton
          :variant="videoRoute === 'video_transcript' ? 'solid' : 'outline'"
          @click="videoRoute = 'video_transcript'"
        >
          Audio
        </UButton>
        <UButton
          :variant="videoRoute === 'video_combined' ? 'solid' : 'outline'"
          @click="videoRoute = 'video_combined'"
        >
          Both
        </UButton>
      </div>

      <!-- Text/Image/Video search bar -->
      <div v-if="queryRoute !== 'tags'" class="flex flex-col sm:flex-row gap-4">
        <UInput
          v-model="queryTextInput"
          size="xl"
          :placeholder="queryRoute === 'video' ? 'Search videos...' : 'Enter your search...'"
          class="w-full text-lg"
        />
        <div class="flex justify-center">
          <UButton :disabled="loading || !queryTextInput" @click="run">
            {{ loading ? 'Searching…' : 'Search' }}
          </UButton>
        </div>
      </div>

      <!-- Tag-based search -->
      <div v-else class="space-y-4">
        <!-- Document/Image Toggle -->
        <div class="flex gap-2">
          <UButton
            :variant="tagSearchMode === 'document' ? 'solid' : 'outline'"
            @click="tagSearchMode = 'document'"
          >
            Document Tags
          </UButton>
          <UButton
            :variant="tagSearchMode === 'image' ? 'solid' : 'outline'"
            @click="tagSearchMode = 'image'"
          >
            Image Tags
          </UButton>
        </div>

        <div class="flex flex-col gap-4">
          <!-- Document tags: category dropdown -->
          <USelectMenu
            v-if="tagSearchMode === 'document'"
            v-model="selectedCategory"
            :items="categoryOptions"
            value-key="value"
            placeholder="Select category..."
            class="w-full"
            :disabled="loadingTags"
            clearable
          />

          <!-- Tags dropdown + Search button on same row -->
          <div class="flex gap-4">
            <USelectMenu
              v-model="selectedTags"
              :items="tagOptions"
              value-key="value"
              :placeholder="tagSearchMode === 'document' ? 'Browse tags...' : 'Browse image tags...'"
              class="flex-1"
              multiple
              searchable
              :disabled="(tagSearchMode === 'document' && !selectedCategory) || loadingTags"
              :search-input="{ placeholder: 'Search tags...' }"
            >
              <template #default>
                <span class="text-muted truncate">
                  {{ tagSearchMode === 'document' ? 'Browse tags...' : 'Browse image tags...' }}
                </span>
              </template>
              <template #empty>
                <span class="text-muted">
                  {{ tagSearchMode === 'document'
                    ? (selectedCategory ? 'No tags available' : 'Select a category first')
                    : 'No image tags available'
                  }}
                </span>
              </template>
            </USelectMenu>

            <UButton :disabled="loading || !selectedTags.length" @click="run">
              {{ loading ? 'Searching…' : 'Search' }}
            </UButton>
          </div>
        </div>

        <!-- Selected tags display -->
        <div v-if="selectedTags.length" class="flex flex-wrap gap-2">
          <UBadge
            v-for="tag in selectedTags"
            :key="tag"
            color="primary"
            variant="subtle"
            class="cursor-pointer hover:bg-primary-600 transition-colors"
            @click="selectedTags = selectedTags.filter(t => t !== tag)"
          >
            <span class="flex items-center gap-1">
              {{ tag.replace(/_/g, ' ') }}
              <span class="text-xs opacity-70">✕</span>
            </span>
          </UBadge>
        </div>
      </div>

      <!-- Smart/Keyword toggle + Group filter row -->
      <div class="flex justify-between items-center gap-4">
        <!-- Smart vs Keyword toggle (only for text search) -->
        <div v-if="queryRoute === 'text'" class="flex gap-2">
          <UButton
            :variant="searchMode === 'smart' ? 'solid' : 'outline'"
            @click="searchMode = 'smart'"
          >
            Smart Search
          </UButton>
          <UButton
            :variant="searchMode === 'keyword' ? 'solid' : 'outline'"
            @click="searchMode = 'keyword'"
          >
            Keyword Search
          </UButton>
        </div>
        <div v-else></div>

        <!-- Group filter -->
        <GroupSelect v-model="selectedGroup" includeAll includeNoGroup />
      </div>

      <USeparator orientation="horizontal" class="h-auto self-stretch" size="lg"/>

      <p v-if="error" class="text-red-500 text-sm text-center">{{ error }}</p>
    </div>
  </BodyCard>
  <div class="m-10 p-2">
    <ResultList :results="results" />
  </div>
</template>