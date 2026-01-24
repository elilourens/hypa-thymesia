<script setup lang="ts">
import { ref } from 'vue'
import { useSearch } from '@/composables/useSearch'
import GroupSelect from '@/components/GroupSelect.vue'
import BodyCard from '@/components/BodyCard.vue'
import ResultList from '@/components/ResultList.vue'

const { search } = useSearch()

const queryTextInput = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const results = ref<any[]>([])
const selectedGroup = ref<string | null>(null)
const selectedModality = ref<string | null>(null)

const modalityOptions = [
  { label: 'All', value: null },
  { label: 'Text', value: 'text' },
  { label: 'Images', value: 'image' },
  { label: 'Videos', value: 'video' },
]

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
</script>

<template>
  <BodyCard>
    <div class="space-y-6 max-w-3xl mx-auto">
      <h1 class="font-semibold text-xl">Search Documents</h1>

      <!-- Search bar and group filter -->
      <div class="flex flex-col gap-4">
        <div class="flex gap-4">
          <UInput
            v-model="queryTextInput"
            size="xl"
            placeholder="Search across all your documents..."
            class="w-full text-lg"
            @keyup.enter="run"
          />
          <UButton :disabled="loading || !queryTextInput.trim()" @click="run">
            {{ loading ? 'Searching…' : 'Search' }}
          </UButton>
        </div>

        <div class="flex gap-4">
          <GroupSelect v-model="selectedGroup" includeAll />
          <USelectMenu
            :model-value="selectedModality"
            @update:model-value="selectedModality = $event"
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

      <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>
    </div>
  </BodyCard>

  <div class="m-10 p-2">
    <ResultList :results="results" />
  </div>
</template>
