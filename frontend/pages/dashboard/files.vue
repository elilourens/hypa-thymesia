<script setup lang="ts">
import { h, resolveComponent, onMounted, ref, computed, watch } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import type { SortingState } from '@tanstack/vue-table'
import { useDebounceFn } from '@vueuse/core'
import {
  useFilesApi,
  type FileItem,
  type SortField,
  type SortDir
} from '~/composables/useFiles'
import { useGroupsApi, type Group, NO_GROUP_VALUE } from '@/composables/useGroups'
import { useIngest } from '@/composables/useIngest'

const UButton = resolveComponent('UButton')
const UBadge = resolveComponent('UBadge')
const UCheckbox = resolveComponent('UCheckbox')
const UDropdownMenu = resolveComponent('UDropdownMenu')
const UIcon = resolveComponent('UIcon')
const UInput = resolveComponent('UInput')
const USelectMenu = resolveComponent('USelectMenu')

const table = useTemplateRef('table')
const { listFiles } = useFilesApi()
// pull all group APIs we need (list + set)
const { listGroups, setDocGroup } = useGroupsApi()
const { deleteDoc } = useIngest()
const toast = useToast()

/** ---------- Table state ---------- **/
const data = ref<FileItem[]>([])
const total = ref(0)

const sorting = ref<SortingState>([
  { id: 'created_at', desc: true }
])

const pagination = ref({
  pageIndex: 0,
  pageSize: 20
})

// Filename-only search term
const filenameQuery = ref('')

// Group filter
const groups = ref<Group[]>([])
const loadingGroups = ref(false)
const selectedGroupId = ref<string | undefined>(undefined)

const sortedGroups = computed(() =>
  [...groups.value].sort(
    (a, b) =>
      (a.sort_index ?? 0) - (b.sort_index ?? 0) ||
      a.name.localeCompare(b.name)
  )
)
const selectOptions = computed(() => [
  { label: 'No Group', value: NO_GROUP_VALUE },   // special option
  ...sortedGroups.value.map(g => ({
    label: g.name ?? '(unnamed)',
    value: g.id,
  }))
])


async function refreshGroups() {
  loadingGroups.value = true
  try {
    groups.value = await listGroups()
  } catch (e: any) {
    console.error('[groups error]', e)
  } finally {
    loadingGroups.value = false
  }
}

/** ---------- Delete state & helpers ---------- **/
const deleting = ref(false)
const deletingIds = ref<Set<string>>(new Set())

function selectedRowIds(): string[] {
  const rows = table?.value?.tableApi?.getSelectedRowModel().rows ?? []
  return rows.map((r: any) => r.original.doc_id as string)
}

async function deleteOne(id: string) {
  if (!confirm('Delete this document? This cannot be undone.')) return
  deleting.value = true
  deletingIds.value.add(id)
  try {
    await deleteDoc(id)
    const before = data.value.length
    data.value = data.value.filter(d => d.doc_id !== id)
    total.value = Math.max(0, total.value - 1)
    if (before > 0 && data.value.length === 0 && (pagination.value.pageIndex > 0)) {
      pagination.value.pageIndex = pagination.value.pageIndex - 1
      await fetchFiles()
    }
    toast.add({ title: 'Deleted', color: 'success', icon: 'i-lucide-trash-2' })
  } catch (e: any) {
    toast.add({ title: e?.message ?? 'Delete failed', color: 'error', icon: 'i-lucide-alert-triangle' })
  } finally {
    deletingIds.value.delete(id)
    deleting.value = deletingIds.value.size > 0
  }
}

async function deleteSelected() {
  const ids = selectedRowIds()
  if (!ids.length) return
  if (!confirm(`Delete ${ids.length} selected document${ids.length === 1 ? '' : 's'}? This cannot be undone.`)) return

  deleting.value = true
  ids.forEach(id => deletingIds.value.add(id))

  const results = await Promise.allSettled(ids.map(id => deleteDoc(id)))

  const okIds = results
    .map((r, i) => (r.status === 'fulfilled' ? ids[i] : null))
    .filter((id): id is string => id !== null)

  if (okIds.length) {
    const okSet = new Set(okIds)
    data.value = data.value.filter(d => !okSet.has(d.doc_id))
    total.value = Math.max(0, total.value - okIds.length)
  }

  table?.value?.tableApi?.resetRowSelection?.()

  if (data.value.length === 0 && pagination.value.pageIndex > 0) {
    pagination.value.pageIndex = pagination.value.pageIndex - 1
  }
  await fetchFiles()

  const failed = results.filter(r => r.status === 'rejected').length
  if (failed) {
    toast.add({
      title: `Deleted ${okIds.length}, failed ${failed}`,
      color: 'warning',
      icon: 'i-lucide-alert-triangle'
    })
  } else {
    toast.add({
      title: `Deleted ${okIds.length} item${okIds.length === 1 ? '' : 's'}`,
      color: 'success',
      icon: 'i-lucide-trash-2'
    })
  }

  deletingIds.value.clear()
  deleting.value = false
}

/** ---------- Per-row "change group" state & helpers ---------- **/
const updatingGroup = ref<Set<string>>(new Set())

async function changeDocGroup(docId: string, value: string) {
  // value is either NO_GROUP_VALUE or a real group id
  const gid: string | null = value === NO_GROUP_VALUE ? null : value
  updatingGroup.value.add(docId)
  try {
    await setDocGroup(docId, gid)

    // optimistic update of the row
    const row = data.value.find(d => d.doc_id === docId)
    if (row) {
      row.group_id = gid
      row.group_name = gid
        ? (groups.value.find(g => g.id === gid)?.name ?? row.group_name ?? '')
        : null
    }

    toast.add({
      title: gid ? 'Moved to group' : 'Cleared group',
      color: 'success',
      icon: 'i-lucide-check'
    })
  } catch (e: any) {
    toast.add({
      title: e?.message ?? 'Failed to change group',
      color: 'error',
      icon: 'i-lucide-alert-triangle'
    })
  } finally {
    updatingGroup.value.delete(docId)
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

function stripLeadingUuid(name: string) {
  return name.replace(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/i,
    ''
  )
}

const columns: TableColumn<FileItem>[] = [
  {
    id: 'select',
    header: ({ table }) =>
      h(UCheckbox, {
        modelValue: table.getIsSomePageRowsSelected()
          ? 'indeterminate'
          : table.getIsAllPageRowsSelected(),
        'onUpdate:modelValue': (v: boolean | 'indeterminate') =>
          table.toggleAllPageRowsSelected(!!v),
        'aria-label': 'Select all'
      }),
    cell: ({ row }) =>
      h(UCheckbox, {
        modelValue: row.getIsSelected(),
        'onUpdate:modelValue': (v: boolean | 'indeterminate') =>
          row.toggleSelected(!!v),
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
        h(
          'div',
          { class: 'font-medium truncate', title: row.original.filename },
          stripLeadingUuid(row.original.filename)
        ),
        h('div', { class: 'text-xs text-muted truncate' }, row.original.mime_type || '—')
      ])
  },
  {
    accessorKey: 'modality',
    header: 'Modality',
    cell: ({ row }) =>
      h(UBadge, { variant: 'subtle' }, () => row.original.modality || '—')
  },
  { accessorKey: 'mime_type', header: 'MIME' },
  {
    accessorKey: 'size_bytes',
    header: sortHeader('Size', 'size_bytes'),
    cell: ({ row }) => formatSize(row.original.size_bytes)
  },
  {
    accessorKey: 'created_at',
    header: sortHeader('Created', 'created_at'),
    cell: ({ row }) =>
      h('span', { title: row.original.created_at }, formatDate(row.original.created_at))
  },
  {
    accessorKey: 'group_name',
    header: 'Group',
    cell: ({ row }) =>
      row.original.group_name
        ? h('span', { class: 'inline-flex items-center gap-1' }, [
            h(UIcon, { name: 'i-heroicons-folder' }),
            row.original.group_name
          ])
        : '—'
  },
  {
    id: 'actions',
    enableHiding: false,
    cell: ({ row }) => {
      const id = row.original.doc_id
      const selectedCount: number =
        table?.value?.tableApi?.getSelectedRowModel?.().rows?.length ?? 0

      // Build the "Move to group" items: No Group + all groups
      const currentGroupId = row.original.group_id ?? null
      const moveItems: any[] = [
        {
          label: updatingGroup.value.has(id) ? 'Moving…' : 'Move to group',
          type: 'label' as const
        },
        {
          label: 'No Group',
          // visually mark current choice if empty
          // if your menu supports 'checked' use it; otherwise remove
          checked: currentGroupId === null,
          onSelect: () => changeDocGroup(id, NO_GROUP_VALUE)
        },
        ...sortedGroups.value.map(g => ({
          label: g.name || '(unnamed)',
          checked: currentGroupId === g.id,
          onSelect: () => changeDocGroup(id, g.id)
        }))
      ]

      const baseItems: any[] = [
        { type: 'label', label: 'Actions' },
        {
          label: 'Copy ID',
          onSelect: () => {
            navigator.clipboard?.writeText(id)
            toast.add({ title: 'ID copied', color: 'success', icon: 'i-lucide-circle-check' })
          }
        },
        { type: 'separator' as const },
        {
          label: deletingIds.value.has(id) ? 'Deleting…' : 'Delete',
          disabled: deletingIds.value.has(id),
          icon: 'i-lucide-trash-2',
          onSelect: () => deleteOne(id)
        },
        { type: 'separator' as const },
        ...moveItems
      ]

      return h(
        'div',
        { class: 'text-right' },
        h(
          UDropdownMenu,
          {
            content: { align: 'end' },
            items: baseItems,
            // refresh groups when the menu opens so list is fresh
            'onUpdate:open': (open: boolean) => { if (open && !groups.value.length) refreshGroups() }
          },
          () =>
            h(UButton, {
              icon: 'i-lucide-ellipsis-vertical',
              color: 'neutral',
              variant: 'ghost',
              class: 'ml-auto',
              'aria-label': 'Actions'
            })
        )
      )
    }
  }
]

/** ---------- Fetch (server-side) ---------- **/
const pending = ref(false)
const error = ref<string | null>(null)

function mapSortField(id?: string): SortField {
  switch (id) {
    case 'filename':
      return 'name'
    case 'size_bytes':
      return 'size'
    case 'created_at':
    default:
      return 'created_at'
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
      group_id:
        selectedGroupId.value === '__NO_GROUP__'
          ? '' // backend interprets empty string as "IS NULL"
          : selectedGroupId.value || null,
      sort: mapSortField(activeSort.id),
      dir: mapSortDir(activeSort.desc),
      page: pagination.value.pageIndex + 1,
      page_size: pagination.value.pageSize,
      group_sort: 'none'
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

/** ---------- React to state changes ---------- **/
watch(
  [sorting, () => pagination.value.pageIndex, () => pagination.value.pageSize],
  () => debouncedFetch(),
  { deep: true }
)

watch(filenameQuery, () => {
  pagination.value.pageIndex = 0
  debouncedFetch()
})

watch(selectedGroupId, () => {
  pagination.value.pageIndex = 0
  debouncedFetch()
})

function handleGroupMenuOpen(open: boolean) {
  if (open && !groups.value.length) refreshGroups()
}

onMounted(() => {
  refreshGroups()
  fetchFiles()
})

/** ---------- Utils ---------- **/
function formatSize(n?: number | null) {
  if (n == null) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let v = n
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`
}
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
function getRowId(row: FileItem) {
  return row.doc_id
}
</script>



<template>
  <div class="flex-1 w-full">
    <!-- Toolbar -->
    <div class="flex items-center gap-2 px-4 py-3.5 border-b border-accented overflow-x-auto">
      <UInput
        v-model="filenameQuery"
        class="max-w-sm min-w-[16ch]"
        placeholder="Search filename…"
        icon="i-heroicons-magnifying-glass-20-solid"
      />

      <USelectMenu
        v-model="selectedGroupId"
        :items="selectOptions"
        value-key="value"
        placeholder="Filter by group…"
        :loading="loadingGroups"
        :search-input="{ placeholder: 'Search groups…' }"
        icon="i-lucide-users"
        class="w-64"
        @update:open="handleGroupMenuOpen"
      >
        <template #empty>
          <span class="text-muted">No groups found</span>
        </template>
      </USelectMenu>

      

      <div class="ms-auto flex items-center gap-3 text-sm text-muted">
        <span v-if="!pending">Total: {{ total.toLocaleString() }}</span>
        <span v-else>Loading…</span>

        <!-- Column visibility menu -->
        <UDropdownMenu
          :items="table?.tableApi?.getAllColumns().filter(c => c.getCanHide()).map(c => ({
            label: c.id,
            type: 'checkbox' as const,
            checked: c.getIsVisible(),
            onUpdateChecked(checked: boolean) { table?.tableApi?.getColumn(c.id)?.toggleVisibility(!!checked) },
            onSelect(e?: Event) { e?.preventDefault() }
          }))"
          :content="{ align: 'end' }"
        >
          <UButton
            label="Columns"
            color="neutral"
            variant="outline"
            trailing-icon="i-lucide-chevron-down"
          />
        </UDropdownMenu>
      </div>
    </div>

    <!-- Table -->
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
      :state="{ pagination, sorting }"
      :onStateChange="() => {}"
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

    <!-- Footer -->
    <div class="flex items-center justify-between px-4 py-3.5 border-t border-accented text-sm text-muted">
      <div>
        Page {{ pagination.pageIndex + 1 }} •
        Showing {{ data.length }} / {{ total.toLocaleString() }}
      </div>
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
  </div>
</template>
