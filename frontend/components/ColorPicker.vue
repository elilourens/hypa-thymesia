<script setup lang="ts">
defineProps<{
  modelValue: string
  disabled?: boolean
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()

const colors = [
  '#EF4444', // red
  '#F97316', // orange
  '#F59E0B', // amber
  '#84CC16', // lime
  '#10B981', // emerald
  '#14B8A6', // teal
  '#06B6D4', // cyan
  '#3B82F6', // blue
  '#8B5CF6', // purple (default)
  '#A855F7', // violet
  '#EC4899', // pink
  '#F43F5E', // rose
]
</script>

<template>
  <div class="flex flex-col gap-2">
    <label class="text-xs font-medium text-foreground/70">Color</label>
    <div class="flex flex-wrap gap-1.5">
      <button
        v-for="color in colors"
        :key="color"
        :disabled="disabled"
        class="w-7 h-7 rounded transition-all duration-200 flex items-center justify-center"
        :class="[
          modelValue === color
            ? 'ring-2 ring-foreground/50 shadow-md'
            : 'border border-foreground/10 hover:border-foreground/30',
          disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:scale-110'
        ]"
        :style="{ backgroundColor: color }"
        :aria-label="`Select color ${color}`"
        @click="$emit('update:modelValue', color)"
      >
        <UIcon
          v-if="modelValue === color"
          name="i-lucide-check"
          class="w-3.5 h-3.5 text-white drop-shadow"
        />
      </button>
    </div>
  </div>
</template>
