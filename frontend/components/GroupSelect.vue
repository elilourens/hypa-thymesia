<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useGroupsCache } from '@/composables/useGroupsCache'
import { NO_GROUP_VALUE } from '@/composables/useGroups'

const props = defineProps<{
  modelValue: string | null
  includeAll?: boolean
  includeNoGroup?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | null): void
}>()

const { groups, fetchGroups } = useGroupsCache()

const options = computed(() => {
  const base: { label: string; value: string | null; color?: string }[] = []
  if (props.includeAll) base.push({ label: 'All groups', value: null })
  if (props.includeNoGroup) base.push({ label: 'No Group', value: NO_GROUP_VALUE })
  return base.concat(groups.value.map(g => ({
    label: g.name ?? '(unnamed)',
    value: g.id,
    color: g.color
  })))
})

onMounted(() => fetchGroups())
</script>

<template>
  <USelectMenu
    :model-value="props.modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    :items="options"
    value-key="value"
    :placeholder="props.placeholder ?? 'Select group…'"
    :search-input="{ placeholder: 'Search groups…' }"
    icon="i-lucide-users"
    class="w-72"
  >
    <template #item="{ item }">
      <div class="flex items-center gap-2 w-full">
        <div
          v-if="item.color"
          class="w-3 h-3 rounded-full flex-shrink-0"
          :style="{ backgroundColor: item.color }"
        />
        <span class="truncate">{{ item.label }}</span>
      </div>
    </template>
    <template #empty>
      <span class="text-muted">No groups found</span>
    </template>
  </USelectMenu>
</template>
