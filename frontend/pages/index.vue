<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { ButtonProps } from '@nuxt/ui'
import type { DocumentItem } from '@/composables/useDocuments'
import FileGrid from '@/components/FileGrid.vue'
import ResultList from '@/components/ResultList.vue'
import BodyCard from '@/components/BodyCard.vue'
import { demoConfig } from '@/data/demo-config'

/* -----------------------------
   Hero section buttons
--------------------------------*/
const heroButtons: ButtonProps[] = [
  { label: 'Login', to: '/login', icon: 'i-lucide-log-in', color: 'primary' },
  { label: 'View Demo', to: '/demo', variant: 'outline', trailingIcon: 'i-lucide-arrow-right' }
]

/* -----------------------------
   Typing animation setup
--------------------------------*/
const displayText = ref("")
const typingSpeed = 80
const pauseBetween = 15000 // 15 seconds to view results
const deletingSpeed = 40

/* -----------------------------
   Demo configuration (imported)
--------------------------------*/
const phrases = demoConfig.phrases
const demoThumbnailUrls = demoConfig.thumbnailUrls
const fakeDataSets = demoConfig.dataSets

/* -----------------------------
   Results state
--------------------------------*/
const showResults = ref(false)
const loading = ref(false)
const viewMode = ref<'grid' | 'list'>('grid')
const filenameMatches = ref<DocumentItem[]>([])
const chunks = ref<any[]>([])

onMounted(() => {
  let phraseIndex = 0
  let charIndex = 0
  let isDeleting = false

  function typeLoop() {
    const currentPhrase = phrases[phraseIndex] ?? ""

    if (!isDeleting) {
      displayText.value = currentPhrase.slice(0, charIndex + 1)
      charIndex++

      if (charIndex === currentPhrase.length) {
        // show loading skeletons
        loading.value = true
        showResults.value = false

        // delay before showing results
        setTimeout(() => {
          const dataSet = fakeDataSets[phraseIndex]
          filenameMatches.value = dataSet?.files ?? []
          chunks.value = dataSet?.chunks ?? []
          loading.value = false
          showResults.value = true
        }, 500)

        // after pauseBetween, start deleting
        setTimeout(() => { isDeleting = true; typeLoop() }, pauseBetween)
        return
      }
    } else {
      displayText.value = currentPhrase.slice(0, charIndex - 1)
      charIndex--

      if (charIndex === 0) {
        isDeleting = false
        phraseIndex = (phraseIndex + 1) % phrases.length
      }
    }

    setTimeout(typeLoop, isDeleting ? deletingSpeed : typingSpeed)
  }

  typeLoop()
})

// Dummy file open handler
function handleOpenFile(file: DocumentItem) {
  console.log('Demo: Would open file', file.filename)
}
</script>

<template>
  <!-- Hero section -->
  <div class="hero-bg">
    <UPageHero
      title="Cloud Based Semantic File Explorer"
      description="Use our Semantic Search technology and our agentic natural-language tools to find what you need, when you need it."
      headline="New Features Released"
    >
      <template #links>
        <div class="button-box">
          <UButton
            v-for="(btn, i) in heroButtons"
            :key="i"
            v-bind="btn"
            class="m-2"
          />
        </div>
      </template>
    </UPageHero>
  </div>

  <!-- Typing + Results -->
  <div class="first-divider">
    <UInput
      v-model="displayText"
      readonly
      size="xl"
      class="typing-box"
      placeholder="Ask me anything…"
    />

    <!-- Loading Skeletons -->
    <BodyCard v-if="loading" class="results-container glass-bg">
      <div class="py-8">
        <!-- Skeleton Files Section -->
        <div class="space-y-8">
          <div class="space-y-3">
            <div class="flex items-center justify-between mb-3 px-2">
              <div class="flex items-center gap-2">
                <USkeleton class="w-5 h-5 rounded" />
                <USkeleton class="w-32 h-6 rounded" />
                <USkeleton class="w-8 h-5 rounded" />
              </div>
              <USkeleton class="w-20 h-8 rounded-lg" />
            </div>
            <!-- Grid of skeleton file cards -->
            <div class="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
              <div v-for="i in 4" :key="i" class="space-y-3">
                <USkeleton class="w-full h-32 rounded-lg" />
                <USkeleton class="w-3/4 h-4 rounded" />
                <USkeleton class="w-1/2 h-3 rounded" />
              </div>
            </div>
          </div>
        </div>

        <!-- Skeleton Chunks Section -->
        <div class="space-y-8 mt-8">
          <div class="border-t border-foreground/10 my-4" />
          <div class="space-y-3">
            <div class="flex items-center gap-2 px-2">
              <USkeleton class="w-5 h-5 rounded" />
              <USkeleton class="w-40 h-6 rounded" />
              <USkeleton class="w-8 h-5 rounded" />
            </div>
            <!-- Grid of skeleton result cards -->
            <div class="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
              <div v-for="i in 3" :key="i">
                <UCard class="flex flex-col">
                  <template #header>
                    <div class="flex items-center justify-between w-full">
                      <USkeleton class="w-48 h-5 rounded" />
                      <USkeleton class="w-16 h-7 rounded" />
                    </div>
                  </template>
                  <div class="space-y-3">
                    <USkeleton class="w-24 h-4 rounded" />
                    <div class="h-px bg-foreground/10" />
                    <USkeleton class="w-full h-40 rounded-lg" />
                    <USkeleton class="w-full h-4 rounded" />
                    <USkeleton class="w-5/6 h-4 rounded" />
                    <USkeleton class="w-4/6 h-4 rounded" />
                  </div>
                </UCard>
              </div>
            </div>
          </div>
        </div>
      </div>
    </BodyCard>

    <!-- Actual Results -->
    <BodyCard v-if="showResults" class="results-container glass-bg">
      <div class="py-8">
        <!-- Filename Matches Section -->
        <div v-if="filenameMatches.length > 0" class="space-y-8">
          <div class="space-y-3">
            <div class="flex items-center justify-between mb-3 px-2">
              <div class="flex items-center gap-2">
                <UIcon name="i-heroicons-document-text" class="w-5 h-5" />
                <h2 class="text-lg font-semibold">Matching Files</h2>
                <span class="text-sm text-foreground/60">({{ filenameMatches.length }})</span>
              </div>
              <div class="flex gap-1 bg-neutral-800/50 rounded-lg p-1">
                <UButton
                  icon="i-heroicons-squares-2x2"
                  :variant="viewMode === 'grid' ? 'solid' : 'ghost'"
                  :color="viewMode === 'grid' ? 'primary' : 'neutral'"
                  size="sm"
                  @click="viewMode = 'grid'"
                  aria-label="Grid view"
                />
                <UButton
                  icon="i-heroicons-list-bullet"
                  :variant="viewMode === 'list' ? 'solid' : 'ghost'"
                  :color="viewMode === 'list' ? 'primary' : 'neutral'"
                  size="sm"
                  @click="viewMode = 'list'"
                  aria-label="List view"
                />
              </div>
            </div>
            <FileGrid
              :files="filenameMatches"
              :loading="false"
              :enable-hover-preview="false"
              :view-mode="viewMode"
              :provided-thumbnail-urls="demoThumbnailUrls"
              @open-file="handleOpenFile"
            />
          </div>
        </div>

        <!-- Chunks Section -->
        <div v-if="chunks.length > 0" class="space-y-8">
          <div v-if="filenameMatches.length > 0" class="border-t border-foreground/10 my-4" />
          <div class="space-y-3">
            <div class="flex items-center gap-2 px-2">
              <UIcon name="i-heroicons-sparkles" class="w-5 h-5" />
              <h2 class="text-lg font-semibold">Relevant Content</h2>
              <span class="text-sm text-foreground/60">({{ chunks.length }})</span>
            </div>
            <ResultList :results="chunks" :disable-actions="true" />
          </div>
        </div>

        <!-- Empty State -->
        <div
          v-if="!filenameMatches.length && !chunks.length"
          class="text-center py-12 text-foreground/50"
        >
          <UIcon name="i-heroicons-folder-open" class="w-12 h-12 mx-auto mb-4" />
          <p class="text-lg">No results found</p>
        </div>
      </div>
    </BodyCard>
  </div>
  
  <h1 class="supported-title">Supported File Types</h1>

<BodyCard class="static-footer">
  <UMarquee pause-on-hover :overlay="false" :ui="{ root: '[--gap:0.5rem]' }" :repeat="6">
    <span class="file-type">TXT</span>
    <span class="file-type">PDF</span>
    <span class="file-type">DOCX</span>
    <span class="file-type">JPEG</span>
    <span class="file-type">PNG</span>
    <span class="file-type">PPT</span>
    <span class="file-type">MP4</span>
  </UMarquee>
</BodyCard>

<!-- Footer -->
<footer class="page-footer">
  <div class="footer-content">
    <div class="footer-section">
      <p>&copy; 2026 SmartQuery Ltd. All rights reserved.</p>
    </div>
    <div class="footer-links">
      <NuxtLink to="/privacy" class="footer-link">Privacy Policy</NuxtLink>
      <span class="footer-divider">•</span>
      <NuxtLink to="/terms" class="footer-link">Terms of Service</NuxtLink>
    </div>
  </div>
</footer>

</template>

<style scoped>

.supported-title {
  text-align: center;      /* centers text horizontally */
  font-size: 3rem;         /* make it large */
  font-weight: 700;        /* bold */
  margin-bottom: 1rem;     /* space between title and card */
  margin-top: 2rem;        /* space above the title */
  color: white;            /* adjust to fit your theme */
}

.static-footer {
  /* size of the card */
          /* or max-width: 400px */
  height: 80px;

  

  /* card styling */
  display: flex;
  align-items: center;
  justify-content: center;

  background: #222;
  color: white;
  border-radius: 0.75rem;
}


.static-footer {
  border-top: 1px solid rgba(255,255,255,0.1);
  box-shadow: 0 -2px 6px rgba(0,0,0,0.3);
}



.hero-bg {
  background: url('/indexbackground.jpg') no-repeat center center / cover;
  background-size: cover;
  background-position: center;
  min-height: 70vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  position: relative;
}

.hero-bg::before {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0.35);
  z-index: 0;
}

.hero-bg > * {
  position: relative;
  z-index: 1;
}

.button-box {
  display: inline-flex;
  gap: 1rem;
  background: rgba(0,0,0,0.8);
  padding: 0.75rem 1rem;
  border-radius: 1rem;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}

.first-divider {
  min-height: 100vh;
  background-color: black;
  color: white;
  padding: 3rem 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2rem;
}

.typing-box {
  width: 100%;
  max-width: 600px;
  font-size: 1.25rem;
}

.results-container {
  width: 100%;
  max-width: 1200px;
  margin: 2rem auto;
  height: 1150px;
  overflow-y: auto; /* Scrollable if content exceeds height */
  overflow-x: hidden;
}

.glass-bg {
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

/* Footer styles */
.page-footer {
  background-color: #1a1a1a;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding: 2rem;
  color: white;
}

.footer-content {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  text-align: center;
}

.footer-section p {
  margin: 0;
  font-size: 0.875rem;
  color: #999;
}

.footer-links {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.footer-link {
  color: #60a5fa;
  text-decoration: none;
  transition: color 0.2s;
}

.footer-link:hover {
  color: #93c5fd;
  text-decoration: underline;
}

.footer-divider {
  color: #666;
}
</style>


