<script setup lang="ts">
const props = defineProps<{ results: any[], deleting?: boolean }>()

// Helper to extract filename from storage_path
function getFileName(path?: string) {
  if (!path) return '(unknown file)'
  return path.split('_').pop() || path
}

// Helper to render text with highlighted spans
function renderHighlightedText(
  text?: string,
  spans?: { start: number; end: number; term: string }[]
) {
  if (!text) return ''
  if (!spans?.length) return text

  let out = ''
  let last = 0
  for (const s of [...spans].sort((a, b) => a.start - b.start)) {
    out += text.slice(last, s.start)
    out += `<span class="bg-primary text-primary-foreground rounded px-0.5">${text.slice(
      s.start,
      s.end
    )}</span>`
    last = s.end
  }
  out += text.slice(last)
  return out
}
</script>

<template>
  <div
    v-if="results?.length"
    class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4 gap-4"
  >
    <UCard
      v-for="r in results"
      :key="r.id"
      class="flex flex-col justify-between"
    >
      <div class="flex-1 space-y-1">
        <!-- Score as percentage -->
        <p class="text-xs text-gray-500">
          Score: {{ (r.score * 100).toFixed(1) }}%
        </p>

        <!-- File with link to original -->
        <p class="text-xs text-gray-500">
          File: 
          <strong>{{ getFileName(r.metadata?.storage_path) }}</strong>
          <a
            v-if="r.metadata?.signed_url"
            :href="r.metadata.signed_url"
            target="_blank"
            rel="noopener noreferrer"
            class="text-primary underline ml-1"
          >
            (open)
          </a>
        </p>

        <USeparator
          orientation="horizontal"
          class="h-auto self-stretch"
          size="lg"
        />

        <!-- Render text hits -->
        <p v-if="(r.metadata?.modality || '').toLowerCase() === 'text'">
          <span
            v-html="renderHighlightedText(r.metadata?.text, r.metadata?.highlight_spans)"
          />
        </p>

        <!-- Render image hits -->
        <div
          v-else-if="(r.metadata?.modality || '').toLowerCase() === 'image'"
        >
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
