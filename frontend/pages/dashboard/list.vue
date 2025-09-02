<script setup lang="ts">
import { h, resolveComponent } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import type { SortingState } from '@tanstack/vue-table'
import { useDebounceFn } from '@vueuse/core'
import { useFilesApi, type FileItem, type SortField, type SortDir } from '~/composables/useFiles'

const UButton = resolveComponent('UButton')
const UBadge = resolveComponent('UBadge')
const UCheckbox = resolveComponent('UCheckbox')
const UDropdownMenu = resolveComponent('UDropdownMenu')
const UIcon = resolveComponent('UIcon')

const table = useTemplateRef('table')
const { listFiles } = useFilesApi()
const toast = useToast()

/** ---------- Table state (TanStack-style) ---------- **/
const data = ref<FileItem[]>([])
const total = ref(0)

const sorting = ref<SortingState>([
  { id: 'created_at', desc: true }  // API default
])

const pagination = ref({
  pageIndex: 0,   // 0-based for TanStack
  pageSize: 20
})

// Single global search (server-side)
const globalFilter = ref('')

/** ---------- Columns ---------- **/
function sortHeader(label: string, columnId: string) {
  return ({ column }: any) => {
    const isSorted = column.getIsSorted()
    return h(UButton, {
      color: 'neutral',
      variant: 'ghost',
      label,
      icon: isSorted ? (isSorted === 'asc'
        ? 'i-lucide-arrow-up-narrow-wide'
        : 'i-lucide-arrow-down-wide-narrow') : 'i-lucide-arrow-up-down',
      class: '-mx-2.5',
      onClick: () => column.toggleSorting(isSorted === 'asc')
    })
  }
}

function stripLeadingUuid(name: string) {
  // Remove a leading UUID followed by an underscore
  return name.replace(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/i, '');
}


const columns: TableColumn<FileItem>[] = [
  {
    id: 'select',
    header: ({ table }) => h(UCheckbox, {
      modelValue: table.getIsSomePageRowsSelected() ? 'indeterminate' : table.getIsAllPageRowsSelected(),
      'onUpdate:modelValue': (v: boolean | 'indeterminate') => table.toggleAllPageRowsSelected(!!v),
      'aria-label': 'Select all'
    }),
    cell: ({ row }) => h(UCheckbox, {
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
    cell: ({ row }) => h('div', { class: 'truncate' }, [
        h('div', {
        class: 'font-medium truncate',
        title: row.original.filename, // tooltip with full original name
        }, stripLeadingUuid(row.original.filename)),
        h('div', { class: 'text-xs text-muted truncate' }, row.original.mime_type || '—')
    ])
    },
  {
    accessorKey: 'modality',
    header: 'Modality',
    cell: ({ row }) => h(UBadge, { variant: 'subtle' }, () => row.original.modality || '—')
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
    cell: ({ row }) => h('span', { title: row.original.created_at }, formatDate(row.original.created_at))
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
  { id: 'actions',
    enableHiding: false,
    cell: ({ row }) => {
      const items = [
        { type: 'label', label: 'Actions' },
        {
          label: 'Copy ID',
          onSelect: () => {
            navigator.clipboard?.writeText(row.original.doc_id)
            toast.add({ title: 'ID copied', color: 'success', icon: 'i-lucide-circle-check' })
          }
        }
      ]
      return h('div', { class: 'text-right' }, h(UDropdownMenu, {
        content: { align: 'end' },
        items
      }, () => h(UButton, {
        icon: 'i-lucide-ellipsis-vertical',
        color: 'neutral',
        variant: 'ghost',
        class: 'ml-auto',
        'aria-label': 'Actions'
      })))
    }
  }
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
      q: globalFilter.value || null,
      sort: mapSortField(activeSort.id),
      dir: mapSortDir(activeSort.desc),
      page: pagination.value.pageIndex + 1,   // API is 1-based
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
watch([sorting, () => pagination.value.pageIndex, () => pagination.value.pageSize], () => {
  debouncedFetch()
}, { deep: true })

watch(globalFilter, () => {
  // Reset to page 0 when changing search
  pagination.value.pageIndex = 0
  debouncedFetch()
})

onMounted(() => {
  fetchFiles()
})

/** ---------- Utils ---------- **/
function formatSize(n?: number | null) {
  if (n == null) return '—'
  const u = ['B','KB','MB','GB','TB']
  let i = 0; let v = n
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`
}
function formatDate(iso: string) {
  const d = new Date(iso)
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  }).format(d)
}

/** Optional: make row ids stable for selection/expansion */
function getRowId(row: FileItem) { return row.doc_id }
</script>

<template>
  <div class="flex-1 w-full">
    <!-- Toolbar -->
    <div class="flex items-center gap-2 px-4 py-3.5 border-b border-accented overflow-x-auto">
      <UInput
        v-model="globalFilter"
        class="max-w-sm min-w-[16ch]"
        placeholder="Search filename, MIME, group…"
        icon="i-heroicons-magnifying-glass-20-solid"
      />

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
      :state="{   /* wire server state but do NOT add client-side models (no getPaginationRowModel) */
        pagination, sorting, globalFilter
      }"
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

    <!-- Footer: external pagination control (drives server fetch) -->
    <div class="flex items-center justify-between px-4 py-3.5 border-t border-accented text-sm text-muted">
      <div>
        Page {{ pagination.pageIndex + 1 }} •
        Showing {{ data.length }} / {{ total.toLocaleString() }}
      </div>
      <UPagination
        :default-page="pagination.pageIndex + 1"
        :items-per-page="pagination.pageSize"
        :total="total"
        @update:page="(p: number) => pagination.pageIndex = p - 1"
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
