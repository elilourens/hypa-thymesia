<script setup lang="ts">
import { ref, computed, onMounted, h, resolveComponent } from 'vue'   
import type { TableColumn } from '@nuxt/ui'
import { useGroupsApi, type Group } from '@/composables/useGroups'
import BodyCard from '@/components/BodyCard.vue';

const { listGroups, createGroup, deleteGroup } = useGroupsApi()

const UButton = resolveComponent('UButton')
const UInput = resolveComponent('UInput')
const UDropdownMenu = resolveComponent('UDropdownMenu')
const UBadge = resolveComponent('UBadge')

const groups = ref<Group[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const newName = ref('')
const newSortIndex = ref<number | null>(0)
const creating = ref(false)

const deletingIds = ref<Set<string>>(new Set())
const toast = useToast()

const sorted = computed(() =>
  [...groups.value].sort(
    (a, b) =>
      (a.sort_index ?? 0) - (b.sort_index ?? 0) ||
      (a.name || '').localeCompare(b.name || '')
  )
)

async function refresh() {
  loading.value = true
  error.value = null
  try {
    groups.value = await listGroups()
  } catch (e: any) {
    error.value = e?.message || 'Failed to load groups'
  } finally {
    loading.value = false
  }
}

async function onCreate() {
  const name = newName.value.trim()
  if (!name) {
    toast.add({ title: 'Enter a group name', color: 'warning', icon: 'i-lucide-alert-triangle' })
    return
  }
  creating.value = true
  try {
    const g = await createGroup(name, Number.isFinite(newSortIndex.value ?? NaN) ? (newSortIndex.value as number) : 0)
    groups.value = [g, ...groups.value]
    newName.value = ''
    // keep current sort_index for next create; no reset
    toast.add({ title: 'Group created', color: 'success', icon: 'i-lucide-check' })
  } catch (e: any) {
    toast.add({ title: e?.message ?? 'Create failed', color: 'error', icon: 'i-lucide-alert-triangle' })
  } finally {
    creating.value = false
  }
}

async function onDelete(id: string) {
  if (!confirm('Delete this group? Docs will be left ungrouped.')) return
  deletingIds.value.add(id)
  try {
    await deleteGroup(id)
    const before = groups.value.length
    groups.value = groups.value.filter(g => g.id !== id)
    if (before && groups.value.length === 0) {
      await refresh()
    }
    toast.add({ title: 'Group deleted', color: 'success', icon: 'i-lucide-trash-2' })
  } catch (e: any) {
    toast.add({ title: e?.message ?? 'Delete failed', color: 'error', icon: 'i-lucide-alert-triangle' })
  } finally {
    deletingIds.value.delete(id)
  }
}

onMounted(refresh)

/** ---------- Table ---------- **/
const columns: TableColumn<Group>[] = [
  {
    accessorKey: 'name',
    header: 'Name',
    cell: ({ row }) => row.original.name || '(unnamed)'
  },
  {
    accessorKey: 'sort_index',
    header: 'Order',
    cell: ({ row }) =>
      h(UBadge, { variant: 'subtle' }, () => String(row.original.sort_index ?? 0))
  },
  {
    accessorKey: 'created_at',
    header: 'Created',
    cell: ({ row }) => {
      const d = new Date(row.original.created_at)
      return new Intl.DateTimeFormat(undefined, {
        year: 'numeric', month: 'short', day: '2-digit',
        hour: '2-digit', minute: '2-digit'
      }).format(d)
    }
  },
  {
    id: 'actions',
    enableHiding: false,
    cell: ({ row }) => {
      const id = row.original.id
      const items = [
        { type: 'label', label: 'Actions' },
        {
          label: deletingIds.value.has(id) ? 'Deleting…' : 'Delete',
          disabled: deletingIds.value.has(id),
          icon: 'i-lucide-trash-2',
          onSelect: () => onDelete(id)
        }
      ]
      return h(
        UDropdownMenu,
        { items, content: { align: 'end' } },
        () => h(UButton, {
          icon: 'i-lucide-ellipsis-vertical',
          color: 'neutral',
          variant: 'ghost',
          'aria-label': 'Actions'
        })
      )
    }
  }
]
</script>

<template>
  <BodyCard>
    <div class=" w-full mx-auto">
      <div class="flex items-center justify-between px-4 py-4">
        <h1 class="text-lg font-semibold">Groups</h1>
        <div class="text-sm text-muted">
          Total: {{ groups.length.toLocaleString() }}
        </div>
      </div>

      <!-- Create -->
      <div class="px-4 pb-4">
        <div class="flex flex-wrap items-center gap-2">
          <UInput
            v-model="newName"
            placeholder="New group name…"
            class="w-64"
          />
          <UInput
            v-model.number="newSortIndex"
            type="number"
            placeholder="Order (sort_index)"
            class="w-40"
          />
          <UButton
            :loading="creating"
            :disabled="creating || !newName.trim()"
            icon="i-lucide-plus"
            @click="onCreate"
          >
            Create group
          </UButton>
        </div>
        <p class="mt-2 text-xs text-muted">
          Groups are ordered by <code>sort_index</code> then name.
        </p>
      </div>

      <!-- List -->
      <UTable
        :data="sorted"
        :columns="columns"
        :loading="loading"
        sticky
        empty="No groups yet."
        :ui="{ root: 'min-w-full', td: 'whitespace-nowrap' }"
        class="px-2"
      >
        <template #loading>
          <div class="py-6 text-sm px-4">Loading groups…</div>
        </template>
        <template #empty>
          <div class="py-6 text-sm px-4">No groups yet. Create your first one above.</div>
        </template>
      </UTable>

      <UAlert
        v-if="error"
        icon="i-heroicons-exclamation-triangle"
        color="error"
        :title="error"
        variant="subtle"
        class="mx-4 my-4"
      />
    </div>
  </BodyCard>
  
</template>
