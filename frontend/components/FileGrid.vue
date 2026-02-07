<script setup lang="ts">
import type { DocumentItem } from '@/composables/useDocuments'

export interface ContextMenuItem {
  label: string
  icon?: string
  action: (file: DocumentItem) => void
  separator?: boolean
}

interface Props {
  files: DocumentItem[]
  loading?: boolean
  enableHoverPreview?: boolean
  chunkMap?: Map<string, any>
  contextMenuItems?: ContextMenuItem[]
}

const props = defineProps<Props>()

// Thumbnail URL state
const thumbnailUrls = ref<Record<string, string>>({})
const { getThumbnailUrl } = useDocuments()

// Watch for files changes and fetch thumbnails
watch(() => props.files, async (newFiles) => {
  if (!newFiles) return

  // Fetch thumbnails for image and video files
  for (const file of newFiles) {
    if ((file.mime_type?.startsWith('image/') || file.mime_type?.startsWith('video/')) && !thumbnailUrls.value[file.id]) {
      const url = await getThumbnailUrl(file.id)
      if (url) {
        thumbnailUrls.value[file.id] = url
      }
    }
  }
}, { immediate: true })

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

// Context menu state
const contextMenu = ref<{ x: number; y: number; file: DocumentItem } | null>(null)
const contextMenuRef = ref<HTMLElement | null>(null)

function onContextMenu(e: MouseEvent, file: DocumentItem) {
  if (!props.contextMenuItems?.length) return
  e.preventDefault()

  // Position menu, clamping to viewport edges
  const menuWidth = 200
  const menuHeight = props.contextMenuItems.length * 36 + 16
  const x = Math.min(e.clientX, window.innerWidth - menuWidth - 8)
  const y = Math.min(e.clientY, window.innerHeight - menuHeight - 8)

  contextMenu.value = { x, y, file }
}

function closeContextMenu() {
  contextMenu.value = null
}

function onMenuItemClick(item: ContextMenuItem) {
  if (contextMenu.value) {
    item.action(contextMenu.value.file)
  }
  closeContextMenu()
}

// Close on click outside or Escape
function onClickOutside(e: MouseEvent) {
  if (contextMenuRef.value && !contextMenuRef.value.contains(e.target as Node)) {
    closeContextMenu()
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') closeContextMenu()
}

onMounted(() => {
  document.addEventListener('click', onClickOutside)
  document.addEventListener('keydown', onKeydown)
  window.addEventListener('scroll', closeContextMenu, true)
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('scroll', closeContextMenu, true)
})
</script>

<template>
  <div>
    <!-- File Grid -->
    <div
      v-if="!loading && files.length > 0"
      class="grid gap-1"
      style="grid-template-columns: repeat(auto-fill, minmax(210px, 1fr))"
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
          class="flex flex-col cursor-pointer border border-transparent hover:border-primary-500 hover:shadow-md transition-all text-left w-full gap-0 bg-transparent"
          :ui="{ body: 'p-0' }"
          @click="emit('open-file', file)"
          @contextmenu="onContextMenu($event, file)"
        >
          <!-- File Thumbnail or Icon -->
          <div class="flex justify-center items-center" style="height: 120px">
            <!-- Show thumbnail for images and videos if available -->
            <img
              v-if="(file.mime_type?.startsWith('image/') || file.mime_type?.startsWith('video/')) && thumbnailUrls[file.id]"
              :src="thumbnailUrls[file.id]"
              :alt="file.filename"
              class="w-full h-full object-cover rounded"
              @error="() => delete thumbnailUrls[file.id]"
            />
            <!-- Fallback to icon -->
            <UIcon
              v-else
              :name="getFileIcon(file.mime_type)"
              class="w-12 h-12 text-primary-500"
            />
          </div>

          <!-- Filename -->
          <h3
            class="font-medium text-[11px] text-foreground leading-tight whitespace-normal mt-1"
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
    <div v-if="loading" class="grid gap-1" style="grid-template-columns: repeat(auto-fill, minmax(210px, 1fr))">
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

    <!-- Custom Context Menu -->
    <Teleport to="body">
      <div
        v-if="contextMenu && contextMenuItems?.length"
        ref="contextMenuRef"
        class="fixed z-[100] min-w-[180px] rounded-md border border-foreground/10 bg-neutral-900 shadow-xl py-1 select-none overflow-hidden"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      >
        <template v-for="(item, i) in contextMenuItems" :key="i">
          <div v-if="item.separator" class="my-1 border-t border-foreground/10" />
          <button
            class="flex items-center gap-2 w-full px-3 py-2 text-sm text-foreground/80 hover:text-foreground hover:bg-white/10 transition-all duration-150 text-left group"
            @click="onMenuItemClick(item)"
          >
            <UIcon v-if="item.icon" :name="item.icon" class="w-4 h-4 text-foreground/50 group-hover:text-foreground transition-colors duration-150" />
            <span>{{ item.label }}</span>
          </button>
        </template>
      </div>
    </Teleport>
  </div>
</template>
