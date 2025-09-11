<script setup lang="ts">
import { ref } from 'vue'
import { useIngest } from '@/composables/useIngest'
import { NO_GROUP_VALUE } from '@/composables/useGroups'
import GroupSelect from '@/components/GroupSelect.vue'
import BodyCard from '@/components/BodyCard.vue';

const { queryText, deleteDoc } = useIngest()

const queryRoute = ref<'text'|'image'>('text')
const queryTextInput = ref('')
const loading = ref(false)
const error = ref<string|null>(null)
const results = ref<any[]>([])
const deleting = ref(false)

// Use reusable GroupSelect
const selectedGroup = ref<string | null>(null) // null = All groups

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

async function onDelete(id: string) {
  try {
    deleting.value = true
    await deleteDoc(id)
    results.value = results.value.filter(m => m?.metadata?.doc_id !== id)
  } catch (e:any) {
    error.value = e?.message ?? 'Delete failed'
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <BodyCard>
    <div class="space-y-4 max-w-xl">
      <h1 class="font-semibold text-lg">Search</h1>

      <UInput v-model="queryTextInput" placeholder="Enter text query..."/>

      <div class="flex gap-4 text-sm">
        <label><input type="radio" value="text" v-model="queryRoute"> text→text</label>
        <label><input type="radio" value="image" v-model="queryRoute"> text→image</label>
      </div>

      <!-- Reusable GroupSelect -->
      <GroupSelect v-model="selectedGroup" includeAll includeNoGroup />

      <UButton :disabled="loading || !queryTextInput" @click="run">
        {{ loading ? 'Searching…' : 'Search' }}
      </UButton>

      <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>

      <ResultList :results="results" :deleting="deleting" @delete="onDelete" />
    </div>
  </BodyCard>
  
</template>
