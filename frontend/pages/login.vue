<template>
  <div class="min-h-screen flex items-center justify-center">
    <div class="w-full max-w-sm space-y-4">
      <h1 class="text-xl font-bold text-center">Auth</h1>

      <UInput v-model="email" type="email" placeholder="Email" />
      <UInput v-model="password" type="password" placeholder="Password" />

      <UButton block :loading="loading" @click="login">Login</UButton>
      <UButton block :loading="loading" @click="signup" variant="outline">Sign up</UButton>

      <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>
      <p v-if="message" class="text-green-600 text-sm">{{ message }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
const client = useSupabaseClient()
const router = useRouter()

const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const message = ref('')

async function login() {
  reset()
  loading.value = true
  const { error: err } = await client.auth.signInWithPassword({
    email: email.value,
    password: password.value
  })
  if (err) error.value = err.message
  else router.push('/')
  loading.value = false
}

async function signup() {
  reset()
  loading.value = true
  const { error: err } = await client.auth.signUp({
    email: email.value,
    password: password.value
  })
  if (err) error.value = err.message
  else message.value = 'Check your inbox to confirm your email.'
  loading.value = false
}

function reset() {
  error.value = ''
  message.value = ''
}
</script>
