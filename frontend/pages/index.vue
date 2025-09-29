<script setup lang="ts">
import type { ButtonProps } from '@nuxt/ui'

const links: ButtonProps[] = [
  {
    label: 'Login',
    to: '/login',
    icon: 'i-lucide-log-in',
    color: 'primary'
  },
  {
    label: 'View Demo',
    to: '/demo',
    variant: 'outline',
    trailingIcon: 'i-lucide-arrow-right'
  }
]
</script>

<template>
  <UPageHero
    title="The Ultimate Smart Search Platform"
    description="Use our Semantic Search technology and our agentic natural-language tools to find what you need when you need it."
    headline="New Features Released"
    :links="links"
  />
</template>
