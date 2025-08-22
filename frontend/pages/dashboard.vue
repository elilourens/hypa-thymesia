<script setup lang="ts">
import { ref } from 'vue'

const supabase = useSupabaseClient()
const user = useSupabaseUser()
const API_BASE = useRuntimeConfig().public.apiBase ?? 'http://127.0.0.1:8000'

const files = ref<File[]>([])
const queryText = ref('')
const results = ref<any[]>([])
const loading = ref(false)
const error = ref<string|null>(null)

// --- NEW: delete state ---
const deleteDocId = ref('')
const deleting = ref(false)
const deleteMsg = ref<string|null>(null)

// --- Upload ---
async function uploadFile() {
  const file = files.value[0]
  if (!file) return

  const { data: ses } = await supabase.auth.getSession()
  const token = ses.session?.access_token
  if (!token) { error.value = 'Not logged in'; return }

  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await fetch(`${API_BASE}/ingest/upload-text-and-images`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    if (!res.ok) throw new Error(await res.text())
    console.log('Uploaded:', await res.json())
  } catch (e: any) {
    error.value = e.message
  }
}

// --- Query ---
async function runQuery() {
  if (!queryText.value.trim()) {
    error.value = 'Enter a query'
    return
  }

  const { data: ses } = await supabase.auth.getSession()
  const token = ses.session?.access_token
  if (!token) { error.value = 'Not logged in'; return }

  loading.value = true
  error.value = null
  results.value = []

  try {
    const res = await fetch(`${API_BASE}/ingest/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ query_text: queryText.value, top_k: 10, modality_filter: 'text' }),
    })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    results.value = data.matches
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// --- NEW: Delete (by doc_id field) ---
async function deleteDocumentById() {
  const id = deleteDocId.value.trim()
  if (!id) return

  const { data: ses } = await supabase.auth.getSession()
  const token = ses.session?.access_token
  if (!token) { error.value = 'Not logged in'; return }

  deleting.value = true
  deleteMsg.value = null
  error.value = null

  try {
    const url = new URL(`${API_BASE}/ingest/delete-document`)
    url.searchParams.set('doc_id', id)
    const res = await fetch(url.toString(), {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    })
    const text = await res.text()
    if (!res.ok) throw new Error(text)
    deleteMsg.value = `Deleted document ${id}`
    // Optional: remove any results that belong to this doc
    results.value = results.value.filter(r => r?.metadata?.doc_id !== id)
  } catch (e: any) {
    error.value = e.message
  } finally {
    deleting.value = false
  }
}

// --- NEW: Delete directly from a result (uses r.metadata.doc_id) ---
async function deleteDocumentFromResult(r: any) {
  const id = r?.metadata?.doc_id
  if (!id) {
    error.value = 'No doc_id found on this result'
    return
  }
  deleteDocId.value = id
  await deleteDocumentById()
}
</script>

<template>
  <div class="space-y-6 max-w-xl">
    <p v-if="user">User: <b>{{ user.email }}</b></p>

    <!-- Upload -->
    <div>
      <h2 class="font-semibold">Upload Files</h2>
      <UFileUpload
        v-model="files"
        multiple
        label="Drop your file here"
        layout="list"
        description="PDF, DOCX, TXT, PNG, JPG"
        class="w-96 min-h-48"
        accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
      />
      <UButton class="mt-2" :disabled="!files.length" @click="uploadFile">Upload</UButton>
    </div>

    <!-- Query -->
    <div>
      <h2 class="font-semibold">Search Text</h2>
      <UInput v-model="queryText" placeholder="Enter text query..." />
      <UButton class="mt-2" :disabled="loading || !queryText" @click="runQuery">
        {{ loading ? 'Searching...' : 'Search' }}
      </UButton>
      <p v-if="error" class="text-red-500 text-sm mt-2">{{ error }}</p>
    </div>

    <!-- NEW: Delete by doc_id -->
    <div>
      <h2 class="font-semibold">Delete Document</h2>
      <div class="flex gap-2">
        <UInput v-model="deleteDocId" placeholder="Enter doc_id to delete" />
        <UButton :disabled="deleting || !deleteDocId" @click="deleteDocumentById">
          {{ deleting ? 'Deleting...' : 'Delete' }}
        </UButton>
      </div>
      <p v-if="deleteMsg" class="text-green-600 text-sm mt-2">{{ deleteMsg }}</p>
    </div>

    <!-- Results -->
    <ul v-if="results.length" class="mt-4 space-y-2">
      <li v-for="r in results" :key="r.id" class="border p-2 rounded">
        <div class="flex items-start justify-between gap-2">
          <div class="flex-1">
            <p class="text-xs text-gray-500">Score: {{ r.score.toFixed(3) }}</p>
            <p class="text-xs text-gray-500">
              Doc: <b>{{ r.metadata?.doc_id || '(unknown)' }}</b>
              <span v-if="r.metadata?.page_number !== undefined && r.metadata?.page_number !== null">
                &nbsp;• Page {{ r.metadata.page_number }}
              </span>
            </p>
            <p>{{ r.metadata?.text || '(no preview)' }}</p>
          </div>
          <UButton
            v-if="r.metadata?.doc_id"
            
            variant="soft"
            @click="deleteDocumentFromResult(r)"
            :disabled="deleting"
          >
            {{ deleting ? 'Deleting...' : 'Delete doc' }}
          </UButton>
        </div>
      </li>
    </ul>
  </div>
</template>
