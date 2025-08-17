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
      label="Drop your file here"
      description="PDF, DOCX, TXT, PNG, JPG"
      class="w-96 min-h-48"
      @change="onFileChange"
      accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
    />
  </div>

  <div>
    <p>Query Files</p>
    <UInput placeholder="Search..." />
    <UButton>Query</UButton>
  </div>
</template>

<script setup lang="ts">
const supabase = useSupabaseClient()
const user = useSupabaseUser()
const { data } = await supabase.auth.getSession()
console.log("Session access token:", data.session?.access_token)

async function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const files = target.files
  if (!files || files.length === 0) {
    console.warn("No file selected")
    return
  }

  const file = files[0]!
  console.log("Uploading file:", file.name)

  const formData = new FormData()
  formData.append("file", file)
  if (user.value?.id) {
    formData.append("user_id", user.value.id) // required by backend
  }

  try {
    const res = await fetch("http://127.0.0.1:3000/ingest/upload-text-and-images", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${data.session?.access_token ?? ""}`,
      },
      body: formData,
    })

    if (!res.ok) {
      throw new Error(`Upload failed: ${res.status} ${res.statusText}`)
    }

    const result = await res.json()
    console.log("Upload success:", result)
  } catch (err) {
    console.error("Upload error:", err)
  }
}
</script>
