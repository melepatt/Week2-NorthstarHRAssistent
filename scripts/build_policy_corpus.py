from __future__ import annotations

from pathlib import Path

from northstar_rag.policy_build import build_corpus

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    manifest = PROJECT_ROOT / "data" / "source" / "manifest.json"
    output_dir = PROJECT_ROOT / "data" / "policies"
    outputs = build_corpus(manifest, output_dir)
    for output in outputs:
        print(output.relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    main()
