"""Скопировать субагентов из agents/ в папки сред, которые их поддерживают.

  python scripts/sync_agents.py

agents/*.md — единственный источник правды. Копии: .claude/agents/ (Claude Code),
.gigacode/agents/ (GigaCode CLI). Формат обеих сред — Markdown с YAML-заголовком
(name, description, model), поэтому файлы копируются без изменений.
Запускать после любого изменения agents/.
"""
from __future__ import annotations

import shutil

from common import ROOT, main_wrapper

TARGETS = [ROOT / ".claude" / "agents", ROOT / ".gigacode" / "agents"]


def main() -> int:
    files = [p for p in (ROOT / "agents").glob("*.md") if p.name != "README.md"]
    for target in TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        for old in target.glob("*.md"):
            if not (ROOT / "agents" / old.name).exists():
                old.unlink()
        for f in files:
            shutil.copyfile(f, target / f.name)
        print(f"{target.relative_to(ROOT)}: {', '.join(f.stem for f in files)}")
    return 0


if __name__ == "__main__":
    main_wrapper(main)
