import type { DocumentItem } from '@/composables/useDocuments'

/**
 * Demo Configuration File
 *
 * Edit this file to customize the demo on the home page.
 * You can modify:
 * - Search phrases that get typed
 * - Thumbnail image URLs
 * - Fake files and their metadata
 * - Fake content chunks
 */

export interface DemoDataSet {
  files: DocumentItem[]
  chunks: any[]
}

export interface DemoConfig {
  phrases: string[]
  thumbnailUrls: Record<string, string>
  dataSets: DemoDataSet[]
}

export const demoConfig: DemoConfig = {
  // Phrases that will be typed in sequence
  phrases: [
    "my holiday to edinburgh",
    "pdf file about the porsche 911",
    "my old ginger cat joe",
    "find research notes on AI agents"
  ],

  // Thumbnail URLs from public folder
  // Key should match the file ID in dataSets
  thumbnailUrls: {
    'demo-1': '/temp_vid.jpg',
    'demo-2': '/xyz.jpg',
    'demo-edinburgh-video': '/2025-05-11temp.jpg',
    'demo-5': '/cute.jpg',
    'demo-6': '/kitty.jpg'
  },

  // Data sets - one for each phrase
  // Each set contains files and/or chunks that match the search
  dataSets: [
    // Query 1: Holiday photos to Edinburgh
    {
      files: [
        {
          id: 'demo-1',
          user_id: 'demo-user',
          filename: '2025-05-11temp.jpg',
          mime_type: 'image/jpeg',
          file_size_bytes: 1024000,
          status: 'ready' as const,
          chunk_count: 1,
          page_count: null,
          group_id: null,
          group_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ragie_document_id: 'demo-1'
        },
        {
          id: 'demo-2',
          user_id: 'demo-user',
          filename: 'xyz.jpg',
          mime_type: 'image/jpeg',
          file_size_bytes: 892000,
          status: 'ready' as const,
          chunk_count: 1,
          page_count: null,
          group_id: null,
          group_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ragie_document_id: 'demo-2'
        },
        {
          id: 'demo-edinburgh-video',
          user_id: 'demo-user',
          filename: 'scotland-castle.mp4',
          mime_type: 'video/mp4',
          file_size_bytes: 45678000,
          status: 'ready' as const,
          chunk_count: 1,
          page_count: null,
          group_id: null,
          group_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ragie_document_id: 'demo-edinburgh-video'
        }
      ],
      chunks: [
        {
          id: 'chunk-edinburgh-video',
          score: 0.92,
          metadata: {
            title: 'scotland-castle.mp4',
            chunk_content_type: 'video',
            document_id: 'demo-edinburgh-video',
            chunk_id: 'chunk-edinburgh-video',
            bucket: 'videos',
            storage_path: 'demo/city_castle.mp4',
            mime_type: 'video/mp4',
            start_time: 585,
            thumbnail_signed_url: '/2025-05-11temp.jpg',
            audio_transcript: 'Audio Transcription: Walking up to this Scottish Castle on a beautiful sunny day in May. The historic fortress sits majestically atop Castle Rock, overlooking the city. You can hear the sounds of tourists chatting and the breeze rustling through the trees.',
            video_description: 'Steadicam footage walking up the cobblestone path toward a Castle. The medieval stone walls and towers are prominent against a clear blue sky. Several tourists can be seen exploring the castle grounds. The Scottish flag flies proudly from the highest tower.'
          }
        }
      ]
    },

    // Query 2: Porsche 911 PDF
    {
      files: [
        {
          id: 'demo-3',
          user_id: 'demo-user',
          filename: '123.pdf',
          mime_type: 'application/pdf',
          file_size_bytes: 2048000,
          status: 'ready' as const,
          chunk_count: 42,
          page_count: 15,
          group_id: null,
          group_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ragie_document_id: 'demo-3'
        },
        {
          id: 'demo-4',
          user_id: 'demo-user',
          filename: 'turbo-history.pdf',
          mime_type: 'application/pdf',
          file_size_bytes: 1536000,
          status: 'ready' as const,
          chunk_count: 28,
          page_count: 8,
          group_id: null,
          group_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ragie_document_id: 'demo-4'
        }
      ],
      chunks: [
        {
          id: 'chunk-1',
          score: 0.88,
          metadata: {
            title: '123.pdf',
            text: `This iconic Stuttgart sports car features a distinctive rear-engine layout with a twin-turbocharged flat-six. Active suspension, rear-axle steering, and adaptive aerodynamics.

**Base Carrera:** 379 hp, 0-60 in 4.0s, manual or PDK
**Carrera S:** 443 hp, 0-60 in 3.3s, coupe/cabriolet/Targa
**4S Models:** AWD variants with wider rear fenders`,
            document_id: 'demo-3',
            chunk_id: 'chunk-1',
            modality: 'text',
            mime_type: 'application/pdf'
          }
        },
        {
          id: 'chunk-2',
          score: 0.91,
          metadata: {
            title: 'turbo-history.pdf',
            text: `The Turbo lineage started in 1975 with the legendary 930 'widowmaker'. Today's 3.8L twin-turbo flat-six delivers up to 640 hp with variable-geometry turbos and AWD.

**Turbo S:** 640 hp, 0-60 in 2.6s, 205+ mph, deployable rear wing
**GT3:** 502 hp naturally aspirated 4.0L, RWD, track-focused aero
**GT3 RS:** 518 hp race-bred, PDK-only, maximum downforce
**GTS:** 473 hp middle ground, 0-60 in 3.1s, RWD or AWD`,
            document_id: 'demo-4',
            chunk_id: 'chunk-2',
            modality: 'text',
            mime_type: 'application/pdf'
          }
        }
      ]
    },

    // Query 3: Ginger cat
    {
      files: [
        {
          id: 'demo-5',
          user_id: 'demo-user',
          filename: 'cute.jpg',
          mime_type: 'image/jpeg',
          file_size_bytes: 756000,
          status: 'ready' as const,
          chunk_count: 1,
          page_count: null,
          group_id: null,
          group_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ragie_document_id: 'demo-5'
        },
        {
          id: 'demo-6',
          user_id: 'demo-user',
          filename: 'kitty.jpg',
          mime_type: 'image/jpeg',
          file_size_bytes: 612000,
          status: 'ready' as const,
          chunk_count: 1,
          page_count: null,
          group_id: null,
          group_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ragie_document_id: 'demo-6'
        },
        {
          id: 'demo-8',
          user_id: 'demo-user',
          filename: 'vet-report.pdf',
          mime_type: 'application/pdf',
          file_size_bytes: 145000,
          status: 'ready' as const,
          chunk_count: 3,
          page_count: 2,
          group_id: null,
          group_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ragie_document_id: 'demo-8'
        },
        {
          id: 'demo-9',
          user_id: 'demo-user',
          filename: 'proof_of_ownership.txt',
          mime_type: 'text/plain',
          file_size_bytes: 8400,
          status: 'ready' as const,
          chunk_count: 1,
          page_count: null,
          group_id: null,
          group_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ragie_document_id: 'demo-9'
        }
      ],
      chunks: [
        {
          id: 'chunk-5',
          score: 0.85,
          metadata: {
            title: 'vet-report.pdf',
            text: `VETERINARY EXAM - March 15, 2024

Feline (Domestic Shorthair) | Ginger Tabby | 8 years | 4.2 kg

Annual checkup revealed healthy, well-nourished orange male with bright amber eyes and characteristic tabby markings. Excellent coat condition, minimal dental tartar. Heart/lungs normal. Body condition 5/9 (ideal).

Vaccinations: FVRCP booster, Rabies booster

Senior feline in excellent health. Schedule dental cleaning within 6 months.

Dr. Sarah Mitchell, DVM`,
            document_id: 'demo-8',
            chunk_id: 'chunk-5',
            modality: 'text',
            mime_type: 'application/pdf'
          }
        },
        {
          id: 'chunk-6',
          score: 0.91,
          metadata: {
            title: 'proof_of_ownership.txt',
            text: `OWNERSHIP CERTIFICATE - January 10, 2025

Orange tabby male in my care since June 2016. Adopted from shelter as 8-week kitten.

Distinguishing marks: White chest patch, pink nose, M-shaped forehead marking
Microchip: 982000123456789 | Neutered Aug 2016

Senior indoor/outdoor feline, friendly and affectionate. Enjoys sunny windowsills and cardboard boxes. Greets visitors at door with distinctive chirping meow.

Veterinary: Greenfield Clinic since 2016, all vaccinations current.`,
            document_id: 'demo-9',
            chunk_id: 'chunk-6',
            modality: 'text',
            mime_type: 'text/plain'
          }
        }
      ]
    },

    // Query 4: AI agents research
    {
      files: [
        {
          id: 'demo-7',
          user_id: 'demo-user',
          filename: 'workdoc.pdf',
          mime_type: 'application/pdf',
          file_size_bytes: 3072000,
          status: 'ready' as const,
          chunk_count: 156,
          page_count: 42,
          group_id: null,
          group_name: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ragie_document_id: 'demo-7'
        }
      ],
      chunks: [
        {
          id: 'chunk-3',
          score: 0.81,
          metadata: {
            title: 'workdoc.pdf',
            text: `AI agents use LLMs with tools and memory to break down complex tasks into steps. They observe, plan, and act iteratively, using APIs and databases to augment their capabilities. Key advances include RAG integration, long-term memory, and multi-agent coordination.`,
            document_id: 'demo-7',
            chunk_id: 'chunk-3',
            modality: 'text',
            mime_type: 'application/pdf'
          }
        },
        {
          id: 'chunk-4',
          score: 0.79,
          metadata: {
            title: 'workdoc.pdf',
            text: `Modern AI agents select and invoke tools—APIs, databases, code execution—through a decision loop. Frameworks like LangChain and AutoGen manage tool schemas and agent communication. Multi-agent systems coordinate specialized agents for complex workflows, requiring robust state management and clear delegation.`,
            document_id: 'demo-7',
            chunk_id: 'chunk-4',
            modality: 'text',
            mime_type: 'application/pdf'
          }
        }
      ]
    }
  ]
}
