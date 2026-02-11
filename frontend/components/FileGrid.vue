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
  enableSelection?: boolean
  selectedIds?: string[]
  groupColors?: Record<string, string>
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

// Selection state
const localSelectedIds = ref<Set<string>>(new Set())

// Sync with prop (v-model support)
watch(() => props.selectedIds, (newIds) => {
  if (newIds) {
    localSelectedIds.value = new Set(newIds)
  }
}, { immediate: true })

// Computed helpers
const allSelected = computed(() => {
  if (props.files.length === 0) return false
  return props.files.every(f => localSelectedIds.value.has(f.id))
})

const someSelected = computed(() => {
  return localSelectedIds.value.size > 0 && !allSelected.value
})

// Selection handlers
function toggleSelection(fileId: string, event: Event) {
  event.stopPropagation() // Prevent opening file

  if (localSelectedIds.value.has(fileId)) {
    localSelectedIds.value.delete(fileId)
  } else {
    localSelectedIds.value.add(fileId)
  }

  emit('update:selectedIds', Array.from(localSelectedIds.value))
}

function toggleSelectAll() {
  if (allSelected.value) {
    localSelectedIds.value.clear()
  } else {
    localSelectedIds.value = new Set(props.files.map(f => f.id))
  }

  emit('update:selectedIds', Array.from(localSelectedIds.value))
}

function isSelected(fileId: string): boolean {
  return localSelectedIds.value.has(fileId)
}

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

// Format date to localized readable format
function formatDate(iso: string): string {
  const d = new Date(iso)
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(d)
}

// Format file size to human-readable format
function formatSize(bytes?: number | null): string {
  if (!bytes) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = bytes
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`
}

// Format chunks and pages info
function formatChunksPages(file: DocumentItem): string | null {
  const parts: string[] = []
  if (file.chunk_count) parts.push(`${file.chunk_count} chunks`)
  if (file.page_count) parts.push(`${file.page_count} pages`)
  return parts.length > 0 ? parts.join(' • ') : null
}

const emit = defineEmits<{
  'open-file': [file: DocumentItem]
  'update:selectedIds': [ids: string[]]
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
    <!-- Select All Header (only shown when enableSelection is true) -->
    <div v-if="enableSelection && files.length > 0" class="flex items-center gap-2 mb-3 px-2">
      <UCheckbox
        :model-value="someSelected ? 'indeterminate' : allSelected"
        @update:model-value="toggleSelectAll"
        aria-label="Select all files"
      />
      <span class="text-sm text-foreground/60">
        {{ localSelectedIds.size > 0 ? `${localSelectedIds.size} selected` : 'Select all' }}
      </span>
    </div>

    <!-- File Grid -->
    <div
      v-if="!loading && files.length > 0"
      class="grid gap-3"
      style="grid-template-columns: repeat(auto-fill, minmax(150px, 1fr))"
    >
      <UPopover
        v-for="file in files"
        :key="file.id"
        :disabled="!enableHoverPreview && !file.filename"
        mode="hover"
        :open-delay="300"
        :close-delay="150"
        arrow
      >
        <button
          class="glass-card group flex flex-col cursor-pointer text-left w-full gap-0 rounded-xl p-3 transition-all duration-300 relative"
          :class="{ 'ring-2 ring-purple-500': enableSelection && isSelected(file.id) }"
          @click="emit('open-file', file)"
          @contextmenu="onContextMenu($event, file)"
        >
          <!-- Checkbox overlay (top-left corner) -->
          <div
            v-if="enableSelection"
            class="absolute top-2 left-2 z-10"
            @click.stop="toggleSelection(file.id, $event)"
          >
            <UCheckbox
              :model-value="isSelected(file.id)"
              aria-label="Select file"
              class="pointer-events-auto"
            />
          </div>

          <!-- Group Color Dot (top-right corner) -->
          <div
            v-if="file.group_id && groupColors?.[file.group_id]"
            class="absolute top-2 right-2 z-10 w-3 h-3 rounded-full shadow-md"
            :style="{ backgroundColor: groupColors[file.group_id] }"
            :title="file.group_name || 'Unnamed group'"
          />

          <!-- File Thumbnail or Icon -->
          <div class="flex justify-center items-center rounded-lg overflow-hidden" style="height: 84px">
            <!-- Show thumbnail for images and videos if available -->
            <div
              v-if="(file.mime_type?.startsWith('image/') || file.mime_type?.startsWith('video/')) && thumbnailUrls[file.id]"
              class="relative w-full h-full"
            >
              <img
                :src="thumbnailUrls[file.id]"
                :alt="file.filename"
                class="w-full h-full object-cover"
                @error="() => delete thumbnailUrls[file.id]"
              />
              <!-- Play Button Overlay for videos -->
              <div
                v-if="file.mime_type?.startsWith('video/')"
                class="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/30 transition-all rounded-lg"
              >
                <UIcon name="i-heroicons-play-solid" class="w-10 h-10 text-white/80 drop-shadow-lg" />
              </div>
            </div>
            <!-- Fallback to icon -->
            <UIcon
              v-else
              :name="getFileIcon(file.mime_type)"
              class="w-12 h-12 text-white/60 group-hover:text-white/80 transition-colors duration-300"
            />
          </div>

          <!-- Filename -->
          <h3
            class="font-medium text-[11px] text-white/80 group-hover:text-white leading-tight whitespace-normal mt-2 transition-colors duration-300"
            :title="file.filename"
          >
            {{ file.filename }}
          </h3>
        </button>

        <!-- Hover Preview Content -->
        <template #content>
          <!-- Chunk Preview (if available) -->
          <Teleport v-if="enableHoverPreview && chunkMap?.has(file.id)" to="body">
            <div class="fixed inset-0 bg-black/50 z-40" />
            <div class="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] max-w-[90vw] max-h-[70vh] overflow-y-auto p-6 rounded-lg shadow-2xl border border-foreground/10 z-50 backdrop-blur-md bg-black/20" style="background: rgba(0, 0, 0, 0.1); backdrop-filter: blur(10px);">
              <p class="text-sm text-foreground/70 font-semibold mb-4 sticky top-0">Most relevant content:</p>
              <p class="text-lg text-foreground whitespace-pre-wrap break-words">
                {{ chunkMap.get(file.id)?.text || '(No preview available)' }}
              </p>
            </div>
          </Teleport>

          <!-- Metadata (fallback when no chunk preview) -->
          <div v-if="!enableHoverPreview || !chunkMap?.has(file.id)" class="w-[280px] p-3 space-y-2 bg-neutral-900/95 backdrop-blur-md rounded-lg border border-foreground/20 shadow-xl" @click.stop>
            <!-- Filename -->
            <div class="font-semibold text-white text-sm whitespace-normal break-words">
              {{ file.filename }}
            </div>

            <div class="border-t border-foreground/10 pt-2 space-y-2 text-sm text-foreground/80">
              <!-- Date Added -->
              <div class="flex items-center gap-2">
                <UIcon name="i-lucide-calendar" class="w-4 h-4 flex-shrink-0" />
                <span>{{ formatDate(file.created_at) }}</span>
              </div>

              <!-- File Size -->
              <div class="flex items-center gap-2">
                <UIcon name="i-lucide-hard-drive" class="w-4 h-4 flex-shrink-0" />
                <span>{{ formatSize(file.file_size_bytes) }}</span>
              </div>

              <!-- Group -->
              <div class="flex items-center gap-2">
                <UIcon name="i-lucide-folder" class="w-4 h-4 flex-shrink-0" />
                <div v-if="file.group_name" class="flex items-center gap-2">
                  <div
                    v-if="file.group_id && groupColors?.[file.group_id]"
                    class="w-2 h-2 rounded-full flex-shrink-0"
                    :style="{ backgroundColor: groupColors[file.group_id] }"
                  />
                  <span>{{ file.group_name }}</span>
                </div>
                <span v-else class="text-foreground/50 italic">No group</span>
              </div>

              <!-- Chunks & Pages (if available) -->
              <div v-if="formatChunksPages(file)" class="flex items-center gap-2">
                <UIcon name="i-lucide-file-text" class="w-4 h-4 flex-shrink-0" />
                <span>{{ formatChunksPages(file) }}</span>
              </div>
            </div>
          </div>
        </template>
      </UPopover>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="grid gap-1" style="grid-template-columns: repeat(auto-fill, minmax(150px, 1fr))">
      <div v-for="i in 6" :key="i" class="h-16 bg-neutral-200 dark:bg-neutral-800 rounded-lg animate-pulse" />
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

<style scoped>
.glass-card {
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(24px) saturate(1.4);
  -webkit-backdrop-filter: blur(24px) saturate(1.4);
  border: 1.5px solid rgba(255, 255, 255, 0.12);
  border-top-color: rgba(255, 255, 255, 0.2);
  border-left-color: rgba(255, 255, 255, 0.15);
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.4),
    inset 0 1px 1px rgba(255, 255, 255, 0.1),
    inset 0 -1px 1px rgba(255, 255, 255, 0.03);
}

.glass-card:hover {
  background: rgba(0, 0, 0, 0.55);
  border-color: rgba(255, 255, 255, 0.2);
  border-top-color: rgba(255, 255, 255, 0.3);
  border-left-color: rgba(255, 255, 255, 0.25);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.5),
    0 0 24px rgba(168, 85, 247, 0.08),
    inset 0 1px 1px rgba(255, 255, 255, 0.15),
    inset 0 -1px 1px rgba(255, 255, 255, 0.05);
  transform: translateY(-2px);
}

.glass-card.ring-2 {
  border-color: rgba(168, 85, 247, 0.5);
}
</style>
