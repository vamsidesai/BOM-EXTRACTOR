"""Seed initial sample drawings if database is empty."""
from __future__ import annotations

import logging
from pathlib import Path
from .storage import storage
from .services.pipeline_service import run_extraction_sync

log = logging.getLogger(__name__)


def seed_sample_drawings():
    existing = storage.list_drawings()
    if existing:
        return

    base_dir = Path(__file__).resolve().parents[1]
    samples = [
        base_dir / "tests" / "data" / "gearbox_casing_legacy.png",
        base_dir / "tests" / "data" / "legacy" / "legacy_drawing_4.pdf",
    ]

    for sample in samples:
        if sample.exists():
            try:
                log.info(f"Seeding sample drawing: {sample.name}")
                with open(sample, "rb") as f:
                    content = f.read()
                d_id = storage.create_drawing(sample.name, content)
                # Run extraction synchronously for seed
                run_extraction_sync(d_id, None)
                log.info(f"Successfully seeded and extracted: {sample.name} (ID: {d_id})")
            except Exception as e:
                log.warning(f"Failed to seed {sample.name}: {e}")

