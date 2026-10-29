import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from env_common import run  # noqa: E402

from bt_backend.raw_models import RawBase  # noqa: E402

run(RawBase.metadata)
