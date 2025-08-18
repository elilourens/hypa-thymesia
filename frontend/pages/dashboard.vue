<template>
  <div>
    <h1>Dashboard</h1>
    <p v-if="user">
      Current user is:
      <strong>{{ user.email }}</strong> their ID is:
      <strong>{{ user.id }}</strong>
    </p>
    <p v-else>No Logged in user</p>
  </div>

  <div>
    <UFileUpload
      v-model="files"
      multiple
      label="Drop your file here"
      layout="list"
      description="PDF, DOCX, TXT, PNG, JPG"
      class="w-96 min-h-48"
      accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
    />
    <UButton :disabled="files.length === 0" @click="onSubmit">Submit</UButton>
  </div>

  <div>
    <p>Query Files</p>
    <UInput placeholder="Search..." />
    <UButton>Query</UButton>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const supabase = useSupabaseClient()
const user = useSupabaseUser()
const { data } = await supabase.auth.getSession()
console.log("Session access token:", data.session?.access_token)

const files = ref<File[]>([])           // ✅ holds selected files

async function onSubmit() {
  const file = files.value[0]
  if (!file) return

  // ⬇️ Get a fresh session on the client right now
  const { data: ses } = await supabase.auth.getSession()
  const accessToken = ses.session?.access_token
  console.log('token prefix:', accessToken)
  if (!accessToken) {
    console.warn('No access token — user probably not logged in')
    return
  }

  const formData = new FormData()
  formData.append('file', file)
  if (user.value?.id) formData.append('user_id', user.value.id)

  const res = await fetch('http://127.0.0.1:8000/ingest/upload-text-and-images', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  })

  const text = await res.text()
  if (!res.ok) throw new Error(`Upload failed: ${res.status} ${res.statusText} — ${text}`)
  console.log('OK:', text)
}
</script>
