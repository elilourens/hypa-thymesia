<script setup lang="ts">
import { h, resolveComponent, ref, reactive, watch, onMounted } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import type { SortingState } from '@tanstack/vue-table'
import { useDebounceFn } from '@vueuse/core'
import {
  useFilesApi,
  type FileItem,
  type SortField,
  type SortDir,
} from '~/composables/useFiles'
import { useGroupsApi, NO_GROUP_VALUE } from '@/composables/useGroups'
import { useIngest } from '@/composables/useIngest'
import GroupSelect from '@/components/GroupSelect.vue'
import BodyCard from '@/components/BodyCard.vue'

const UButton = resolveComponent('UButton')
const UBadge = resolveComponent('UBadge')
const UCheckbox = resolveComponent('UCheckbox')
const UIcon = resolveComponent('UIcon')
const UInput = resolveComponent('UInput')

const table = useTemplateRef('table')
const { listFiles } = useFilesApi()
const { setDocGroup } = useGroupsApi()
const { deleteDoc } = useIngest()
const toast = useToast()

/** ---------- Table state ---------- **/
const data = ref<FileItem[]>([])
const total = ref(0)
const sorting = ref<SortingState>([{ id: 'created_at', desc: true }])
const pagination = reactive({ pageIndex: 0, pageSize: 20 })
const filenameQuery = ref('')
const selectedGroupId = ref<string | null>(null)

/** ---------- Bulk selection helpers ---------- **/
function selectedRowIds(): string[] {
  const rows = table?.value?.tableApi?.getSelectedRowModel().rows ?? []
  return rows.map((r: any) => r.original.doc_id as string)
}

/** ---------- Delete state ---------- **/
const deleting = ref(false)

async function deleteSelected() {
  const ids = selectedRowIds()
  if (!ids.length) return
  if (!confirm(`Delete ${ids.length} document(s)? This cannot be undone.`)) return

  deleting.value = true
  try {
    for (const id of ids) {
      await deleteDoc(id)
      data.value = data.value.filter(d => d.doc_id !== id)
      total.value = Math.max(0, total.value - 1)
    }
    toast.add({ title: `Deleted ${ids.length} file(s)`, color: 'success', icon: 'i-lucide-trash-2' })
  } catch (e: any) {
    toast.add({ title: e?.message ?? 'Delete failed', color: 'error', icon: 'i-lucide-alert-triangle' })
  } finally {
    deleting.value = false
    if (data.value.length === 0 && pagination.pageIndex > 0) {
      pagination.pageIndex -= 1
      await fetchFiles()
    }
  }
}

/** ---------- Bulk group change ---------- **/
const updatingGroup = ref(false)

async function bulkChangeGroup(value: string | null) {
  const ids = selectedRowIds()
  if (!ids.length) return

  const gid: string | null = value === NO_GROUP_VALUE ? null : value
  updatingGroup.value = true
  try {
    for (const id of ids) {
      await setDocGroup(id, gid)
      const row = data.value.find(d => d.doc_id === id)
      if (row) {
        row.group_id = gid
        row.group_name = gid ? row.group_name : null
      }
    }
    toast.add({
      title: gid ? `Moved ${ids.length} file(s) to group` : `Cleared group for ${ids.length} file(s)`,
      color: 'success',
      icon: 'i-lucide-check',
    })
  } catch (e: any) {
    toast.add({ title: e?.message ?? 'Failed to change group', color: 'error', icon: 'i-lucide-alert-triangle' })
  } finally {
    updatingGroup.value = false
  }
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
      onClick: () => column.toggleSorting(isSorted === 'asc'),
    })
  }
}

function stripLeadingUuid(name: string) {
  return name.replace(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/i, '')
}

function prettyMime(mime?: string): string {
  if (!mime) return '—'
  if (mime.includes('pdf')) return 'PDF'
  if (mime.includes('wordprocessingml')) return 'Word Doc'
  if (mime.includes('spreadsheetml')) return 'Excel Sheet'
  if (mime.includes('presentationml')) return 'PowerPoint'
  if (mime === 'image/png') return 'PNG Image'
  if (mime === 'image/jpeg' || mime === 'image/jpg') return 'JPEG Image'
  if (mime === 'text/plain') return 'Text File'
  if (mime.startsWith('image/')) return 'Image'
  if (mime.startsWith('text/')) return 'Text'
  return mime
}

const columns: TableColumn<FileItem>[] = [
  {
    id: 'select',
    header: ({ table }) =>
      h(UCheckbox, {
        modelValue: table.getIsSomePageRowsSelected()
          ? 'indeterminate'
          : table.getIsAllPageRowsSelected(),
        'onUpdate:modelValue': (v: boolean | 'indeterminate') => table.toggleAllPageRowsSelected(!!v),
        'aria-label': 'Select all',
      }),
    cell: ({ row }) =>
      h(UCheckbox, {
        modelValue: row.getIsSelected(),
        'onUpdate:modelValue': (v: boolean | 'indeterminate') => row.toggleSelected(!!v),
        'aria-label': 'Select row',
      }),
    enableSorting: false,
    enableHiding: false,
  },
  {
    accessorKey: 'filename',
    header: sortHeader('Name', 'filename'),
    cell: ({ row }) =>
      h('div', { class: 'truncate' }, [
        h('div', { class: 'font-medium truncate', title: row.original.filename }, stripLeadingUuid(row.original.filename)),
        h('div', { class: 'text-xs text-muted truncate' }, prettyMime(row.original.mime_type)),
      ]),
  },
  {
    accessorKey: 'modality',
    header: 'Modality',
    cell: ({ row }) => h(UBadge, { variant: 'subtle' }, () => row.original.modality || '—'),
  },
  {
    accessorKey: 'mime_type',
    header: 'Type',
    cell: ({ row }) =>
      h(UBadge, { variant: 'subtle', color: 'primary' }, () => prettyMime(row.original.mime_type)),
  },
  {
    accessorKey: 'size_bytes',
    header: sortHeader('Size', 'size_bytes'),
    cell: ({ row }) => formatSize(row.original.size_bytes),
  },
  {
    accessorKey: 'created_at',
    header: sortHeader('Created', 'created_at'),
    cell: ({ row }) => h('span', { title: row.original.created_at }, formatDate(row.original.created_at)),
  },
  {
    accessorKey: 'group_name',
    header: 'Group',
    cell: ({ row }) =>
      row.original.group_name
        ? h('span', { class: 'inline-flex items-center gap-1' }, [h(UIcon, { name: 'i-heroicons-folder' }), row.original.group_name])
        : '—',
  },
]

/** ---------- Fetch (server-side) ---------- **/
const pending = ref(false)
const error = ref<string | null>(null)

function mapSortField(id?: string): SortField {
  switch (id) {
    case 'filename': return 'name'
    case 'size_bytes': return 'size'
    case 'created_at':
    default: return 'created_at'
  }
}
function mapSortDir(desc?: boolean): SortDir {
  return desc ? 'desc' : 'asc'
}

const fetchFiles = async () => {
  pending.value = true
  error.value = null
  try {
    const activeSort = sorting.value[0] || { id: 'created_at', desc: true }
    const res = await listFiles({
      q: filenameQuery.value || null,
      group_id: selectedGroupId.value === NO_GROUP_VALUE ? '' : selectedGroupId.value || null,
      sort: mapSortField(activeSort.id),
      dir: mapSortDir(activeSort.desc),
      page: pagination.pageIndex + 1,
      page_size: pagination.pageSize,
      group_sort: 'none',
    })
    data.value = res.items
    total.value = res.total
  } catch (e: any) {
    error.value = e?.message || 'Failed to load files'
  } finally {
    pending.value = false
  }
}

const debouncedFetch = useDebounceFn(fetchFiles, 150)
watch([sorting, () => pagination.pageIndex, () => pagination.pageSize], () => debouncedFetch(), { deep: true })
watch(filenameQuery, () => { pagination.pageIndex = 0; debouncedFetch() })
watch(selectedGroupId, () => { pagination.pageIndex = 0; debouncedFetch() })
onMounted(fetchFiles)

/** ---------- Utils ---------- **/
function formatSize(n?: number | null) {
  if (n == null) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = n
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`
}
function formatDate(iso: string) {
  const d = new Date(iso)
  return new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(d)
}
function getRowId(row: FileItem) { return row.doc_id }
</script>

<template>
  <!-- Search & Tools -->
  <BodyCard>
    <h1 class="font-semibold text-lg mb-4">Stored Files</h1>
    <div class="flex flex-col gap-4 w-full">
      <!-- Search Row -->
      <div class="flex items-center gap-3 px-4 py-3.5 border-b border-accented overflow-x-auto">
        
        <UInput
          v-model="filenameQuery"
          class="max-w-sm min-w-[16ch]"
          placeholder="Search filename…"
          icon="i-heroicons-magnifying-glass-20-solid"
        />
        <GroupSelect v-model="selectedGroupId" :include-no-group="true" class="w-64" />
        <UButton
          color="neutral"
          icon="i-lucide-refresh-ccw"
          variant="ghost"
          @click="fetchFiles"
        >
          Refresh Table 
        </UButton>

        <div class="ms-auto flex items-center gap-3 text-sm text-muted">
          <span v-if="!pending">Total: {{ total.toLocaleString() }}</span>
          <span v-else>Loading…</span>
        </div>
      </div>

      <!-- Bulk Actions -->
      <div class="flex items-center gap-20 px-4 py-2 border-b border-accented bg-muted/30">
        
        <GroupSelect
          :model-value="null"
          placeholder="Move selected to group…"
          :include-no-group="true"
          class="w-64"
          :disabled="!selectedRowIds().length || updatingGroup"
          @update:model-value="bulkChangeGroup"
        />
        <UButton
          color="error"
          icon="i-lucide-trash-2"
          variant="outline"
          :disabled="!selectedRowIds().length || deleting"
          @click="deleteSelected"
        >
          Delete Selected
        </UButton>
      </div>
    </div>
  </BodyCard>

  <!-- Files Table -->
  <BodyCard>
    <UTable
      ref="table"
      :data="data"
      :columns="columns"
      :loading="pending"
      sticky
      empty="No files found."
      :ui="{ root: 'min-w-full', td: 'whitespace-nowrap' }"
      :pagination="pagination"
      :sorting="sorting"
      :getRowId="getRowId"
      class="flex-1"
    >
      <template #loading><div class="py-6 text-sm">Fetching files…</div></template>
      <template #empty><div class="py-6 text-sm">Nothing to show.</div></template>
    </UTable>

    <!-- Footer -->
    <div class="flex items-center justify-between px-4 py-3.5 border-t border-accented text-sm text-muted">
      <div>Page {{ pagination.pageIndex + 1 }} • Showing {{ data.length }} / {{ total.toLocaleString() }}</div>
      <UPagination
        :default-page="pagination.pageIndex + 1"
        :items-per-page="pagination.pageSize"
        :total="total"
        @update:page="(p: number) => (pagination.pageIndex = p - 1)"
      />
    </div>

    <UAlert
      v-if="error"
      icon="i-heroicons-exclamation-triangle"
      color="error"
      :title="error"
      variant="subtle"
      class="mx-4 mb-4"
    />
  </BodyCard>
</template>
