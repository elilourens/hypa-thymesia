<script setup lang="ts">
import { ref, reactive, onMounted, h, resolveComponent } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { useGroupsApi, type Group } from '@/composables/useGroups'
import BodyCard from '@/components/BodyCard.vue';

const { listGroups, createGroup, deleteGroup } = useGroupsApi()

const UButton = resolveComponent('UButton')
const UInput = resolveComponent('UInput')

const groups = ref<Group[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const pagination = reactive({ pageIndex: 0, pageSize: 15 })

const newName = ref('')
const creating = ref(false)

const deletingIds = ref<Set<string>>(new Set())
const toast = useToast()

async function refresh() {
  loading.value = true
  error.value = null
  try {
    const allGroups = await listGroups()
    total.value = allGroups.length
    // Simple client-side pagination for groups
    const start = pagination.pageIndex * pagination.pageSize
    groups.value = allGroups.slice(start, start + pagination.pageSize)
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
    await createGroup(name)
    newName.value = ''
    pagination.pageIndex = 0
    await refresh()
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
    groups.value = groups.value.filter(g => g.id !== id)
    total.value = Math.max(0, total.value - 1)

    if (groups.value.length === 0 && pagination.pageIndex > 0) {
      pagination.pageIndex -= 1
      await refresh()
    } else {
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
    cell: ({ row }) =>
      h(UButton, {
        color: 'error',
        variant: 'ghost',
        size: 'sm',
        icon: 'i-lucide-trash-2',
        loading: deletingIds.value.has(row.original.id),
        disabled: deletingIds.value.has(row.original.id),
        onClick: () => onDelete(row.original.id),
        'aria-label': 'Delete group'
      })
  }
]
</script>

<template>
  <BodyCard>
    <div class="w-full mx-auto">
      <div class="flex items-center justify-between px-4 py-4">
        <h1 class="text-lg font-semibold">Groups</h1>
        <div class="text-sm text-muted">
          Total: {{ total.toLocaleString() }}
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
          <UButton
            :loading="creating"
            :disabled="creating || !newName.trim()"
            icon="i-lucide-plus"
            @click="onCreate"
          >
            Create group
          </UButton>
        </div>
      </div>

      <!-- List -->
      <UTable
        :data="groups"
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

      <!-- Footer with pagination -->
      <div class="flex items-center justify-between px-4 py-3.5 border-t border-accented text-sm text-muted">
        <div>Page {{ pagination.pageIndex + 1 }} • Showing {{ groups.length }} / {{ total.toLocaleString() }}</div>
        <UPagination
          :default-page="pagination.pageIndex + 1"
          :items-per-page="pagination.pageSize"
          :total="total"
          @update:page="(p: number) => (pagination.pageIndex = p - 1, refresh())"
        />
      </div>

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
