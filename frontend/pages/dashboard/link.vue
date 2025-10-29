<script setup lang="ts">
import { h, resolveComponent, ref, reactive, watch, onMounted } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { useDebounceFn } from '@vueuse/core'

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
  fetchGoogleDriveFiles,
  files,
  googleLinked,
  loading: googleLoading,
  error,
  success,
  checkGoogleLinked
} = useGoogleDrive()

const { ingestGoogleDriveFileToSupabase } = useAddGoogleDriveFile()

const client = useSupabaseClient()
const toast = useToast()

/** ---------- Table state ---------- **/
const data = ref<GoogleDriveFile[]>([])
const sorting = ref([{ id: 'createdTime', desc: true }])
const pagination = reactive({ pageIndex: 0, pageSize: 20 })
const filenameQuery = ref('')

/** ---------- Import state ---------- **/
const selectedGroupId = ref<string | null>(null)
const importing = ref(false)

/** ---------- Bulk selection helpers ---------- **/
function selectedRowIds(): string[] {
  const rows = table?.value?.tableApi?.getSelectedRowModel().rows ?? []
  return rows.map((r: any) => r.original.id as string)
}

function getSelectedFiles(): GoogleDriveFile[] {
  const ids = selectedRowIds()
  return data.value.filter(f => ids.includes(f.id))
}

/** ---------- Columns ---------- **/
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

function formatSize(bytes?: number | null) {
  if (!bytes) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = bytes
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`
}

function formatDate(iso?: string) {
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

/** ---------- Fetch ---------- **/
const pending = ref(false)
const fetchError = ref<string | null>(null)

const fetchGoogleFiles = async () => {
  pending.value = true
  fetchError.value = null
  try {
    const { data: { session } } = await client.auth.getSession()
    if (session?.access_token) {
      await fetchGoogleDriveFiles(session.access_token)
      
      // Filter by filename query if provided
      let filtered = files.value
      if (filenameQuery.value) {
        filtered = files.value.filter(f => 
          f.name.toLowerCase().includes(filenameQuery.value.toLowerCase())
        )
      }
      
      data.value = filtered as GoogleDriveFile[]
    }
  } catch (e: any) {
    fetchError.value = e?.message || 'Failed to load files'
  } finally {
    pending.value = false
  }
}

const debouncedFetch = useDebounceFn(fetchGoogleFiles, 150)
watch([filenameQuery], () => {
  pagination.pageIndex = 0
  debouncedFetch()
})

/** ---------- Import handler ---------- **/
async function handleImportToHypaThymesia() {
  const selectedFiles = getSelectedFiles()
  
  if (!selectedFiles.length) {
    toast.add({
      title: 'No files selected',
      description: 'Select files to import',
      color: 'warning',
      icon: 'i-lucide-alert-circle'
    })
    return
  }

  importing.value = true
  let successCount = 0
  let failureCount = 0

  try {
    const { data: { session } } = await client.auth.getSession()
    if (!session?.access_token) throw new Error('No session')

    for (const file of selectedFiles) {
      try {
        await ingestGoogleDriveFileToSupabase(
          session.access_token,
          file,
          selectedGroupId.value || undefined,
          true
        )
        successCount++
      } catch (e: any) {
        console.error(`Failed to import ${file.name}:`, e)
        failureCount++
      }
    }

    // Deselect rows
    table.value?.tableApi?.resetRowSelection?.()

    toast.add({
      title: `Imported ${successCount} file(s)${failureCount ? `, ${failureCount} failed` : ''}`,
      color: failureCount > 0 ? 'warning' : 'success',
      icon: failureCount > 0 ? 'i-lucide-alert-triangle' : 'i-lucide-check'
    })
  } finally {
    importing.value = false
  }
}

onMounted(async () => {
  const { data: { session } } = await client.auth.getSession()
  if (session?.access_token) {
    // Check if already linked
    await checkGoogleLinked(session.access_token)
    
    // If linked, fetch files
    if (googleLinked.value) {
      await fetchGoogleFiles()
    }
  }
})

function getRowId(row: GoogleDriveFile) { return row.id }
</script>

<template>
  <BodyCard>
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <h1 class="font-semibold text-lg">Google Drive Files</h1>
        <div v-if="!googleLinked" class="text-sm text-muted">
          Link your Google account to browse files
        </div>
      </div>

      <!-- Link/Unlink component -->
      <div class="border-b pb-4">
        <div v-if="!googleLinked" class="space-y-2">
          <p class="text-sm text-gray-600">Connect your Google account to access your Drive files</p>
          <UButton
            @click="async () => {
              const { data: { session } } = await client.auth.getSession()
              if (session?.access_token) {
                const { linkGoogleAccount } = useGoogleDrive()
                await linkGoogleAccount(client, session.access_token)
              }
            }"
            :loading="googleLoading"
            icon="i-lucide-chrome"
          >
            Link Google Account
          </UButton>
        </div>

        <div v-else class="space-y-2">
          <div class="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-200">
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-check-circle" class="text-green-600" />
              <span class="text-sm font-medium text-green-700">Google account linked</span>
            </div>
          </div>

          <div class="flex gap-2">
            <UButton
              @click="fetchGoogleFiles"
              :loading="googleLoading"
              variant="soft"
              icon="i-lucide-refresh-ccw"
            >
              Refresh Files
            </UButton>

            <UButton
              @click="async () => {
                const { data: { session } } = await client.auth.getSession()
                if (session?.access_token) {
                  const { unlinkGoogle } = useGoogleDrive()
                  await unlinkGoogle(session.access_token)
                }
              }"
              :loading="googleLoading"
              variant="ghost"
              icon="i-lucide-unlink"
            >
              Unlink Google Account
            </UButton>
          </div>
        </div>
      </div>

      <!-- Search and Import Controls -->
      <div v-if="googleLinked" class="space-y-4">
        <div class="flex items-center gap-2">
          <UInput
            v-model="filenameQuery"
            placeholder="Search filename…"
            icon="i-lucide-magnifying-glass"
            class="flex-1"
          />
          <div class="text-sm text-muted whitespace-nowrap">
            <span v-if="!googleLoading">Total: {{ files.length.toLocaleString() }}</span>
            <span v-else>Loading…</span>
          </div>
        </div>

        <!-- Import Control Bar -->
        <div class="flex items-center gap-3 p-3 bg-muted/30 rounded-lg border border-accented">
          <USelect
            v-model="selectedGroupId"
            placeholder="Select group (optional)…"
            :options="[
              { label: 'No Group', value: null },
              { label: 'Test Group 1', value: 'test-1' },
              { label: 'Test Group 2', value: 'test-2' }
            ]"
            value-key="value"
            label-key="label"
            class="flex-1"
            :disabled="importing"
            nullable
          />
          <div class="text-xs text-muted">
            Selected: {{ selectedRowIds().length }} files
          </div>
          <UButton
            @click="handleImportToHypaThymesia"
            :loading="importing"
            :disabled="selectedRowIds().length === 0"
            color="success"
            icon="i-lucide-download"
          >
            Import to Hypa-Thymesia
          </UButton>
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
          <template #loading><div class="py-6 text-sm">Fetching files…</div></template>
          <template #empty><div class="py-6 text-sm">Nothing to show.</div></template>
        </UTable>

        <!-- Pagination -->
        <div class="flex items-center justify-between px-4 py-3.5 border-t border-accented text-sm text-muted">
          <div>Page {{ pagination.pageIndex + 1 }} • Showing {{ data.slice(pagination.pageIndex * pagination.pageSize, (pagination.pageIndex + 1) * pagination.pageSize).length }} / {{ data.length }}</div>
          <UPagination
            :default-page="pagination.pageIndex + 1"
            :items-per-page="pagination.pageSize"
            :total="data.length"
            @update:page="(p: number) => (pagination.pageIndex = p - 1)"
          />
        </div>

        <!-- Alerts -->
        <UAlert
          v-if="fetchError"
          icon="i-lucide-alert-circle"
          color="error"
          :title="fetchError"
          variant="subtle"
          class="mt-4"
        />
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