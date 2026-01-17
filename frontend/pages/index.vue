<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { ButtonProps } from '@nuxt/ui'

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
const phrases: string[] = [
  "show me my holiday photos to edinburgh",
  "pdf file about the porsche 911",
  "my old ginger cat joe",
  "find research notes on AI agents"
]



const displayText = ref("")
const typingSpeed = 80
const pauseBetween = 7000
const deletingSpeed = 40

/* -----------------------------
   Fake results – fully hard-coded
--------------------------------*/
interface FakeResult {
  id: number
  score: number
  title: string
  fileName: string
  type: 'image' | 'text'
  text?: string
  src?: string
}

const results = ref<FakeResult[]>([])       // always an array
const showResults = ref(false)

// Hard-coded sample data
const fakeDataSets: FakeResult[][] = [
  [
    {
      id: 1,
      score: 0.92,
      title: '',
      fileName: '2025-05-11temp.jpg',
      type: 'image',
      src: '/2025-05-11temp.jpg'
    },
    {
      id: 2,
      score: 0.85,
      title: '',
      fileName: 'xyz.jpg',
      type: 'image',
      src: '/xyz.jpg'
    }
  ],
  [
    {
      id: 1,
      score: 0.88,
      title: 'Porsche 911 PDF preview',
      fileName: '123.pdf',
      type: 'text',
      text: "The Porsche 911 is a rear-engined sports car first introduced in 1964 and still regarded as an icon of performance engineering. The modern 911 Carrera uses a 3.0-liter twin-turbocharged flat-six producing up to 379 hp and 331 lb-ft of torque, with the Carrera S reaching 443 hp. Most models use an eight-speed PDK dual-clutch gearbox for rapid shifts, while a seven-speed manual remains available on select trims. The car’s 0-60 mph time ranges from 4.0 s to just 2.8 s for the Turbo S, thanks to launch control and all-wheel-drive traction. The 911 features Porsche Active Suspension Management, adaptive dampers, optional rear-axle steering, and advanced aerodynamics including an automatically extending rear spoiler for high-speed stability. Its timeless silhouette, precise steering feel, and heritage as both a road car and endurance-racing champion have made the 911 one of the most celebrated sports cars in automotive history."
    },
    {
      id: 2,
      score: 0.91,
      title: 'Porsche 911 Turbo Evolution',
      fileName: 'turbo-history.pdf',
      type: 'text',
      text: "The Porsche 911 Turbo lineage began in 1975 with the legendary 930, notable for its dramatic turbo lag and iconic wide rear fenders. Over decades the Turbo evolved into a sophisticated high-performance machine, now using a 3.8-liter twin-turbo flat-six producing up to 640 hp in the current Turbo S. Porsche refined turbocharging to deliver seamless power and instant torque while retaining everyday usability. Modern Turbos include advanced all-wheel drive, variable-geometry turbos, and active aerodynamics such as a two-stage rear wing and adaptive front splitter. With a 0-60 mph time as low as 2.6 s and a top speed exceeding 200 mph, the 911 Turbo combines supercar acceleration with grand-touring comfort and remains a benchmark for performance coupes worldwide."
    }
  ],
  [
    {
      id: 1,
      score: 0.95,
      title: '',
      fileName: 'cute.jpg',
      type: 'image',
      src: '/cute.jpg'
    },
    {
      id: 2,
      score: 0.93,
      title: '',
      fileName: 'kitty.jpg',
      type: 'image',
      src: '/kitty.jpg'
    }
  ],
  [
    {
      id: 1,
      score: 0.81,
      title: 'LLM-Based Agentic Architectures',
      fileName: 'workdoc.pdf',
      type: 'text',
      text: `Agentic architectures leverage large language models (LLMs) as the core reasoning and planning component within a broader system of tools, memory, and environment interaction. These agents are designed to autonomously decompose complex tasks, invoke external APIs, and maintain context over extended interactions. A typical LLM agent includes a planning module, a set of tool-use policies, and a memory or scratchpad for intermediate results. The agent receives a user goal, breaks it into actionable steps, and iteratively executes them, often using a loop of observation, planning, and action. Key challenges include managing context window limitations, ensuring reliable tool invocation, and handling ambiguous or underspecified instructions. Recent advances focus on integrating vector databases for long-term memory, using retrieval-augmented generation (RAG) to ground responses, and orchestrating multiple agents for collaborative problem-solving.`
    },
    {
      id: 2,
      score: 0.79,
      title: 'Tool Use and Orchestration',
      fileName: 'workdoc.pdf',
      type: 'text',
      text: `A defining feature of modern AI agents is their ability to use external tools—APIs, databases, web browsers, or code execution environments—to augment their capabilities beyond pure language modeling. Tool use is typically orchestrated through a decision-making loop, where the agent selects the most appropriate tool for a given subtask, formulates the input, and interprets the output. This process can be single-step (reactive) or multi-step (reflective), with the latter allowing for more sophisticated reasoning and error correction. Orchestration frameworks like LangChain, AutoGen, and CrewAI provide abstractions for defining tool schemas, agent roles, and communication protocols. Multi-agent systems can coordinate specialized agents (e.g., a researcher, coder, and critic) to tackle complex workflows. Effective orchestration requires robust state management, clear delegation of responsibilities, and mechanisms for conflict resolution or consensus-building among agents.`
    }
  ]
]


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
        // hide results first
        showResults.value = false

        // delay before showing results
        setTimeout(() => {
          results.value = fakeDataSets[phraseIndex] ?? []   // always array
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
</script>

<template>
  <!-- Hero section -->
  <div class="hero-bg">
    <UPageHero
      title="The Ultimate Smart Search Platform"
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

    <div v-if="showResults" class="results-grid">
      <UCard
        v-for="r in results"
        :key="r.id"
        class="flex flex-col justify-between bg-neutral-900 text-white"
      >
        <div class="flex-1 space-y-2">
          <!-- Score -->
          <p class="text-xs text-gray-400">
            Score: {{ (r.score * 100).toFixed(1) }}%
          </p>

          <!-- File row -->
          <div class="flex items-center justify-between text-xs text-gray-400">
            <span>File: <strong>{{ r.fileName }}</strong></span>

            <UButton
             
              :to="r.src"
              target="_blank"
              rel="noopener noreferrer"
              size="xs"
              color="primary"
              variant="soft"
              icon="i-heroicons-eye"
            >
              Open
            </UButton>
          </div>

          <USeparator orientation="horizontal" class="h-auto self-stretch" size="lg" />

          <!-- Text or Image -->
          <p v-if="r.type === 'text'">{{ r.text }}</p>

          <div v-else-if="r.type === 'image'">
            <img
              :src="r.src"
              :alt="r.title"
              class="object-contain mx-auto p-2 rounded"
            />
            <p class="text-center text-sm mt-2">{{ r.title }}</p>
          </div>
        </div>
      </UCard>
    </div>

    
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
  background: url('/indexbackground.jpg') no-repeat center bottom / cover;
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

/* --- Results Grid: horizontal layout --- */
.results-grid {
  width: 100%;
  max-width: 1000px;
  margin-left: auto;
  margin-right: auto;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 1.2rem;
  justify-items: stretch;
  align-items: stretch;
}

/* Horizontal card layout */
.results-grid .u-card {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 1rem;
  padding: 1.5rem 1.25rem;
  background: #1a1a1a;
  min-height: 220px;
  border-radius: 0.75rem;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}

/* Make image cards display image and content side by side on wide screens */
.results-grid .u-card:has(img) {
  flex-direction: column;
  align-items: stretch;
}

/* Image on the left, now larger */
.results-grid img {
  width: 100%;
  height: 240px;
  object-fit: cover;
  border-radius: 0.5rem;
  display: block;
  margin-left: 0;
  margin-right: 0;
}

/* Content on the right */
.results-grid .flex-1 {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
</style>


