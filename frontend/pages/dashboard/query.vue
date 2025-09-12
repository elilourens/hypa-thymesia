<script setup lang="ts">
import { ref } from 'vue'
import type { RadioGroupItem } from '@nuxt/ui'
import { useIngest } from '@/composables/useIngest'
import { NO_GROUP_VALUE } from '@/composables/useGroups'
import GroupSelect from '@/components/GroupSelect.vue'
import BodyCard from '@/components/BodyCard.vue';

const { queryText } = useIngest()

const queryRoute = ref<'text'|'image'>('text')
const queryTextInput = ref('')
const loading = ref(false)
const error = ref<string|null>(null)
const results = ref<any[]>([])

// Group selection
const selectedGroup = ref<string | null>(null) // null = All groups

// Radio items for route selection
const routeItems: RadioGroupItem[] = [
  { value: 'text', label: 'Text' },
  { value: 'image', label: 'Images' }
]

// ---- Actions ----
async function run() {
  if (!queryTextInput.value.trim()) { 
    error.value = 'Enter a query'
    return
  }
  error.value = null
  results.value = []
  try {
    loading.value = true

    const group_id =
      selectedGroup.value === NO_GROUP_VALUE
        ? '' // backend interprets "" as ungrouped
        : selectedGroup.value || undefined

    const r = await queryText({
      query: queryTextInput.value,
      route: queryRoute.value,
      top_k: 10,
      group_id
    })

    results.value = r.matches || []
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

      <!-- Larger search bar -->
      <UInput
        v-model="queryTextInput"
        size="xl"
        placeholder="Enter your search..."
        class="w-full text-lg py-4"
      />

      <!-- Radio + GroupSelect on same line -->
      <div class="flex flex-col sm:flex-row gap-4 ">
        <URadioGroup
          v-model="queryRoute"
          orientation="horizontal"
          variant="list"
          :items="routeItems"
        />
        <GroupSelect v-model="selectedGroup" includeAll includeNoGroup />
      </div>

      <div class="flex justify-center">
        <UButton :disabled="loading || !queryTextInput" @click="run">
          {{ loading ? 'Searching…' : 'Search' }}
        </UButton>
      </div>

      <p v-if="error" class="text-red-500 text-sm text-center">{{ error }}</p>

      <!-- Results (no delete feature) -->
      <ResultList :results="results" />
    </div>
  </BodyCard>
</template>
