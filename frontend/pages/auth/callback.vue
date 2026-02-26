<script setup lang="ts">
const router = useRouter()
const user = useSupabaseUser()

onMounted(async () => {
  // The Nuxt Supabase module automatically handles the code exchange
  // when this page loads. Just wait a moment and check if user is authenticated

  await new Promise(resolve => setTimeout(resolve, 500))

  // If user is authenticated, redirect to dashboard
  if (user.value) {
    await router.push('/dashboard/query')
  } else {
    // If still not authenticated, redirect back to login with error
    await router.push('/login?error=Authentication failed')
  }
})
</script>

<template>
  <div class="flex items-center justify-center min-h-screen">
    <div class="text-center">
      <div class="mb-4">
        <div class="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary border-r-transparent"></div>
      </div>
      <p class="text-gray-600">Signing you in...</p>
    </div>
  </div>
</template>
