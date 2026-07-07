"""
data/batch_embed.py
One-shot batch embedding script — run once after seed data is loaded
to populate all embedding columns in candidates and jobs tables.

Also processes any PDF/DOCX files in data/uploads/training/
to create candidate records from real resumes.

Usage:
    python -m data.batch_embed               # embed seeded data only
    python -m data.batch_embed --training    # also parse training resumes
    python -m data.batch_embed --force       # re-embed everything
"""
import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def embed_seed_data(force: bool = False):
    """Embed all seeded candidates and jobs."""
    from ml.embedder import embed_all_candidates, embed_all_jobs

    print("\n── Embedding candidates ──────────────────────────")
    n_candidates = embed_all_candidates(force=force)
    print(f"✅ Embedded {n_candidates} candidates")

    print("\n── Embedding jobs ────────────────────────────────")
    n_jobs = embed_all_jobs(force=force)
    print(f"✅ Embedded {n_jobs} jobs")

    return n_candidates, n_jobs


def process_training_resumes():
    """
    Parse all PDFs/DOCXs in data/uploads/training/ and
    create candidate records in the database.
    """
    from data.file_store import list_training_files
    from ml.parser import parse_resume_file
    from db.queries import create_candidate
    from db.models import VisaStatusEnum

    files = list_training_files()
    if not files:
        print("\n⚠️  No training files found in data/uploads/training/")
        print("   Drop PDF or DOCX resumes there and re-run with --training")
        return 0

    print(f"\n── Processing {len(files)} training resumes ──────────")
    created = 0

    for file_path in files:
        try:
            print(f"  Parsing: {Path(file_path).name}")
            result = parse_resume_file(file_path)

            # Map visa string to enum
            visa_map = {v.value: v for v in VisaStatusEnum}
            visa = visa_map.get(result["visa_status"], VisaStatusEnum.unknown)

            candidate_id = create_candidate({
                "name":         result["name"],
                "email":        result.get("email"),
                "phone":        result.get("phone"),
                "skills":       result["skills"],
                "visa_status":  visa,
                "yoe":          result["yoe"],
                "resume_path":  file_path,
                "resume_text":  result["raw_text"],
            })
            print(f"    ✅ Created candidate #{candidate_id}: {result['name']}")
            created += 1

        except Exception as e:
            print(f"    ❌ Failed to parse {file_path}: {e}")

    return created


def main():
    parser = argparse.ArgumentParser(description="Batch embed candidates and jobs")
    parser.add_argument("--training", action="store_true",
                        help="Also parse and import training resumes")
    parser.add_argument("--force", action="store_true",
                        help="Re-embed even records that already have embeddings")
    args = parser.parse_args()

    print("🧠 Staffing Intelligence Platform — Batch Embedder")
    print("=" * 52)

    if args.training:
        n_training = process_training_resumes()
        print(f"\n📄 Imported {n_training} candidates from training resumes")

    n_candidates, n_jobs = embed_seed_data(force=args.force)

    print("\n" + "=" * 52)
    print("✅ Batch embedding complete:")
    print(f"   {n_candidates} candidates embedded")
    print(f"   {n_jobs} jobs embedded")
    print("\nRun the matching engine next: Sprint 4")


if __name__ == "__main__":
    main()
