<script setup lang="ts">
import { ref } from 'vue'
import { getTextFromMessage } from '@nuxt/ui/utils/ai'
import { useChat } from '~/composables/useChat'

const { sendChatMessage } = useChat()

// Message type
interface ChatMsg {
  id: string
  role: 'user' | 'assistant'
  parts: { type: 'text'; text: string }[]
  metadata?: any
}

// State
const input = ref('')
const messages = ref<ChatMsg[]>([])
const status = ref<'ready' | 'submitted' | 'error'>('ready')
const error = ref<Error | undefined>(undefined)

// Submit handler
async function handleSubmit(e: Event) {
  e.preventDefault?.()
  const text = input.value.trim()
  if (!text) return

  // Add user message
  messages.value.push({
    id: crypto.randomUUID(),
    role: 'user',
    parts: [{ type: 'text', text }]
  })

  input.value = ''
  status.value = 'submitted'
  error.value = undefined

  try {
    const reply = await sendChatMessage(text)
    messages.value.push(reply)
    status.value = 'ready'
  } catch (err) {
    console.error(err)
    error.value = err instanceof Error ? err : new Error(String(err))
    status.value = 'error'
  }
}

function reload() {
  handleSubmit({} as Event)
}
</script>

<template>
  <BodyCard>
    <p>Coming soon</p>
  </BodyCard>
</template>

