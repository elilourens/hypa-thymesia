<script setup lang="ts">
import { ref } from 'vue'

const supabase = useSupabaseClient()
const user = useSupabaseUser()
const API_BASE = useRuntimeConfig().public.apiBase ?? 'http://127.0.0.1:8000'

const files = ref<File[]>([])
const queryText = ref('')
const queryRoute = ref<'text'|'image'>('text')   // text->text (MiniLM) or text->image (CLIP)
const imageQueryFile = ref<File|null>(null)

const results = ref<any[]>([])
const loading = ref(false)
const error = ref<string|null>(null)

const deleteDocId = ref('')
const deleting = ref(false)
const deleteMsg = ref<string|null>(null)

async function token() {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token
}

async function uploadFile() {
  const f = files.value[0]; if (!f) return
  const t = await token(); if (!t) { error.value = 'Not logged in'; return }
  const fd = new FormData(); fd.append('file', f)
  const r = await fetch(`${API_BASE}/ingest/upload-text-and-images`, { method:'POST', headers:{ Authorization:`Bearer ${t}` }, body:fd })
  if (!r.ok) error.value = await r.text()
}

async function runQuery() {
  if (!queryText.value.trim()) { error.value = 'Enter a query'; return }
  const t = await token(); if (!t) { error.value = 'Not logged in'; return }
  loading.value = true; error.value = null; results.value = []
  const r = await fetch(`${API_BASE}/ingest/query`, {
    method:'POST',
    headers:{ 'Content-Type':'application/json', Authorization:`Bearer ${t}` },
    body: JSON.stringify({ query_text: queryText.value, route: queryRoute.value, top_k: 10 })
  })
  loading.value = false
  if (!r.ok) { error.value = await r.text(); return }
  results.value = (await r.json()).matches || []
}

async function runImageQuery() {
  const f = imageQueryFile.value; if (!f) { error.value = 'Pick an image'; return }
  const t = await token(); if (!t) { error.value = 'Not logged in'; return }
  const buf = await f.arrayBuffer()
  const b64 = btoa(String.fromCharCode(...new Uint8Array(buf))) // raw base64
  loading.value = true; error.value = null; results.value = []
  const r = await fetch(`${API_BASE}/ingest/query`, {
    method:'POST',
    headers:{ 'Content-Type':'application/json', Authorization:`Bearer ${t}` },
    body: JSON.stringify({ image_b64: b64, top_k: 10 })
  })
  loading.value = false
  if (!r.ok) { error.value = await r.text(); return }
  results.value = (await r.json()).matches || []
}

async function deleteDocumentById() {
  const id = deleteDocId.value.trim(); if (!id) return
  const t = await token(); if (!t) { error.value = 'Not logged in'; return }
  deleting.value = true; deleteMsg.value = null; error.value = null
  const u = new URL(`${API_BASE}/ingest/delete-document`); u.searchParams.set('doc_id', id)
  const r = await fetch(u.toString(), { method:'DELETE', headers:{ Authorization:`Bearer ${t}` } })
  deleting.value = false
  const txt = await r.text()
  if (!r.ok) { error.value = txt; return }
  deleteMsg.value = `Deleted ${id}`
  results.value = results.value.filter(m => m?.metadata?.doc_id !== id)
}

async function deleteFromResult(r:any) { deleteDocId.value = r?.metadata?.doc_id || ''; if (deleteDocId.value) await deleteDocumentById() }
</script>

<template>
  <div class="space-y-6 max-w-xl">
    <p v-if="user">User: <b>{{ user.email }}</b></p>

    <!-- Upload --> 
     <div> 
      <h2 class="font-semibold">Upload Files</h2> 
      <UFileUpload v-model="files" multiple label="Drop your file here" layout="list" description="PDF, DOCX, TXT, PNG, JPG" class="w-96 min-h-48" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" /> 
      <UButton class="mt-2" :disabled="!files.length" @click="uploadFile">Upload</UButton> 
    </div>

    <!-- Text query -->
    <div>
      <h2 class="font-semibold">Search (Text)</h2>
      <UInput v-model="queryText" placeholder="Enter text query..." class="mb-2"/>
      <div class="flex gap-4 text-sm">
        <label><input type="radio" value="text" v-model="queryRoute"> text→text</label>
        <label><input type="radio" value="image" v-model="queryRoute"> text→image</label>
      </div>
      <UButton class="mt-2" :disabled="loading || !queryText" @click="runQuery">
        {{ loading ? 'Searching...' : 'Search' }}
      </UButton>
      <p v-if="error" class="text-red-500 text-sm mt-2">{{ error }}</p>
    </div>

    <!-- Image query -->
    <div>
      <h2 class="font-semibold">Search (Image)</h2>
      <UFileUpload v-model="imageQueryFile" :multiple="false" accept=".png,.jpg,.jpeg,.webp" class="w-96"/>
      <UButton class="mt-2" :disabled="loading || !imageQueryFile" @click="runImageQuery">
        {{ loading ? 'Searching...' : 'Search with image' }}
      </UButton>
    </div>

    <!-- Delete -->
    <div>
      <h2 class="font-semibold">Delete</h2>
      <div class="flex gap-2">
        <UInput v-model="deleteDocId" placeholder="doc_id"/>
        <UButton :disabled="deleting || !deleteDocId" @click="deleteDocumentById">
          {{ deleting ? 'Deleting…' : 'Delete' }}
        </UButton>
      </div>
      <p v-if="deleteMsg" class="text-green-600 text-sm mt-2">{{ deleteMsg }}</p>
    </div>

    <!-- Results -->
    <ul v-if="results.length" class="mt-4 space-y-2">
      <li v-for="r in results" :key="r.id" class="border p-2 rounded">
        <div class="flex items-start justify-between gap-2">
          <div class="flex-1">
            <p class="text-xs text-gray-500">Score: {{ r.score?.toFixed?.(3) ?? r.score }}</p>
            <p class="text-xs text-gray-500">Doc: <b>{{ r.metadata?.doc_id || '(unknown)' }}</b></p>
            <p v-if="(r.metadata?.modality||'').toLowerCase()==='text'">{{  r.metadata?.text || '(no preview)' }}</p>
            <p v-else>{{ r.metadata?.title || '(image)' }}</p>
          </div>
          <UButton v-if="r.metadata?.doc_id" variant="soft" :disabled="deleting" @click="deleteFromResult(r)">
            {{ deleting ? 'Deleting…' : 'Delete doc' }}
          </UButton>
        </div>
      </li>
    </ul>
  </div>
</template>
