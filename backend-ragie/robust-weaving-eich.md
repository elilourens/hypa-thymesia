# Video Storage Migration Plan: Ragie → Supabase Hybrid

## Overview
Migrate from Ragie-hosted video streaming to Supabase storage while keeping Ragie for video analysis (transcription, descriptions, timestamps). This reduces streaming costs by ~85-90%.

---

## Architecture

### Current State (Ragie-Only)
```
User Uploads Video
    ↓
Ragie (stores + processes + streams)
    ↓
Query returns: transcript, description, timestamps
    ↓
User clicks "Play" → Stream from Ragie ($0.001/MB)
```

### Target State (Supabase + Ragie Hybrid)
```
User Uploads Video
    ↓
Supabase Storage (store original)
    ↓
Send to Ragie for Processing (transcription/analysis only)
    ↓
Store Ragie metadata (transcript, description, timestamps) in Supabase DB
    ↓
Query returns: transcript, description, timestamps, supabase_storage_path
    ↓
User clicks "Play" → Stream from Supabase ($0.09/GB vs $1.00/GB)
```

---

## Key Features to Implement

### 1. **Smart Video Streaming with Timestamp Seeking**

**Problem:** Videos can be hours long, but user only wants to watch a 15-30 second chunk

**Solution:** HTTP Range Requests + Browser Caching
- Use HTML5 video element with `currentTime` property
- Browser automatically sends `Range` headers to fetch only needed bytes
- Start playback at Ragie's `start_time` timestamp
- Allow user to seek forward/backward (browser handles partial downloads)

**How it works:**
```javascript
// User clicks "Play from 45 seconds"
videoPlayer.currentTime = 45  // Sets timestamp

// Browser automatically requests:
// GET /video.mp4
// Range: bytes=5242880-  (roughly 45 seconds worth of bytes)

// Supabase responds with:
// 206 Partial Content
// Content-Range: bytes 5242880-67108864/67108864
// (Only sends from 45s onwards, not the whole file)
```

**User Experience:**
- Click "Play" on chunk at 45-60s → Video starts at 45s
- User can scrub timeline forward/backward
- Browser only downloads segments being watched
- Seeking backwards? Browser may re-request earlier bytes (small cost)

---

### 2. **Browser Caching Strategy**

**Goal:** Don't re-download videos users have already watched

**Implementation:**
- Supabase signed URLs with long TTL (e.g., 3600s = 1 hour)
- Browser HTTP cache headers (`Cache-Control: public, max-age=3600`)
- Service Worker cache (optional, for offline viewing)
- LocalStorage to track "recently watched" videos

**Cache Layers:**
```
Level 1: Browser Memory Cache (current session)
    ↓ (on next visit)
Level 2: Browser Disk Cache (persists across sessions)
    ↓ (optional)
Level 3: Service Worker Cache (offline-first PWA)
```

**Expected Savings:**
- First view: Full download cost
- Repeat views (same session): $0 (cached)
- Repeat views (different day): $0 if within cache TTL

---

### 3. **Result List UI Update**

**Current:** Shows transcript text for video chunks

**New Design:**
```
┌────────────────────────────────────────────┐
│ [Aberdeenshire News Video]           [Open]│
├────────────────────────────────────────────┤
│ Score: 17.1%                               │
├────────────────────────────────────────────┤
│ ┌──────────────────────────────┐           │
│ │  [Thumbnail or video poster] │           │
│ │  📹 0:45 - 1:00 (15 seconds) │           │
│ └──────────────────────────────┘           │
│                                            │
│ 💬 Transcript:                             │
│ "It's been very busy. I've been 16 years   │
│  as a community first responder and these  │
│  are the worst conditions..."              │
│                                            │
│ 📝 Description:                            │
│ Two men standing in snow. One wearing      │
│ green/yellow jacket (first responder)...   │
│                                            │
│ [▶ Play from 0:45]                         │
└────────────────────────────────────────────┘
```

**Elements:**
- Thumbnail (optional): First frame at `start_time`
- Time badge: Shows chunk duration
- Transcript: Audio text from Ragie
- Description: Visual description from Ragie
- Play button: Opens video modal starting at `start_time`

---

### 4. **Video Player Modal Behavior**

**When user clicks "Play from 0:45":**
1. Open modal with video player
2. Fetch signed URL from Supabase Storage
3. Set `<video>` element:
   - `src` = Supabase signed URL
   - `currentTime` = 45 (starts at 45 seconds)
   - `autoplay` = true
4. Video loads and plays from 45s onwards
5. User can seek anywhere in the video timeline

**Bandwidth Optimization:**
- Browser sends `Range` header based on `currentTime`
- Only downloads from 45s onwards (not 0-45s)
- If user seeks backward to 30s, browser requests bytes for 30-45s
- If user seeks forward to 90s, browser requests bytes for 60-90s

**Example:**
- Video file: 67 MB total (152 seconds)
- User plays from 45s to 60s (watches 15 seconds)
- Download: ~7 MB (not 67 MB)
- Savings: 90% bandwidth

---

## Data Flow

### Upload Flow
```
1. User uploads video.mp4 (4 GB)
2. Frontend → Supabase Storage API
3. Get storage_path: "videos/abc123.mp4"
4. Frontend → Backend: Send for Ragie processing
5. Backend → Ragie API: Process video (transcription + analysis)
6. Ragie returns: 10 chunks with transcripts, timestamps, descriptions
7. Backend → Supabase DB: Store chunks with metadata
   {
     chunk_id: 1,
     video_id: "abc123",
     storage_path: "videos/abc123.mp4",
     bucket: "videos",
     start_time: 30,
     end_time: 45,
     transcript: "...",
     description: "...",
     thumbnail_url: "thumbnails/abc123_30s.jpg" (optional)
   }
```

### Query Flow
```
1. User searches "aberdeen snow"
2. Query Ragie semantic search
3. Ragie returns scored chunks with metadata
4. Frontend receives chunks with:
   - transcript
   - description
   - start_time, end_time
   - storage_path (Supabase, not Ragie!)
5. Render ResultList with chunks
6. User clicks "Play from 0:45"
7. Frontend → Supabase: Get signed URL for storage_path
8. Open modal, set video.currentTime = 45
9. Browser requests video from Supabase (Range: bytes=...)
10. Video streams from 45s onwards
```

---

## Cost Analysis (100 Users, 400GB)

### Ragie Processing (One-Time)
- 250 hours × 60 min × $0.025/min = **$360**

### Supabase Monthly Costs

**Storage:**
- 400 GB - 100 GB free = 300 GB overage
- 300 × $0.021/GB = **$6.30/month**

**Egress (3 views/user average):**
- 100 users × 4 GB × 3 views = 1,200 GB total
- 1,200 GB - 250 GB free = 950 GB billable
- 950 × $0.09/GB = **$85.50/month**

**With Browser Caching (30% cache hit rate):**
- 1,200 GB × 70% = 840 GB total
- 840 GB - 250 GB free = 590 GB billable
- 590 × $0.09/GB = **$53.10/month**

**Total Monthly: $25 (Pro) + $6.30 + $53.10 = $84.40**

---

## Implementation Phases

### Phase 1: Video Upload to Supabase
- Update upload flow to store videos in Supabase Storage
- Create `videos` bucket with public access
- Store metadata in `video_metadata` table

### Phase 2: Ragie Integration for Processing
- Send uploaded videos to Ragie for analysis
- Store returned chunks in database
- Link chunks to Supabase storage paths

### Phase 3: Update ResultList Component
- Detect Ragie video chunks (`chunk_content_type: 'video'`)
- Display transcript + description + time badge
- Add "Play" button

### Phase 4: Video Player with Timestamp Seeking
- Update video modal to accept Supabase URLs
- Implement `currentTime` seeking
- Add browser caching headers

### Phase 5: Browser Caching
- Configure Supabase signed URLs with cache headers
- Set appropriate TTL (1-3 hours)
- Optional: Service Worker for offline caching

### Phase 6: Thumbnail Generation (Optional)
- Extract frame at `start_time` during processing
- Upload to Supabase Storage
- Display in ResultList

---

## Technical Considerations

### HTTP Range Requests
- Supabase Storage supports `Range` headers natively
- HTML5 `<video>` automatically uses Range requests
- No custom code needed for partial downloads
- Works seamlessly with `currentTime` seeking

### Video Formats
- Recommend H.264/MP4 (universal browser support)
- Enable "faststart" flag (moov atom at beginning for seeking)
- Consider transcoding on upload if not already optimized

### Signed URL Management
- TTL: 3600s (1 hour) balances security vs caching
- Generate on-demand (not pre-generated)
- Cache in frontend state to avoid repeated DB calls

### Browser Cache Headers
- Supabase automatically sets `Cache-Control` headers
- Public signed URLs are cacheable
- Browser will reuse downloaded segments

---

## Open Questions

1. **Thumbnail Generation:**
   - Generate server-side during Ragie processing?
   - Generate client-side on first view?
   - Skip thumbnails and just show transcript?

2. **Video Quality:**
   - Allow users to upload any format and transcode?
   - Require H.264/MP4 upload only?
   - Support multiple quality levels (360p, 720p, 1080p)?

3. **Ragie Integration:**
   - Send public Supabase URL to Ragie for processing?
   - Or upload to Ragie, process, then delete from Ragie?
   - How to track processing status (async job)?

4. **Database Schema:**
   - Extend existing tables or create new video-specific tables?
   - Store chunks as JSON array or separate rows?

---

## Success Metrics

- ✅ 85-90% reduction in streaming costs
- ✅ Videos start playing within 2 seconds
- ✅ Seeking works smoothly (no full re-download)
- ✅ Browser cache hits reduce bandwidth by 30%+
- ✅ Users can watch full video from any chunk
- ✅ Transcripts/descriptions display instantly

---

## Next Steps

1. Review this plan and clarify open questions
2. Explore codebase to understand current video handling
3. Design database schema for video metadata + chunks
4. Create detailed implementation plan with file changes
5. Begin implementation phase by phase
