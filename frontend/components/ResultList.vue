<script setup lang="ts">
const props = defineProps<{ results: any[], deleting?: boolean }>()


// Helper to extract filename from storage_path
function getFileName(path?: string) {
  if (!path) return '(unknown file)'
  return path.split('_').pop() || path
}
</script>

<template>
  <div v-if="results?.length" 
       class=" grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4 gap-4">
    <UCard v-for="r in results" :key="r.id" class="flex flex-col justify-between">
      <div class="flex-1 space-y-1">
        <p class="text-xs text-gray-500">Score: {{ r.score?.toFixed?.(3) ?? r.score }}</p>
        <p class="text-xs text-gray-500">File: <strong>{{ getFileName(r.metadata?.storage_path) }}</strong><b></b></p>
        <USeparator orientation="horizontal" class="h-auto self-stretch" size="lg"/>

        <p v-if="(r.metadata?.modality||'').toLowerCase()==='text'">
          {{ r.metadata?.text || '(no preview)' }}
        </p>
        <p v-else>{{ r.metadata?.title || '(image)' }}</p>
      </div>

      
    </UCard>
  </div>
</template>
