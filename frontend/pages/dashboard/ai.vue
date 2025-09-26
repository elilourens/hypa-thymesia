<template>
  <BodyCard variant="subtle" class="p-6 space-y-6">
    <h2 class="text-xl font-semibold">AI Chat Test</h2>

    <!-- Large wide text input -->
    <UTextarea
      v-model="userInput"
      placeholder="Ask the AI something..."
      :rows="6"
      autoresize
      class="w-full min-h-[150px] text-base"
    />

    <!-- Action buttons -->
    <div class="flex gap-4">
      <UButton
        color="primary"
        size="lg"
        :loading="loading"
        :disabled="!userInput.trim()"
        @click="send"
      >
        {{ loading ? 'Thinking…' : 'Send' }}
      </UButton>

      <UButton
        v-if="loading"
        color="error"
        size="lg"
        @click="cancel"
      >
        Stop Generating
      </UButton>
    </div>

    <!-- AI Answer -->
    <div v-if="answer" class="mt-6">
      <h3 class="font-semibold mb-2">AI:</h3>
      <div class="whitespace-pre-line leading-relaxed">
        {{ answer }}
      </div>
    </div>
  </BodyCard>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useChat } from '~/composables/useChat'

const { authHeaders, API_BASE } = useChat()

const userInput = ref('')
const answer = ref('')
const loading = ref(false)
let controller: AbortController | null = null

async function send() {
  if (!userInput.value.trim()) return
  loading.value = true
  answer.value = ''
  controller = new AbortController()

  try {
    const headers = {
      'Content-Type': 'application/json',
      ...(await authHeaders()),
    }

    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers,
      signal: controller.signal,
      body: JSON.stringify({
        question: userInput.value, // ✅ matches backend
      }),
    })

    if (!res.ok) throw new Error(`Chat failed: ${res.status}`)
    const data = await res.json()
    answer.value = data.answer || 'No answer returned.'
  } catch (err: any) {
    if (err.name === 'AbortError') {
      answer.value += '\n\n[Generation stopped by user]'
    } else {
      answer.value = `Error: ${err.message || err}`
    }
  } finally {
    loading.value = false
    controller = null
  }
}

function cancel() {
  if (controller) controller.abort()
}
</script>

<style scoped>
/* Ensure the text area feels more spacious */
</style>
