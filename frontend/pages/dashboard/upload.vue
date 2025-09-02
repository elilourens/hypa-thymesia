<script setup lang="ts">
import { ref } from 'vue'
const { uploadFile } = useIngest()

const files = ref<File[]>([])
const error = ref<string|null>(null)
const success = ref<string|null>(null)
const uploading = ref(false)

async function doUpload() {
  error.value = null; success.value = null
  const f = files.value[0]
  if (!f) { error.value = 'Pick a file'; return }
  try {
    uploading.value = true
    await uploadFile(f)
    success.value = `Uploaded ${f.name}`
    files.value = []
  } catch (e:any) {
    error.value = e?.message ?? 'Upload failed'
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="space-y-4 max-w-xl">
    <h1 class="font-semibold text-lg">Upload Files</h1>
    <UFileUpload v-model="files" multiple label="Drop your file here" layout="list"
      description="PDF, DOCX, TXT, PNG, JPG" class="w-96 min-h-48"
      accept=".pdf,.docx,.txt,.png,.jpg,.jpeg" />
    <UButton :disabled="!files.length || uploading" @click="doUpload">
      {{ uploading ? 'Uploading…' : 'Upload' }}
    </UButton>
    <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>
    <p v-if="success" class="text-green-600 text-sm">{{ success }}</p>
  </div>
</template>
