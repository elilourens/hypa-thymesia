"""
Cleanup script to remove orphaned vectors from ALL Pinecone indexes.

Orphaned vectors are those whose corresponding records no longer exist in Supabase:
- Text chunks: chunk_id not in app_chunks or doc_id not in app_doc_meta
- Image chunks: chunk_id not in app_chunks or doc_id not in app_doc_meta
- Extracted images: chunk_id not in app_chunks or doc_id not in app_doc_meta
- Video frames: video_id (doc_id) not in app_doc_meta
- Video transcripts: video_id (doc_id) not in app_doc_meta

Usage:
    python scripts/cleanup_orphaned_pinecone.py --dry-run    # Preview what would be deleted
    python scripts/cleanup_orphaned_pinecone.py              # Actually delete orphaned vectors
    python scripts/cleanup_orphaned_pinecone.py --text-only  # Only cleanup text index
    python scripts/cleanup_orphaned_pinecone.py --images-only # Only cleanup image indexes
    python scripts/cleanup_orphaned_pinecone.py --video-only  # Only cleanup video indexes
"""
import os
import sys
import argparse
from typing import Set, List, Dict, Any
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from pinecone import Pinecone
from supabase import create_client

# Initialize clients
PINECONE_KEY = os.getenv("PINECONE_API_KEY") or os.getenv("PINECONE_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

if not PINECONE_KEY:
    raise RuntimeError("Missing PINECONE_API_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY")

pc = Pinecone(api_key=PINECONE_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Index names from environment
TEXT_INDEX_NAME = os.getenv("PINECONE_TEXT_INDEX_NAME")
IMAGE_INDEX_NAME = os.getenv("PINECONE_IMAGE_INDEX_NAME")
EXTRACTED_IMAGE_INDEX_NAME = os.getenv("PINECONE_EXTRACTED_IMAGE_INDEX_NAME")
VIDEO_FRAME_INDEX_NAME = os.getenv("PINECONE_VIDEO_FRAME_INDEX_NAME", "video-frames")
VIDEO_TRANSCRIPT_INDEX_NAME = os.getenv("PINECONE_VIDEO_TRANSCRIPT_INDEX_NAME", "video-transcripts")


def get_valid_doc_ids() -> Set[str]:
    """Get all valid document IDs from Supabase app_doc_meta."""
    print("Fetching valid document IDs from app_doc_meta...")

    all_ids = set()
    page_size = 1000
    offset = 0

    while True:
        response = supabase.table("app_doc_meta").select("doc_id").range(offset, offset + page_size - 1).execute()
        if not response.data:
            break
        for row in response.data:
            all_ids.add(row["doc_id"])
        if len(response.data) < page_size:
            break
        offset += page_size

    print(f"  Found {len(all_ids)} valid documents")
    return all_ids


def get_valid_chunk_ids() -> Set[str]:
    """Get all valid chunk IDs from Supabase app_chunks."""
    print("Fetching valid chunk IDs from app_chunks...")

    all_ids = set()
    page_size = 1000
    offset = 0

    while True:
        response = supabase.table("app_chunks").select("chunk_id").range(offset, offset + page_size - 1).execute()
        if not response.data:
            break
        for row in response.data:
            all_ids.add(row["chunk_id"])
        if len(response.data) < page_size:
            break
        offset += page_size

    print(f"  Found {len(all_ids)} valid chunks")
    return all_ids


def get_valid_video_ids() -> Set[str]:
    """Get all valid video document IDs from Supabase."""
    print("Fetching valid video IDs from app_doc_meta...")

    all_ids = set()
    page_size = 1000
    offset = 0

    while True:
        response = supabase.table("app_doc_meta").select("doc_id").eq("modality", "video").range(offset, offset + page_size - 1).execute()
        if not response.data:
            break
        for row in response.data:
            all_ids.add(row["doc_id"])
        if len(response.data) < page_size:
            break
        offset += page_size

    print(f"  Found {len(all_ids)} valid video documents")
    return all_ids


def list_all_pinecone_vectors(index_name: str, limit_per_namespace: int = None) -> List[Dict[str, Any]]:
    """List all vectors from a Pinecone index with their metadata."""
    print(f"Fetching vectors from Pinecone index '{index_name}'...")

    try:
        index = pc.Index(index_name)
    except Exception as e:
        print(f"  Warning: Could not connect to index '{index_name}': {e}")
        return []

    all_vectors = []

    # Get index stats to find all namespaces
    try:
        stats = index.describe_index_stats()
    except Exception as e:
        print(f"  Error getting index stats: {e}")
        return []

    namespaces = list(stats.get("namespaces", {}).keys())

    if not namespaces:
        namespaces = [""]  # Default namespace

    print(f"  Found {len(namespaces)} namespaces")

    for namespace in namespaces:
        ns_display = namespace or "(default)"
        print(f"  Processing namespace: '{ns_display}'...")

        try:
            # Use list operation to get all vector IDs in namespace
            vector_ids = []
            for ids_batch in index.list(namespace=namespace):
                vector_ids.extend(ids_batch)
                if limit_per_namespace and len(vector_ids) >= limit_per_namespace:
                    vector_ids = vector_ids[:limit_per_namespace]
                    break

            if not vector_ids:
                print(f"    No vectors in namespace")
                continue

            print(f"    Found {len(vector_ids)} vector IDs")

            # Fetch vectors in batches to get metadata
            batch_size = 100
            for i in range(0, len(vector_ids), batch_size):
                batch_ids = vector_ids[i:i + batch_size]
                fetch_response = index.fetch(ids=batch_ids, namespace=namespace)

                for vec_id, vec_data in fetch_response.vectors.items():
                    all_vectors.append({
                        "id": vec_id,
                        "namespace": namespace,
                        "metadata": vec_data.metadata or {},
                    })

        except Exception as e:
            print(f"    Error processing namespace '{ns_display}': {e}")
            continue

    print(f"  Total vectors fetched: {len(all_vectors)}")
    return all_vectors


def find_orphaned_chunk_vectors(
    vectors: List[Dict[str, Any]],
    valid_doc_ids: Set[str],
    valid_chunk_ids: Set[str],
) -> List[Dict[str, Any]]:
    """Find vectors whose chunk_id or doc_id no longer exists in Supabase."""
    orphaned = []

    for vec in vectors:
        metadata = vec["metadata"]

        # Extract chunk_id from vector ID (format: {chunk_id}:{version})
        vec_id = vec["id"]
        chunk_id = vec_id.split(":")[0] if ":" in vec_id else vec_id

        # Also check metadata
        meta_chunk_id = metadata.get("chunk_id", chunk_id)
        doc_id = metadata.get("doc_id")

        is_orphaned = False
        reasons = []

        # Check if chunk exists
        if meta_chunk_id and meta_chunk_id not in valid_chunk_ids:
            is_orphaned = True
            reasons.append(f"chunk_id '{meta_chunk_id[:8]}...' not in app_chunks")

        # Check if document exists
        if doc_id and doc_id not in valid_doc_ids:
            is_orphaned = True
            reasons.append(f"doc_id '{doc_id[:8]}...' not in app_doc_meta")

        if is_orphaned:
            vec["orphan_reason"] = "; ".join(reasons)
            orphaned.append(vec)

    return orphaned


def find_orphaned_video_vectors(
    vectors: List[Dict[str, Any]],
    valid_video_ids: Set[str],
) -> List[Dict[str, Any]]:
    """Find video vectors whose video_id (doc_id) no longer exists in Supabase."""
    orphaned = []

    for vec in vectors:
        metadata = vec["metadata"]
        video_id = metadata.get("video_id") or metadata.get("doc_id")

        if video_id and video_id not in valid_video_ids:
            vec["orphan_reason"] = f"video_id '{video_id[:8]}...' not in app_doc_meta"
            orphaned.append(vec)

    return orphaned


def delete_vectors(index_name: str, vectors: List[Dict[str, Any]], dry_run: bool = True):
    """Delete orphaned vectors from Pinecone."""
    if not vectors:
        print("  No vectors to delete.")
        return 0

    # Group by namespace
    by_namespace: Dict[str, List[str]] = defaultdict(list)
    for vec in vectors:
        by_namespace[vec["namespace"]].append(vec["id"])

    index = pc.Index(index_name)
    total_deleted = 0

    for namespace, ids in by_namespace.items():
        ns_display = namespace or "(default)"
        if dry_run:
            print(f"  [DRY RUN] Would delete {len(ids)} vectors from namespace '{ns_display}'")
        else:
            print(f"  Deleting {len(ids)} vectors from namespace '{ns_display}'...")
            # Delete in batches
            batch_size = 100
            for i in range(0, len(ids), batch_size):
                batch = ids[i:i + batch_size]
                index.delete(ids=batch, namespace=namespace)
            print(f"    Deleted {len(ids)} vectors")
        total_deleted += len(ids)

    return total_deleted


def print_sample_orphans(orphaned: List[Dict[str, Any]], max_show: int = 10):
    """Print a sample of orphaned vectors."""
    if not orphaned:
        return

    print(f"\n  Sample orphaned vectors (showing {min(len(orphaned), max_show)} of {len(orphaned)}):")
    for vec in orphaned[:max_show]:
        vec_id_short = vec['id'][:40] + "..." if len(vec['id']) > 40 else vec['id']
        print(f"    - {vec_id_short}")
        print(f"      Reason: {vec['orphan_reason']}")

    if len(orphaned) > max_show:
        print(f"    ... and {len(orphaned) - max_show} more")


def process_text_index(valid_doc_ids: Set[str], valid_chunk_ids: Set[str], dry_run: bool) -> Dict[str, int]:
    """Process text index for orphaned vectors."""
    print("\n" + "=" * 60)
    print("PROCESSING TEXT INDEX")
    print("=" * 60)

    if not TEXT_INDEX_NAME:
        print("  Skipping: PINECONE_TEXT_INDEX_NAME not configured")
        return {"found": 0, "deleted": 0}

    vectors = list_all_pinecone_vectors(TEXT_INDEX_NAME)
    if not vectors:
        return {"found": 0, "deleted": 0}

    orphaned = find_orphaned_chunk_vectors(vectors, valid_doc_ids, valid_chunk_ids)
    print(f"\n  Found {len(orphaned)} orphaned text vectors (out of {len(vectors)} total)")

    print_sample_orphans(orphaned)

    if orphaned:
        print()
        deleted = delete_vectors(TEXT_INDEX_NAME, orphaned, dry_run=dry_run)
        return {"found": len(orphaned), "deleted": deleted if not dry_run else 0}

    return {"found": 0, "deleted": 0}


def process_image_index(valid_doc_ids: Set[str], valid_chunk_ids: Set[str], dry_run: bool) -> Dict[str, int]:
    """Process image index for orphaned vectors."""
    print("\n" + "=" * 60)
    print("PROCESSING IMAGE INDEX")
    print("=" * 60)

    if not IMAGE_INDEX_NAME:
        print("  Skipping: PINECONE_IMAGE_INDEX_NAME not configured")
        return {"found": 0, "deleted": 0}

    vectors = list_all_pinecone_vectors(IMAGE_INDEX_NAME)
    if not vectors:
        return {"found": 0, "deleted": 0}

    orphaned = find_orphaned_chunk_vectors(vectors, valid_doc_ids, valid_chunk_ids)
    print(f"\n  Found {len(orphaned)} orphaned image vectors (out of {len(vectors)} total)")

    print_sample_orphans(orphaned)

    if orphaned:
        print()
        deleted = delete_vectors(IMAGE_INDEX_NAME, orphaned, dry_run=dry_run)
        return {"found": len(orphaned), "deleted": deleted if not dry_run else 0}

    return {"found": 0, "deleted": 0}


def process_extracted_image_index(valid_doc_ids: Set[str], valid_chunk_ids: Set[str], dry_run: bool) -> Dict[str, int]:
    """Process extracted image index for orphaned vectors."""
    print("\n" + "=" * 60)
    print("PROCESSING EXTRACTED IMAGE INDEX")
    print("=" * 60)

    if not EXTRACTED_IMAGE_INDEX_NAME:
        print("  Skipping: PINECONE_EXTRACTED_IMAGE_INDEX_NAME not configured")
        return {"found": 0, "deleted": 0}

    vectors = list_all_pinecone_vectors(EXTRACTED_IMAGE_INDEX_NAME)
    if not vectors:
        return {"found": 0, "deleted": 0}

    orphaned = find_orphaned_chunk_vectors(vectors, valid_doc_ids, valid_chunk_ids)
    print(f"\n  Found {len(orphaned)} orphaned extracted image vectors (out of {len(vectors)} total)")

    print_sample_orphans(orphaned)

    if orphaned:
        print()
        deleted = delete_vectors(EXTRACTED_IMAGE_INDEX_NAME, orphaned, dry_run=dry_run)
        return {"found": len(orphaned), "deleted": deleted if not dry_run else 0}

    return {"found": 0, "deleted": 0}


def process_video_frame_index(valid_video_ids: Set[str], dry_run: bool) -> Dict[str, int]:
    """Process video frame index for orphaned vectors."""
    print("\n" + "=" * 60)
    print("PROCESSING VIDEO FRAME INDEX")
    print("=" * 60)

    if not VIDEO_FRAME_INDEX_NAME:
        print("  Skipping: PINECONE_VIDEO_FRAME_INDEX_NAME not configured")
        return {"found": 0, "deleted": 0}

    vectors = list_all_pinecone_vectors(VIDEO_FRAME_INDEX_NAME)
    if not vectors:
        return {"found": 0, "deleted": 0}

    orphaned = find_orphaned_video_vectors(vectors, valid_video_ids)
    print(f"\n  Found {len(orphaned)} orphaned video frame vectors (out of {len(vectors)} total)")

    print_sample_orphans(orphaned)

    if orphaned:
        print()
        deleted = delete_vectors(VIDEO_FRAME_INDEX_NAME, orphaned, dry_run=dry_run)
        return {"found": len(orphaned), "deleted": deleted if not dry_run else 0}

    return {"found": 0, "deleted": 0}


def process_video_transcript_index(valid_video_ids: Set[str], dry_run: bool) -> Dict[str, int]:
    """Process video transcript index for orphaned vectors."""
    print("\n" + "=" * 60)
    print("PROCESSING VIDEO TRANSCRIPT INDEX")
    print("=" * 60)

    if not VIDEO_TRANSCRIPT_INDEX_NAME:
        print("  Skipping: PINECONE_VIDEO_TRANSCRIPT_INDEX_NAME not configured")
        return {"found": 0, "deleted": 0}

    vectors = list_all_pinecone_vectors(VIDEO_TRANSCRIPT_INDEX_NAME)
    if not vectors:
        return {"found": 0, "deleted": 0}

    orphaned = find_orphaned_video_vectors(vectors, valid_video_ids)
    print(f"\n  Found {len(orphaned)} orphaned video transcript vectors (out of {len(vectors)} total)")

    print_sample_orphans(orphaned)

    if orphaned:
        print()
        deleted = delete_vectors(VIDEO_TRANSCRIPT_INDEX_NAME, orphaned, dry_run=dry_run)
        return {"found": len(orphaned), "deleted": deleted if not dry_run else 0}

    return {"found": 0, "deleted": 0}


def main():
    parser = argparse.ArgumentParser(description="Cleanup orphaned vectors from Pinecone indexes")
    parser.add_argument("--dry-run", action="store_true", help="Preview deletions without actually deleting")
    parser.add_argument("--text-only", action="store_true", help="Only cleanup text index")
    parser.add_argument("--images-only", action="store_true", help="Only cleanup image indexes (image + extracted)")
    parser.add_argument("--video-only", action="store_true", help="Only cleanup video indexes (frames + transcripts)")
    args = parser.parse_args()

    # Determine which indexes to process
    process_all = not (args.text_only or args.images_only or args.video_only)
    do_text = process_all or args.text_only
    do_images = process_all or args.images_only
    do_video = process_all or args.video_only

    print("=" * 60)
    print("PINECONE ORPHAN CLEANUP")
    print("=" * 60)

    if args.dry_run:
        print("\n*** DRY RUN MODE - No vectors will be deleted ***\n")

    # Fetch valid IDs from Supabase
    valid_doc_ids = set()
    valid_chunk_ids = set()
    valid_video_ids = set()

    if do_text or do_images:
        valid_doc_ids = get_valid_doc_ids()
        valid_chunk_ids = get_valid_chunk_ids()

    if do_video:
        valid_video_ids = get_valid_video_ids()

    # Track results
    results = {}

    # Process each index type
    if do_text:
        results["text"] = process_text_index(valid_doc_ids, valid_chunk_ids, args.dry_run)

    if do_images:
        results["image"] = process_image_index(valid_doc_ids, valid_chunk_ids, args.dry_run)
        results["extracted_image"] = process_extracted_image_index(valid_doc_ids, valid_chunk_ids, args.dry_run)

    if do_video:
        results["video_frame"] = process_video_frame_index(valid_video_ids, args.dry_run)
        results["video_transcript"] = process_video_transcript_index(valid_video_ids, args.dry_run)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_found = 0
    total_deleted = 0

    for index_type, counts in results.items():
        found = counts["found"]
        deleted = counts["deleted"]
        total_found += found
        total_deleted += deleted

        if found > 0:
            if args.dry_run:
                print(f"  {index_type}: {found} orphaned vectors found (would delete)")
            else:
                print(f"  {index_type}: {found} orphaned vectors found, {deleted} deleted")
        else:
            print(f"  {index_type}: No orphaned vectors")

    print()
    print(f"Total orphaned vectors: {total_found}")

    if args.dry_run and total_found > 0:
        print("\n*** This was a dry run. Run without --dry-run to actually delete vectors. ***")
    elif total_deleted > 0:
        print(f"Total vectors deleted: {total_deleted}")

    print("\n" + "=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
