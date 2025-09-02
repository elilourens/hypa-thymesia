<script setup lang="ts">
const props = defineProps<{ results: any[], deleting?: boolean }>()
const emit = defineEmits<{ (e: 'delete', id: string): void }>()
</script>

<template>
  <ul v-if="results?.length" class="mt-4 space-y-2">
    <li v-for="r in results" :key="r.id" class="border p-2 rounded">
      <div class="flex items-start justify-between gap-2">
        <div class="flex-1">
          <p class="text-xs text-gray-500">Score: {{ r.score?.toFixed?.(3) ?? r.score }}</p>
          <p class="text-xs text-gray-500">Doc: <b>{{ r.metadata?.doc_id || '(unknown)' }}</b></p>
          <p v-if="(r.metadata?.modality||'').toLowerCase()==='text'">
            {{ r.metadata?.text || '(no preview)' }}
          </p>
          <p v-else>{{ r.metadata?.title || '(image)' }}</p>
        </div>
        <UButton
          v-if="r.metadata?.doc_id"
          variant="soft"
          :disabled="props.deleting"
          @click="emit('delete', r.metadata.doc_id)"
        >
          {{ props.deleting ? 'Deleting…' : 'Delete doc' }}
        </UButton>
      </div>
    </li>
  </ul>
</template>
