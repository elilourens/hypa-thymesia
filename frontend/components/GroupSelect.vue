<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useGroupsApi, type Group, NO_GROUP_VALUE } from '@/composables/useGroups'

const props = defineProps<{
  modelValue: string | null
  includeAll?: boolean
  includeNoGroup?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | null): void
}>()

const { listGroups } = useGroupsApi()
const groups = ref<Group[]>([])
const loading = ref(false)

const sortedGroups = computed(() =>
  [...groups.value].sort(
    (a, b) =>
      (a.sort_index ?? 0) - (b.sort_index ?? 0) ||
      a.name.localeCompare(b.name)
  )
)

const options = computed(() => {
  const base: { label: string; value: string | null }[] = []
  if (props.includeAll) base.push({ label: 'All groups', value: null })
  if (props.includeNoGroup) base.push({ label: 'No Group', value: NO_GROUP_VALUE })
  return base.concat(sortedGroups.value.map(g => ({
    label: g.name ?? '(unnamed)',
    value: g.id
  })))
})

async function refresh() {
  loading.value = true
  try {
    groups.value = await listGroups()
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="flex items-center gap-2">
    <USelectMenu
      :model-value="props.modelValue"
      @update:model-value="emit('update:modelValue', $event)"
      :items="options"
      value-key="value"
      :placeholder="props.placeholder ?? 'Select group…'"
      :loading="loading"
      :search-input="{ placeholder: 'Search groups…' }"
      icon="i-lucide-users"
      class="w-72"
      @update:open="(open) => { if (open && !groups.length) refresh() }"
    >
      <template #empty>
        <span class="text-muted">No groups found</span>
      </template>
    </USelectMenu>
    <UButton variant="ghost" :disabled="loading" @click="refresh">
      {{ loading ? 'Refreshing…' : 'Refresh' }}
    </UButton>
  </div>
</template>
