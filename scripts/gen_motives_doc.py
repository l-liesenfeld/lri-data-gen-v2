"""Regenerate docs/motives.md from data/motive_matrix.json.

Run after editing the matrix:

    python scripts/gen_motives_doc.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "data" / "motive_matrix.json"
OUT = ROOT / "docs" / "motives.md"


def main() -> None:
    raw = json.loads(MATRIX.read_text(encoding="utf-8"))
    lines: list[str] = [
        "# Motives",
        "",
        "_Auto-generated from `data/motive_matrix.json` by `scripts/gen_motives_doc.py`. Edit the JSON, then re-run the script._",
        "",
        "The matrix defines 4 categories × 5 motives = 20 motives total. Each motive has an ID (e.g. `A1`, `L3`), a name, and a German description. IDs are the stable reference everything else keys off.",
        "",
        "## Strength scale",
        "",
        "Every selected motive is configured with a strength between **0.1** and **1.0**. The model receives the numeric value plus this guidance (see `prompts/legacy.txt`):",
        "",
        "> Higher strength values (closer to 1.0) mean the motive should be more detectable (though still not explicitly stated). Lower values (closer to 0.0) mean the motive should be more deeply hidden and nuanced or even ambiguous.",
        "",
        "Practical anchors:",
        "",
        "| Strength | Intent |",
        "|---|---|",
        "| 0.1–0.2 | Barely perceptible — a careful reader might not catch it |",
        "| 0.3–0.5 | Moderate — detectable on close reading |",
        "| 0.6–0.8 | Pronounced — clearly shapes the entry's voice |",
        "| 0.9–1.0 | Dominant — the defining psychological note of the entry |",
        "",
        "## Categories",
        "",
    ]

    for cat_key, cat in raw["motives"].items():
        lines.append(f"### {cat_key} — {cat['name']}")
        lines.append("")
        if cat.get("key_description"):
            lines.append(f"_{cat['key_description']}_")
            lines.append("")
        lines.append("| ID | Name | Description |")
        lines.append("|---|---|---|")
        for _, cell in cat["cells"].items():
            desc = cell["description"].strip().rstrip(";").replace("|", "\\|")
            lines.append(f"| `{cell['key']}` | {cell['name']} | {desc} |")
        lines.append("")

    if "levels" in raw:
        lines.append("## Levels (reference)")
        lines.append("")
        lines.append(
            "Each motive cell maps to a PSI-theory level (intrinsic approach, extrinsic approach, "
            "self-regulated coping, active avoidance, passive avoidance). This metadata is preserved "
            "in the matrix but is **not** currently injected into the prompt."
        )
        lines.append("")
        lines.append("| Key | Name | Description |")
        lines.append("|---|---|---|")
        for _, lvl in raw["levels"].items():
            desc = lvl["description"].replace("|", "\\|")
            lines.append(f"| `{lvl['key']}` | {lvl['name']} | {desc} |")
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
