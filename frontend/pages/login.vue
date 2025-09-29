<script setup lang="ts">
import * as z from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'

const client = useSupabaseClient()
const router = useRouter()

const loading = ref(false)
const error = ref('')
const message = ref('')
const mode = ref<'login' | 'signup'>('login')   // toggle between login/signup

const fields = [
  { name: 'email',    type: 'text'     as const, label: 'Email',    placeholder: 'Enter your email',    required: true },
  { name: 'password', type: 'password' as const, label: 'Password', placeholder: 'Enter your password', required: true }
]

const schema = z.object({
  email: z.string().email('Invalid email'),
  password: z.string().min(6, 'Password must be at least 6 characters')
})
type Schema = z.output<typeof schema>

async function onSubmit({ data }: FormSubmitEvent<Schema>) {
  error.value = ''
  message.value = ''
  loading.value = true

  if (mode.value === 'login') {
    const { error: err } = await client.auth.signInWithPassword({
      email: data.email,
      password: data.password
    })
    if (err) error.value = err.message
    else router.push('/dashboard')
  } else {
    const { error: err } = await client.auth.signUp({
      email: data.email,
      password: data.password
    })
    if (err) error.value = err.message
    else message.value = 'Check your inbox to confirm your email.'
  }

  loading.value = false
}
</script>

<template>
  <div class="flex items-center justify-center min-h-screen p-4">
    <UPageCard class="w-full max-w-sm">
      <UAuthForm
        :schema="schema"
        :fields="fields"
        :loading="loading"
        @submit="onSubmit"
        :submit="{ label: mode === 'login' ? 'Login' : 'Sign up', block: true }"
        title="Authentication"
        icon="i-lucide-lock"
      >
        <template #description>
          {{ mode === 'login' ? 'Log in to your account' : 'Create a new account' }}
        </template>

        <template #validation>
          <UAlert v-if="error" color="error" :title="error" />
          <UAlert v-if="message" color="success" :title="message" />
        </template>

        <template #footer>
          <p class="text-sm text-center text-muted">
            {{ mode === 'login' ? 'No account?' : 'Already have an account?' }}
            <ULink class="text-primary font-medium cursor-pointer"
                   @click="mode = mode === 'login' ? 'signup' : 'login'">
              {{ mode === 'login' ? 'Sign up here' : 'Log in here' }}
            </ULink>
          </p>
        </template>
      </UAuthForm>
    </UPageCard>
  </div>
</template>
