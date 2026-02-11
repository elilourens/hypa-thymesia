<script setup lang="ts">
import { ref, reactive, onMounted, h, resolveComponent, computed } from 'vue'
import type { TableColumn } from '@nuxt/ui'
import { useGroupsApi, type Group } from '@/composables/useGroups'
import BodyCard from '@/components/BodyCard.vue'
import ColorPicker from '@/components/ColorPicker.vue'

const { listGroups, createGroup, deleteGroup, renameGroup } = useGroupsApi()

const UButton = resolveComponent('UButton')
const UInput = resolveComponent('UInput')

const groups = ref<Group[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const pagination = reactive({ pageIndex: 0, pageSize: 15 })

const newName = ref('')
const newColor = ref('#8B5CF6')
const creating = ref(false)

const deletingIds = ref<Set<string>>(new Set())
const toast = useToast()

// Edit state
const editingId = ref<string | null>(null)
const editName = ref('')
const editColor = ref('')
const isUpdating = ref(false)

const isModalOpen = computed({
  get: () => editingId.value !== null,
  set: (value: boolean) => {
    if (!value) closeEditModal()
  }
})

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
    await createGroup(name, 0, newColor.value)
    newName.value = ''
    newColor.value = '#8B5CF6'
    pagination.pageIndex = 0
    await refresh()
    toast.add({ title: 'Group created', color: 'success', icon: 'i-lucide-check' })
  } catch (e: any) {
    toast.add({ title: e?.message ?? 'Create failed', color: 'error', icon: 'i-lucide-alert-triangle' })
  } finally {
    creating.value = false
  }
}

function onEdit(group: Group) {
  editingId.value = group.id
  editName.value = group.name
  editColor.value = group.color
}

function closeEditModal() {
  editingId.value = null
  editName.value = ''
  editColor.value = ''
}

async function onSaveEdit() {
  const name = editName.value.trim()
  if (!name) {
    toast.add({ title: 'Enter a group name', color: 'warning', icon: 'i-lucide-alert-triangle' })
    return
  }
  if (!editingId.value) return

  isUpdating.value = true
  try {
    await renameGroup(editingId.value, name, editColor.value)
    await refresh()
    closeEditModal()
    toast.add({ title: 'Group updated', color: 'success', icon: 'i-lucide-check' })
  } catch (e: any) {
    toast.add({ title: e?.message ?? 'Update failed', color: 'error', icon: 'i-lucide-alert-triangle' })
  } finally {
    isUpdating.value = false
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
    accessorKey: 'color',
    header: 'Color',
    cell: ({ row }) =>
      h('div', { class: 'flex items-center gap-2' }, [
        h('div', {
          class: 'w-5 h-5 rounded-full border border-foreground/20',
          style: { backgroundColor: row.original.color }
        }),
        h('span', { class: 'text-xs font-mono text-foreground/60' }, row.original.color)
      ])
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
      h('div', { class: 'flex gap-2' }, [
        h(UButton, {
          variant: 'ghost',
          size: 'sm',
          icon: 'i-lucide-pencil',
          disabled: isUpdating.value || deletingIds.value.has(row.original.id),
          onClick: () => onEdit(row.original),
          'aria-label': 'Edit group'
        }),
        h(UButton, {
          color: 'error',
          variant: 'ghost',
          size: 'sm',
          icon: 'i-lucide-trash-2',
          loading: deletingIds.value.has(row.original.id),
          disabled: deletingIds.value.has(row.original.id) || isUpdating.value,
          onClick: () => onDelete(row.original.id),
          'aria-label': 'Delete group'
        })
      ])
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
      <div class="px-4 pb-6 border-b border-accented">
        <div class="flex flex-col gap-4">
          <div class="flex flex-wrap items-end gap-2">
            <div class="flex-1 min-w-64">
              <label class="text-xs font-medium text-foreground/70 block mb-1">Group name</label>
              <UInput
                v-model="newName"
                placeholder="New group name…"
                maxlength="30"
                class="w-full"
              />
            </div>
            <UButton
              :loading="creating"
              :disabled="creating || !newName.trim()"
              icon="i-lucide-plus"
              @click="onCreate"
            >
              Create group
            </UButton>
          </div>
          <div class="w-full">
            <ColorPicker v-model="newColor" :disabled="creating" />
          </div>
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

    <!-- Edit Modal -->
    <UModal v-model:open="isModalOpen">
      <template #header>
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">Edit group</h2>
        </div>
      </template>

      <template #body>
        <div class="flex flex-col gap-4">
          <div>
            <label class="text-xs font-medium text-foreground/70 block mb-1">Group name</label>
            <UInput
              v-model="editName"
              placeholder="Group name…"
              maxlength="30"
              class="w-full"
            />
          </div>

          <div>
            <ColorPicker v-model="editColor" :disabled="isUpdating" />
          </div>
        </div>
      </template>

      <template #footer>
        <div class="flex gap-2 justify-end">
          <UButton
            color="gray"
            variant="ghost"
            :disabled="isUpdating"
            @click="closeEditModal"
          >
            Cancel
          </UButton>
          <UButton
            :loading="isUpdating"
            :disabled="isUpdating || !editName.trim()"
            @click="onSaveEdit"
          >
            Save changes
          </UButton>
        </div>
      </template>
    </UModal>
  </BodyCard>
</template>
