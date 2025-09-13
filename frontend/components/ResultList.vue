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
       class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4 gap-4">
    <UCard v-for="r in results" :key="r.id" class="flex flex-col justify-between">
      <div class="flex-1 space-y-1">
        <!-- Score as percentage -->
        <p class="text-xs text-gray-500">
          Score: {{ (r.score * 100).toFixed(1) }}%
        </p>

        <p class="text-xs text-gray-500">
          File: <strong>{{ getFileName(r.metadata?.storage_path) }}</strong>
        </p>
        <USeparator orientation="horizontal" class="h-auto self-stretch" size="lg"/>

        <!-- Render text hits -->
        <p v-if="(r.metadata?.modality||'').toLowerCase()==='text'">
          {{ r.metadata?.text || '(no preview)' }}
        </p>

        <!-- Render image hits -->
        <div v-else-if="(r.metadata?.modality||'').toLowerCase()==='image'">
          <img 
            v-if="r.metadata?.signed_url"
            :src="r.metadata.signed_url" 
            :alt="r.metadata?.title || 'image result'" 
            class="object-contain mx-auto p-2"
          />
          <p v-else>{{ r.metadata?.title || '(image)' }}</p>
        </div>

        <!-- Fallback -->
        <p v-else>{{ r.metadata?.title || '(unknown modality)' }}</p>
      </div>
    </UCard>
  </div>
</template>

