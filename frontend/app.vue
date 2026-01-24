<script setup lang="ts">
import Header from './components/header.vue';

</script>

<template>
  <UApp>
    <Header />
    <NuxtPage />   <!-- renders pages/index.vue or whatever route -->
  </UApp>
</template>
