<script setup lang="ts">
import { h, resolveComponent, ref, reactive, watch, onMounted } from 'vue'
import type { TableColumn } from '@nuxt/ui'

const UButton = resolveComponent('UButton')
const UBadge = resolveComponent('UBadge')
const UCheckbox = resolveComponent('UCheckbox')
const UIcon = resolveComponent('UIcon')

interface GoogleDriveFile {
  id: string
  name: string
  mimeType?: string
  createdTime?: string
  modifiedTime?: string
  webViewLink?: string
  size?: number
}

const table = useTemplateRef('table')

const {
  error,
  success,
  loading: googleLoading,
  files,
  googleLinked,
  isInitialized,
  checkGoogleLinked,
  linkGoogleAccount,
  unlinkGoogle,
  fetchGoogleDriveFiles
} = useGoogleDrive()

const client = useSupabaseClient()
const toast = useToast()

/** ---------- Table state ---------- **/
const data = ref<GoogleDriveFile[]>([])
const sorting = ref([{ id: 'createdTime', desc: true }])
const pagination = reactive({ pageIndex: 0, pageSize: 20 })
const filenameQuery = ref('')

/** ---------- UI state ---------- **/
const linking = ref(false)
const unlinking = ref(false)
const initializing = ref(true)

/** ---------- Bulk selection helpers ---------- **/
function selectedRowIds(): string[] {
  const rows = table?.value?.tableApi?.getSelectedRowModel().rows ?? []
  return rows.map((r: any) => r.original.id as string)
}

function getSelectedFiles(): GoogleDriveFile[] {
  const ids = selectedRowIds()
  return data.value.filter(f => ids.includes(f.id))
}

/** ---------- Formatting helpers ---------- **/
function prettyMime(mime?: string): string {
  if (!mime) return '—'
  if (mime.includes('pdf')) return 'PDF'
  if (mime.includes('document')) return 'Document'
  if (mime.includes('spreadsheet')) return 'Spreadsheet'
  if (mime.includes('presentation')) return 'Presentation'
  if (mime === 'image/png') return 'PNG Image'
  if (mime === 'image/jpeg' || mime === 'image/jpg') return 'JPEG Image'
  if (mime.startsWith('image/')) return 'Image'
  if (mime.startsWith('text/')) return 'Text'
  if (mime === 'application/vnd.google-apps.folder') return 'Folder'
  return mime
}

function formatSize(bytes?: number | null): string {
  if (!bytes) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = bytes
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`
}

function formatDate(iso?: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(d)
}

function sortHeader(label: string, columnId: string) {
  return ({ column }: any) => {
    const isSorted = column.getIsSorted()
    return h(UButton, {
      color: 'neutral',
      variant: 'ghost',
      label,
      icon: isSorted
        ? (isSorted === 'asc'
            ? 'i-lucide-arrow-up-narrow-wide'
            : 'i-lucide-arrow-down-wide-narrow')
        : 'i-lucide-arrow-up-down',
      class: '-mx-2.5',
      onClick: () => column.toggleSorting(isSorted === 'asc')
    })
  }
}

/** ---------- Table columns ---------- **/
const columns: TableColumn<GoogleDriveFile>[] = [
  {
    id: 'select',
    header: ({ table }: any) =>
      h(UCheckbox, {
        modelValue: table.getIsSomePageRowsSelected()
          ? 'indeterminate'
          : table.getIsAllPageRowsSelected(),
        'onUpdate:modelValue': (v: boolean | 'indeterminate') => table.toggleAllPageRowsSelected(!!v),
        'aria-label': 'Select all'
      }),
    cell: ({ row }: any) =>
      h(UCheckbox, {
        modelValue: row.getIsSelected(),
        'onUpdate:modelValue': (v: boolean | 'indeterminate') => row.toggleSelected(!!v),
        'aria-label': 'Select row'
      }),
    enableSorting: false,
    enableHiding: false
  },
  {
    accessorKey: 'name',
    header: sortHeader('Name', 'name'),
    cell: ({ row }: any) =>
      h('div', { class: 'truncate' }, [
        h('div', { class: 'font-medium truncate', title: row.original.name }, row.original.name),
        h('div', { class: 'text-xs text-muted truncate' }, prettyMime(row.original.mimeType))
      ])
  },
  {
    accessorKey: 'mimeType',
    header: 'Type',
    cell: ({ row }: any) =>
      h(UBadge, { variant: 'subtle', color: 'primary' }, () => prettyMime(row.original.mimeType))
  },
  {
    accessorKey: 'size',
    header: sortHeader('Size', 'size'),
    cell: ({ row }: any) => formatSize(row.original.size)
  },
  {
    accessorKey: 'createdTime',
    header: sortHeader('Created', 'createdTime'),
    cell: ({ row }: any) => h('span', { title: row.original.createdTime }, formatDate(row.original.createdTime))
  },
  {
    accessorKey: 'modifiedTime',
    header: sortHeader('Modified', 'modifiedTime'),
    cell: ({ row }: any) => h('span', { title: row.original.modifiedTime }, formatDate(row.original.modifiedTime))
  },
  {
    id: 'actions',
    header: 'Actions',
    cell: ({ row }: any) =>
      h(UButton, {
        size: 'xs',
        color: 'primary',
        variant: 'soft',
        icon: 'i-lucide-external-link',
        onClick: () => {
          if (row.original.webViewLink) {
            window.open(row.original.webViewLink, '_blank')
          }
        }
      }, () => 'Open')
  }
]

/** ---------- Event handlers ---------- **/

async function handleLinkGoogle() {
  linking.value = true
  try {
    const { data: { session } } = await client.auth.getSession()
    if (!session?.access_token) throw new Error('No session')

    // Trigger twice to ensure it works
    await linkGoogleAccount(client, session.access_token)
    
    // Small delay then trigger again
    await new Promise(resolve => setTimeout(resolve, 500))
    await linkGoogleAccount(client, session.access_token)
  } catch (err) {
    toast.add({
      title: 'Link failed',
      description: error.value || 'Failed to link Google account',
      color: 'error',
      icon: 'i-lucide-alert-circle'
    })
  } finally {
    linking.value = false
  }
}

async function handleUnlinkGoogle() {
  unlinking.value = true
  try {
    const { data: { session } } = await client.auth.getSession()
    if (!session?.access_token) throw new Error('No session')

    await unlinkGoogle(client, session.access_token)
    data.value = []
    filenameQuery.value = ''

    toast.add({
      title: 'Unlinked',
      description: 'Your Google Drive connection has been removed',
      color: 'success',
      icon: 'i-lucide-check'
    })
  } catch (err) {
    toast.add({
      title: 'Unlink failed',
      description: error.value || 'Failed to unlink Google account',
      color: 'error',
      icon: 'i-lucide-alert-circle'
    })
  } finally {
    unlinking.value = false
  }
}

async function handleFetchFiles() {
  try {
    const { data: { session } } = await client.auth.getSession()
    if (!session?.access_token) throw new Error('No session')

    await fetchGoogleDriveFiles(session.access_token)
    
    // files.value is now a computed that returns mutable array
    if (filenameQuery.value) {
      data.value = files.value.filter(f =>
        f.name.toLowerCase().includes(filenameQuery.value.toLowerCase())
      )
    } else {
      data.value = files.value
    }

    toast.add({
      title: 'Files loaded',
      description: `Found ${files.value.length} files`,
      color: 'success',
      icon: 'i-lucide-check'
    })
  } catch (err) {
    toast.add({
      title: 'Failed to load files',
      description: error.value || 'An error occurred',
      color: 'error',
      icon: 'i-lucide-alert-circle'
    })
  }
}

/** ---------- Watch for search input ---------- **/
watch([filenameQuery], () => {
  pagination.pageIndex = 0
  
  if (!files.value.length) return
  
  if (filenameQuery.value) {
    data.value = files.value.filter(f =>
      f.name.toLowerCase().includes(filenameQuery.value.toLowerCase())
    )
  } else {
    data.value = files.value
  }
})

/** ---------- Initialize on mount ---------- **/
onMounted(async () => {
  try {
    const { data: { session } } = await client.auth.getSession()
    if (session?.access_token) {
      // Check if Google is linked
      await checkGoogleLinked(session.access_token)
      
      // If linked, fetch files
      if (googleLinked.value) {
        await fetchGoogleDriveFiles(session.access_token)
        data.value = files.value
      }
    }
  } catch (err) {
    console.error('Initialization error:', err)
  } finally {
    initializing.value = false
  }
})

function getRowId(row: GoogleDriveFile) { 
  return row.id 
}
</script>

<template>
  <BodyCard>
    <div class="space-y-4">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <h1 class="font-semibold text-lg">Google Drive Files</h1>
        <div v-if="!googleLinked && isInitialized" class="text-sm text-muted">
          Link your Google account to browse files
        </div>
      </div>

      <!-- Link/Unlink Section -->
      <div class="border-b pb-4">
        <div v-if="!googleLinked" class="space-y-2">
          <p class="text-sm text-gray-600">
            Connect your Google account to access your Drive files
          </p>
          <UButton
            @click="handleLinkGoogle"
            :loading="linking"
            icon="i-lucide-chrome"
          >
            Link Google Account
          </UButton>
        </div>

        <div v-else class="space-y-2">
          <div class="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-200">
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-check-circle" class="text-green-600" />
              <span class="text-sm font-medium text-green-700">
                Google account linked
              </span>
            </div>
          </div>

          <div class="flex gap-2 flex-wrap">
            <UButton
              @click="handleFetchFiles"
              :loading="googleLoading"
              variant="soft"
              icon="i-lucide-refresh-ccw"
            >
              Refresh Files
            </UButton>

            <UButton
              @click="handleUnlinkGoogle"
              :loading="unlinking"
              :disabled="googleLoading"
              variant="outline"
              icon="i-lucide-unlink"
              color="red"
            >
              Unlink Google Account
            </UButton>
          </div>
        </div>
      </div>

      <!-- Files Section -->
      <div v-if="googleLinked" class="space-y-4">
        <!-- Search -->
        <div class="flex items-center gap-2">
          <UInput
            v-model="filenameQuery"
            placeholder="Search filename…"
            icon="i-lucide-magnifying-glass"
            class="flex-1"
          />
          <div class="text-sm text-muted whitespace-nowrap">
            <span v-if="!googleLoading">
              Total: {{ files.length.toLocaleString() }}
            </span>
            <span v-else>Loading…</span>
          </div>
        </div>

        <!-- Files Table -->
        <UTable
          ref="table"
          :data="data.slice(
            pagination.pageIndex * pagination.pageSize,
            (pagination.pageIndex + 1) * pagination.pageSize
          )"
          :columns="columns"
          :loading="googleLoading"
          sticky
          empty="No files found."
          :ui="{ root: 'min-w-full', td: 'whitespace-nowrap' }"
          :sorting="sorting"
          :getRowId="getRowId"
          class="flex-1"
        >
          <template #loading>
            <div class="py-6 text-sm">Fetching files…</div>
          </template>
          <template #empty>
            <div class="py-6 text-sm">Nothing to show.</div>
          </template>
        </UTable>

        <!-- Pagination -->
        <div class="flex items-center justify-between px-4 py-3.5 border-t border-accented text-sm text-muted">
          <div>
            Page {{ pagination.pageIndex + 1 }} •
            Showing {{ data.slice(pagination.pageIndex * pagination.pageSize, (pagination.pageIndex + 1) * pagination.pageSize).length }} / {{ data.length }}
          </div>
          <UPagination
            :default-page="pagination.pageIndex + 1"
            :items-per-page="pagination.pageSize"
            :total="data.length"
            @update:page="(p: number) => (pagination.pageIndex = p - 1)"
          />
        </div>

        <!-- Alerts -->
        <UAlert
          v-if="error"
          icon="i-lucide-alert-circle"
          color="error"
          :title="error"
          variant="subtle"
          class="mt-4"
        />
        <UAlert
          v-if="success"
          icon="i-lucide-check-circle"
          color="success"
          :title="success"
          variant="subtle"
          class="mt-4"
        />
      </div>
    </div>
  </BodyCard>
</template>