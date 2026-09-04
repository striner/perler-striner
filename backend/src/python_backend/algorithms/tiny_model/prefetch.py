from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path

from python_backend.core.config import DEFAULT_MODEL_DIR

from .model_store import ARTIFACTS, ModelStore


def prefetch(model_dir: Path) -> None:
    store = ModelStore(model_dir)
    store.root.mkdir(parents=True, exist_ok=True)
    for artifact in ARTIFACTS:
        destination = store.root / artifact.relative_path
        try:
            store.validate_artifact(artifact)
            print(f"verified {destination}")
            continue
        except Exception:
            pass

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(f"{destination}.part")
        temporary.unlink(missing_ok=True)
        print(f"downloading {artifact.url}")
        request = urllib.request.Request(
            artifact.url,
            headers={"User-Agent": "perler-striner-tiny-model-prefetch/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                with temporary.open("wb") as output:
                    shutil.copyfileobj(response, output, length=1024 * 1024)
            temporary.replace(destination)
            store.validate_artifact(artifact)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        print(f"verified {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and verify tiny-model artifacts")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = parser.parse_args()
    prefetch(args.model_dir)


if __name__ == "__main__":
    main()
