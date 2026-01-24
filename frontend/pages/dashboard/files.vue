<script setup lang="ts">
import { h, resolveComponent, ref, reactive, watch, onMounted } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import type { SortingState } from '@tanstack/vue-table'
import { useDebounceFn } from '@vueuse/core'
import {
  useDocuments,
  type DocumentItem,
  type SortField,
  type SortDir,
} from '@/composables/useDocuments'
import { NO_GROUP_VALUE } from '@/composables/useGroups'
import GroupSelect from '@/components/GroupSelect.vue'
import BodyCard from '@/components/BodyCard.vue'

const UButton = resolveComponent('UButton')
const UBadge = resolveComponent('UBadge')
const UCheckbox = resolveComponent('UCheckbox')
const UIcon = resolveComponent('UIcon')

const table = useTemplateRef('table')

const { listDocuments, deleteDocument, updateDocumentGroup } = useDocuments()
const toast = useToast()

/** ---------- Table state ---------- **/
const data = ref<DocumentItem[]>([])
const total = ref(0)
const sorting = ref<SortingState>([{ id: 'created_at', desc: true }])
const pagination = reactive({ pageIndex: 0, pageSize: 20 })
const selectedGroupId = ref<string | null>(null)
const searchQuery = ref<string>('')

/** ---------- Bulk selection helpers ---------- **/
function selectedRowIds(): string[] {
  const rows = table?.value?.tableApi?.getSelectedRowModel().rows ?? []
  return rows.map((r: any) => r.original.id as string)
}

/** ---------- Delete state ---------- **/
const deletingIds = ref<Set<string>>(new Set())

async function deleteDocument_(docId: string) {
  if (!confirm('Delete this document? This cannot be undone.')) return

  deletingIds.value.add(docId)
  try {
    await deleteDocument(docId)
    data.value = data.value.filter(d => d.id !== docId)
    total.value = Math.max(0, total.value - 1)
    toast.add({ title: 'Document deleted', color: 'success', icon: 'i-lucide-trash-2' })

    if (data.value.length === 0 && pagination.pageIndex > 0) {
      pagination.pageIndex -= 1
      await fetchFiles()
    }
  } catch (e: any) {
    toast.add({ title: e?.message ?? 'Delete failed', color: 'error', icon: 'i-lucide-alert-triangle' })
  } finally {
    deletingIds.value.delete(docId)
  }
}

/** ---------- Set group state ---------- **/
const settingGroupIds = ref<Set<string>>(new Set())
const selectedGroupForBulk = ref<string | null>(null)

async function setGroupForSelected() {
  const ids = selectedRowIds()
  if (!ids.length) {
    toast.add({ title: 'No documents selected', color: 'warning' })
    return
  }

  if (selectedGroupForBulk.value === null) {
    toast.add({ title: 'Please select a group', color: 'warning' })
    return
  }

  settingGroupIds.value = new Set(ids)
  try {
    // Convert NO_GROUP_VALUE sentinel to null for the backend
    const groupId = selectedGroupForBulk.value === NO_GROUP_VALUE ? null : selectedGroupForBulk.value

    for (const id of ids) {
      await updateDocumentGroup(id, groupId)
      const doc = data.value.find(d => d.id === id)
      if (doc) {
        doc.group_id = groupId
        doc.group_name = null
      }
    }
    toast.add({ title: `Updated ${ids.length} document(s)`, color: 'success', icon: 'i-lucide-check' })
    selectedGroupForBulk.value = null

    // Clear selection
    table.value?.tableApi?.toggleAllPageRowsSelected(false)
  } catch (e: any) {
    toast.add({ title: e?.message ?? 'Failed to update documents', color: 'error', icon: 'i-lucide-alert-triangle' })
  } finally {
    settingGroupIds.value.clear()
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
      onClick: () => column.toggleSorting(isSorted === 'asc')
    })
  }
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
  if (mime.startsWith('audio/')) return 'Audio'
  if (mime.startsWith('video/')) return 'Video'
  return mime
}

const columns: TableColumn<DocumentItem>[] = [
  {
    id: 'select',
    header: ({ table }) =>
      h(UCheckbox, {
        modelValue: table.getIsSomePageRowsSelected()
          ? 'indeterminate'
          : table.getIsAllPageRowsSelected(),
        'onUpdate:modelValue': (v: boolean | 'indeterminate') => table.toggleAllPageRowsSelected(!!v),
        'aria-label': 'Select all'
      }),
    cell: ({ row }) =>
      h(UCheckbox, {
        modelValue: row.getIsSelected(),
        'onUpdate:modelValue': (v: boolean | 'indeterminate') => row.toggleSelected(!!v),
        'aria-label': 'Select row'
      }),
    enableSorting: false,
    enableHiding: false
  },
  {
    accessorKey: 'filename',
    header: sortHeader('Name', 'filename'),
    cell: ({ row }) =>
      h('div', { class: 'truncate' }, [
        h('div', { class: 'font-medium truncate', title: row.original.filename }, row.original.filename),
        h('div', { class: 'text-xs text-muted truncate' }, prettyMime(row.original.mime_type))
      ])
  },
  {
    accessorKey: 'mime_type',
    header: 'Type',
    cell: ({ row }) =>
      h(UBadge, { variant: 'subtle', color: 'primary' }, () => prettyMime(row.original.mime_type))
  },
  {
    accessorKey: 'chunk_count',
    header: 'Chunks',
    cell: ({ row }) => row.original.chunk_count ?? '—'
  },
  {
    accessorKey: 'page_count',
    header: sortHeader('Pages', 'page_count'),
    cell: ({ row }) => row.original.page_count ?? '—'
  },
  {
    accessorKey: 'created_at',
    header: sortHeader('Created', 'created_at'),
    cell: ({ row }) => h('span', { title: row.original.created_at }, formatDate(row.original.created_at))
  },
  {
    accessorKey: 'group_name',
    header: 'Group',
    cell: ({ row }) =>
      row.original.group_name
        ? h('span', { class: 'inline-flex items-center gap-1' }, [h(UIcon, { name: 'i-heroicons-folder' }), row.original.group_name])
        : '—'
  },
  {
    id: 'actions',
    header: 'Actions',
    enableSorting: false,
    cell: ({ row }) =>
      h(UButton, {
        color: 'error',
        variant: 'ghost',
        size: 'sm',
        icon: 'i-lucide-trash-2',
        loading: deletingIds.value.has(row.original.id),
        disabled: deletingIds.value.has(row.original.id),
        onClick: () => deleteDocument_(row.original.id),
        'aria-label': 'Delete document'
      })
  }
]

/** ---------- Fetch (server-side) ---------- **/
const pending = ref(false)
const error = ref<string | null>(null)

function mapSortField(id?: string): SortField {
  switch (id) {
    case 'filename': return 'filename'
    case 'page_count': return 'page_count'
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

    const res = await listDocuments({
      group_id: selectedGroupId.value,
      sort: mapSortField(activeSort.id),
      dir: mapSortDir(activeSort.desc),
      page: pagination.pageIndex + 1,
      page_size: pagination.pageSize,
      search: searchQuery.value || undefined,
    })
    data.value = res.items
    total.value = res.total
  } catch (e: any) {
    error.value = e?.message || 'Failed to load documents'
  } finally {
    pending.value = false
  }
}

const debouncedFetch = useDebounceFn(fetchFiles, 150)
watch([sorting, () => pagination.pageIndex, () => pagination.pageSize], () => debouncedFetch(), { deep: true })
watch([selectedGroupId, searchQuery], () => {
  pagination.pageIndex = 0
  debouncedFetch()
})

onMounted(fetchFiles)

/** ---------- Utils ---------- **/
function formatDate(iso: string) {
  const d = new Date(iso)
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(d)
}

function getRowId(row: DocumentItem) { return row.id }
</script>

<template>
  <!-- Filters -->
  <BodyCard>
    <h1 class="font-semibold text-lg mb-4">Your Documents</h1>

    <!-- Filter block -->
    <div class="space-y-4">
      <div class="flex items-center gap-4 px-4 py-4 border-b border-accented bg-muted/20 rounded-md flex-wrap">
        <UInput
          v-model="searchQuery"
          type="text"
          placeholder="Search by filename..."
          icon="i-lucide-search"
          :ui="{ base: 'w-48' }"
        />

        <GroupSelect v-model="selectedGroupId" :include-no-group="true" />

        <div class="text-sm text-muted">
          <span v-if="!pending">Total: {{ total.toLocaleString() }}</span>
          <span v-else>Loading…</span>
        </div>
      </div>
    </div>
  </BodyCard>

  <!-- Documents Table -->
  <BodyCard>
    <div class="flex items-center justify-between mb-4 px-4 pt-4">
      <h2 class="font-semibold text-lg">Files</h2>
      <UButton
        color="primary"
        icon="i-lucide-refresh-ccw"
        variant="outline"
        @click="fetchFiles"
      >
        Refresh
      </UButton>
    </div>
    <UTable
      ref="table"
      :data="data"
      :columns="columns"
      :loading="pending"
      sticky
      empty="No documents found."
      :ui="{ root: 'min-w-full', td: 'whitespace-nowrap' }"
      :pagination="pagination"
      :sorting="sorting"
      :getRowId="getRowId"
      class="flex-1"
    >
      <template #loading><div class="py-6 text-sm">Fetching documents…</div></template>
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

  <!-- Bulk actions -->
  <BodyCard>
    <h2 class="font-semibold text-lg mb-3">Bulk Actions</h2>
    <div class="flex flex-wrap gap-4 items-center px-4 py-3 border-b border-accented bg-muted/20 rounded-md">
      <div class="flex items-center gap-2">
        <label class="text-sm font-medium">Set Group:</label>
        <GroupSelect
          v-model="selectedGroupForBulk"
          :include-no-group="true"
        />
      </div>
      <UButton
        color="primary"
        icon="i-lucide-check"
        variant="outline"
        :disabled="!selectedRowIds().length || !selectedGroupForBulk || settingGroupIds.size > 0"
        :loading="settingGroupIds.size > 0"
        @click="setGroupForSelected"
      >
        Apply
      </UButton>
    </div>
  </BodyCard>
</template>
