"""Batch 4 build (approved 2026-11-16): batch 3's stages on batch 4's users, catalogue, plan and seed.

    python -m research.dataset.batch4_build --prepare          # plan, seed each user, run every SQL, save the jobs
    python -m research.dataset.batch4_build --collect-authored # check the written versions (raw/batch4/authored/)
    python -m research.dataset.batch4_build --make-review      # an INCOMPLETE review manifest to fill in
    python -m research.dataset.batch4_build --replay           # checks + review -> data/batch4/{train,validation}.jsonl
"""

from functools import partial

from research.dataset import batch4
from research.dataset.batch3_build import Batch, main, validate_jobs

BATCH4 = Batch("batch4", "b4", batch4.TODAYS, batch4.TRAIN, batch4.VALIDATION, batch4.load_batch4_catalogue,
               batch4.batch4_user, batch4.plan, batch4.SEED_PREFIX)  # fmt: skip
validate_batch4_jobs = partial(validate_jobs, batch=BATCH4)

if __name__ == "__main__":
    raise SystemExit(main(batch=BATCH4))
