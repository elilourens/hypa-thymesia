<script setup lang="ts">
import * as z from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'

const client = useSupabaseClient()
const router = useRouter()

const loading = ref(false)
const error = ref('')
const message = ref('')
const isValidSession = ref(false)

const schema = z.object({
  password: z.string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
    .regex(/[0-9]/, 'Password must contain at least one number'),
  confirmPassword: z.string()
}).refine(data => data.password === data.confirmPassword, {
  message: "Passwords don't match",
  path: ["confirmPassword"],
})

type Schema = z.output<typeof schema>

const state = reactive<Partial<Schema>>({
  password: '',
  confirmPassword: ''
})

onMounted(async () => {
  const route = useRoute()

  // Supabase sends recovery code in URL query parameter
  const code = route.query.code as string

  if (code) {
    // Verify the recovery code to create a session
    const { error: err } = await client.auth.verifyOtp({
      email: '',
      token: code,
      type: 'recovery'
    })

    if (err) {
      error.value = 'Invalid or expired recovery link. Please request a new password reset.'
      isValidSession.value = false
    } else {
      isValidSession.value = true
    }
  } else {
    // No code in URL, check if there's an existing session
    const { data: { session } } = await client.auth.getSession()

    if (session) {
      isValidSession.value = true
    } else {
      error.value = 'Invalid or expired recovery link. Please request a new password reset.'
      isValidSession.value = false
    }
  }
})

async function onSubmit({ data }: FormSubmitEvent<Schema>) {
  error.value = ''
  message.value = ''
  loading.value = true

  const { error: err } = await client.auth.updateUser({
    password: data.password
  })

  if (err) {
    error.value = err.message
  } else {
    message.value = 'Password updated successfully! Redirecting to login...'
    setTimeout(() => {
      router.push('/login')
    }, 2000)
  }

  loading.value = false
}
</script>

<template>
  <div class="flex items-center justify-center min-h-screen p-4">
    <UPageCard class="w-full max-w-sm">
      <div class="text-center mb-6">
        <h2 class="text-2xl font-bold">Reset Your Password</h2>
        <p class="text-sm text-muted mt-2">Create a new password for your account</p>
      </div>

      <UAlert v-if="error" color="error" :title="error" class="mb-4" />
      <UAlert v-if="message" color="success" :title="message" class="mb-4" />

      <div v-if="isValidSession">
        <UForm :schema="schema" :state="state" @submit="onSubmit" class="space-y-4">
          <UFormField label="New Password" name="password">
            <UInput v-model="state.password" type="password" placeholder="Enter new password" />
          </UFormField>

          <UFormField label="Confirm Password" name="confirmPassword">
            <UInput v-model="state.confirmPassword" type="password" placeholder="Confirm your password" />
          </UFormField>

          <UButton type="submit" :loading="loading" block>
            Update Password
          </UButton>

          <UButton to="/login" variant="ghost" block>
            Back to Login
          </UButton>
        </UForm>
      </div>

      <div v-else>
        <UButton to="/login" block>
          Return to Login
        </UButton>
      </div>
    </UPageCard>
  </div>
</template>
