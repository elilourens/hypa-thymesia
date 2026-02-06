<script setup lang="ts">
import type { DocumentItem } from '@/composables/useDocuments'

interface Props {
  files: DocumentItem[]
  loading?: boolean
  enableHoverPreview?: boolean
  chunkMap?: Map<string, any>
}

defineProps<Props>()

// Helper function to get appropriate icon based on mime type
function getFileIcon(mimeType?: string): string {
  if (!mimeType) return 'i-lucide-file'

  if (mimeType.includes('pdf')) return 'i-lucide-file-text'
  if (mimeType.startsWith('image/')) return 'i-lucide-file-image'
  if (mimeType.startsWith('video/')) return 'i-lucide-file-video'
  if (mimeType.includes('wordprocessingml')) return 'i-lucide-file-text'
  if (mimeType.includes('spreadsheetml')) return 'i-lucide-file-spreadsheet'
  if (mimeType.includes('presentationml')) return 'i-lucide-presentation'
  if (mimeType.startsWith('audio/')) return 'i-lucide-file-audio'

  return 'i-lucide-file'
}



const emit = defineEmits<{
  'open-file': [file: DocumentItem]
}>()
</script>

<template>
  <div>
    <!-- File Grid -->
    <div
      v-if="!loading && files.length > 0"
      class="grid gap-1"
      style="grid-template-columns: repeat(auto-fill, minmax(130px, 1fr))"
    >
      <UPopover
        v-for="file in files"
        :key="file.id"
        :disabled="!enableHoverPreview || !chunkMap?.has(file.id)"
        mode="hover"
        :open-delay="500"
        :close-delay="200"
        arrow
      >
        <UCard
          as="button"
          class="flex flex-col cursor-pointer border border-transparent hover:border-primary-500 hover:shadow-md transition-all text-left w-full gap-0"
          :ui="{ body: 'p-0' }"
          @click="emit('open-file', file)"
        >
          <!-- File Icon -->
          <div class="flex justify-center py-2">
            <UIcon
              :name="getFileIcon(file.mime_type)"
              class="w-18 h-18 text-primary-500"
            />
          </div>

          <!-- Filename -->
          <h3
            class="font-medium text-[10px] text-foreground leading-tight whitespace-normal"
            :title="file.filename"
          >
            {{ file.filename }}
          </h3>
        </UCard>

        <!-- Hover Preview Content -->
        <template v-if="enableHoverPreview && chunkMap?.has(file.id)" #content>
          <Teleport to="body">
            <div class="fixed inset-0 bg-black/50 z-40" />
            <div class="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] max-w-[90vw] max-h-[70vh] overflow-y-auto p-6 rounded-lg shadow-2xl border border-foreground/10 z-50 backdrop-blur-md bg-black/20" style="background: rgba(0, 0, 0, 0.1); backdrop-filter: blur(10px);">
              <p class="text-sm text-foreground/70 font-semibold mb-4 sticky top-0">Most relevant content:</p>
              <p class="text-lg text-foreground whitespace-pre-wrap break-words">
                {{ chunkMap.get(file.id)?.text || '(No preview available)' }}
              </p>
            </div>
          </Teleport>
        </template>
      </UPopover>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="grid gap-1" style="grid-template-columns: repeat(auto-fill, minmax(130px, 1fr))">
      <div v-for="i in 6" :key="i" class="h-24 bg-gray-200 dark:bg-gray-800 rounded-lg animate-pulse" />
    </div>

    <!-- Empty State -->
    <div
      v-if="!loading && files.length === 0"
      class="text-center py-12 px-4"
    >
      <UIcon name="i-lucide-folder-open" class="w-12 h-12 mx-auto mb-4 text-foreground/40" />
      <p class="text-foreground/60">No files found</p>
    </div>
  </div>
</template>
