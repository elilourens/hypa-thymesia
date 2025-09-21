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
      <div class="flex-1 space-y-2">
        <!-- Score as percentage -->
        <p class="text-xs text-gray-500">
          Score: {{ (r.score * 100).toFixed(1) }}%
        </p>

        <!-- File info row -->
        <div class="flex items-center justify-between text-xs text-gray-500">
          <span>
            File: <strong>{{ getFileName(r.metadata?.storage_path) }}</strong>
          </span>

          <div class="flex items-center gap-2">
            <!-- Open button (all files) -->
            <UButton
              v-if="r.metadata?.signed_url"
              :to="(r.metadata?.mime_type || '').includes('officedocument.wordprocessingml.document')
                ? `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(r.metadata.signed_url)}`
                : r.metadata.signed_url"
              target="_blank"
              rel="noopener noreferrer"
              size="xs"
              color="primary"
              variant="soft"
              icon="i-heroicons-eye"
            >
              Open
            </UButton>

            <!-- Download button (DOCX only) -->
            <UButton
              v-if="r.metadata?.signed_url && (r.metadata?.mime_type || '').includes('officedocument.wordprocessingml.document')"
              :to="r.metadata.signed_url"
              target="_blank"
              rel="noopener noreferrer"
              size="xs"
              color="primary"
              variant="soft"
              icon="i-heroicons-arrow-down-tray"
            >
              Download
            </UButton>
          </div>
        </div>

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
        <div v-else-if="(r.metadata?.modality || '').toLowerCase() === 'image'">
          <img
            v-if="r.metadata?.signed_url"
            :src="r.metadata.signed_url"
            :alt="r.metadata?.title || 'image result'"
            class="object-contain mx-auto p-2"
          />
          <p v-else>{{ r.metadata?.title || '(image)' }}</p>
        </div>

        <!-- Render PDF inline -->
        <div v-else-if="(r.metadata?.mime_type || '').includes('application/pdf')">
          <iframe
            v-if="r.metadata?.signed_url"
            :src="r.metadata.signed_url"
            width="100%"
            height="400"
            style="border: none;"
          ></iframe>
        </div>

        <!-- Render DOCX inline via Office viewer -->
        <div v-else-if="(r.metadata?.mime_type || '').includes('officedocument.wordprocessingml.document')">
          <iframe
            v-if="r.metadata?.signed_url"
            :src="`https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(r.metadata.signed_url)}`"
            width="100%"
            height="400"
            frameborder="0"
          ></iframe>
        </div>

        <!-- Fallback -->
        <p v-else>{{ r.metadata?.title || '(unknown modality)' }}</p>
      </div>
    </UCard>
  </div>
</template>
