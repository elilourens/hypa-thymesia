<script setup lang="ts">
import * as z from 'zod'
import type { FormSubmitEvent } from '@nuxt/ui'

const client = useSupabaseClient()
const router = useRouter()

const loading = ref(false)
const oauthLoading = ref(false)
const error = ref('')
const message = ref('')
const mode = ref<'login' | 'signup' | 'forgot'>('login')

const fields = [
  { name: 'email',    type: 'text'     as const, label: 'Email',    placeholder: 'Enter your email',    required: true },
  { name: 'password', type: 'password' as const, label: 'Password', placeholder: 'Enter your password', required: true }
]

const schema = z.object({
  email: z.string().email('Invalid email'),
  password: z.string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
    .regex(/[0-9]/, 'Password must contain at least one number')
})
type Schema = z.output<typeof schema>

const forgotSchema = z.object({
  email: z.string().email('Invalid email')
})
type ForgotSchema = z.output<typeof forgotSchema>

const forgotState = reactive<Partial<ForgotSchema>>({
  email: ''
})

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
    else router.push('/dashboard/query')
  } else {
    const { error: err } = await client.auth.signUp({
      email: data.email,
      password: data.password,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`
      }
    })
    if (err) error.value = err.message
    else message.value = 'Check your inbox to confirm your email.'
  }

  loading.value = false
}

async function signInWithGoogle() {
  error.value = ''
  oauthLoading.value = true

  try {
    const { data, error: err } = await client.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`
      }
    })
    if (err) {
      error.value = err.message
      oauthLoading.value = false
    } else if (data?.url) {
      // Navigate to the OAuth URL
      window.location.href = data.url
    }
  } catch (e: any) {
    error.value = e.message || 'An error occurred during sign in'
    oauthLoading.value = false
  }
}

async function onForgotSubmit({ data }: FormSubmitEvent<ForgotSchema>) {
  error.value = ''
  message.value = ''
  loading.value = true

  const { error: err } = await client.auth.resetPasswordForEmail(data.email, {
    redirectTo: `${window.location.origin}/reset-password/`
  })

  if (err) {
    error.value = err.message
  } else {
    message.value = 'Check your email for password reset instructions'
    setTimeout(() => {
      mode.value = 'login'
      message.value = ''
      error.value = ''
    }, 3000)
  }

  loading.value = false
}
</script>

<template>
  <div class="flex items-center justify-center min-h-screen p-4">
    <UPageCard class="w-full max-w-sm">
      <!-- Login/Signup Form -->
      <div v-if="mode !== 'forgot'">
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
            <div class="space-y-3">
              <p class="text-sm text-center text-muted">
                {{ mode === 'login' ? 'No account?' : 'Already have an account?' }}
                <ULink class="text-primary font-medium cursor-pointer"
                       @click="mode = mode === 'login' ? 'signup' : 'login'">
                  {{ mode === 'login' ? 'Sign up here' : 'Log in here' }}
                </ULink>
              </p>
              <p v-if="mode === 'login'" class="text-xs text-center text-muted">
                <ULink class="text-primary font-medium cursor-pointer"
                       @click="mode = 'forgot'">
                  Forgot your password?
                </ULink>
              </p>
            </div>
          </template>
        </UAuthForm>

        <!-- Google Sign-In Button -->
        <div class="mt-4">
          <UButton
            @click="signInWithGoogle"
            :loading="oauthLoading"
            variant="subtle"
            block
            class="flex items-center justify-center gap-2"
          >
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Sign in with Google
          </UButton>
        </div>
      </div>

      <!-- Forgot Password Form -->
      <div v-else>
        <div class="mb-6">
          <h2 class="text-2xl font-bold">Reset Password</h2>
          <p class="text-sm text-muted mt-2">Enter your email and we'll send you a password reset link</p>
        </div>

        <UAlert v-if="error" color="error" :title="error" class="mb-4" />
        <UAlert v-if="message" color="success" :title="message" class="mb-4" />

        <UForm :schema="forgotSchema" :state="forgotState" @submit="onForgotSubmit" class="space-y-4">
          <UFormField label="Email" name="email">
            <UInput v-model="forgotState.email" type="email" placeholder="Enter your email" />
          </UFormField>
          <UButton type="submit" :loading="loading" block>
            Send Reset Link
          </UButton>
          <UButton @click="mode = 'login'" variant="ghost" block>
            Back to Login
          </UButton>
        </UForm>
      </div>
    </UPageCard>
  </div>
</template>
