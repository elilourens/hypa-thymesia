<script setup lang="ts">
import { ref } from 'vue'
const { queryText, deleteDoc } = useIngest()

const queryRoute = ref<'text'|'image'>('text')
const queryTextInput = ref('')
const loading = ref(false)
const error = ref<string|null>(null)
const results = ref<any[]>([])
const deleting = ref(false)

async function run() {
  if (!queryTextInput.value.trim()) { error.value = 'Enter a query'; return }
  error.value = null; results.value = []
  try {
    loading.value = true
    const r = await queryText({ query: queryTextInput.value, route: queryRoute.value, top_k: 10 })
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
  <div class="space-y-4 max-w-xl">
    <h1 class="font-semibold text-lg">Search (Text)</h1>
    <UInput v-model="queryTextInput" placeholder="Enter text query..."
      class="[&>input]:text-black [&>input::placeholder]:text-gray-400"/>
    <div class="flex gap-4 text-sm">
      <label><input type="radio" value="text" v-model="queryRoute"> text→text</label>
      <label><input type="radio" value="image" v-model="queryRoute"> text→image</label>
    </div>
    <UButton :disabled="loading || !queryTextInput" @click="run">
      {{ loading ? 'Searching…' : 'Search' }}
    </UButton>
    <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>

    <ResultList :results="results" :deleting="deleting" @delete="onDelete" />
  </div>
</template>
