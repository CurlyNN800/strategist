"""Найти выводы, которые затрагивают новые данные.

  python scripts/revise.py <task> <S… | E…> [<S… | E…> ...]

Для нового источника (S…) берутся все его записи из evidence.jsonl, для записи (E…) — она сама.
Затронутыми считаются активные записи с общими темами (topics) и все места в результатах,
где на них ссылаются, а также решения в decision.md / decisions.md. Скрипт только ищет —
что подтверждается, уточняется или опровергается, решает агент по skills/revise.md.
"""
from __future__ import annotations

import argparse
import re

from common import ToolError, load_evidence, main_wrapper, task_dir
from validate import E_RE, RESULT_FILES


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task"); p.add_argument("ids", nargs="+")
    a = p.parse_args()
    tdir = task_dir(a.task)
    evidence = {e["id"]: e for e in load_evidence(tdir)}

    new = []
    for i in a.ids:
        if re.fullmatch(r"S\d+", i):
            recs = [e for e in evidence.values() if e.get("source") == i]
            if not recs:
                raise ToolError(f"Из источника {i} ещё не выписано ни одной записи — сначала заполните evidence.jsonl.")
            new += recs
        elif i in evidence:
            new.append(evidence[i])
        else:
            raise ToolError(f"Не найдено: {i}")
    new_ids = {e["id"] for e in new}
    topics = {t for e in new for t in e.get("topics", [])}

    affected = [e for e in evidence.values()
                if e["id"] not in new_ids and e.get("status") == "active" and topics & set(e.get("topics", []))]
    print(f"Новые записи: {', '.join(sorted(new_ids))}; темы: {', '.join(sorted(topics))}")
    if not affected:
        print("Активных записей с теми же темами нет — выводы не затронуты. Проверьте по смыслу и запишите в log.md.")
        return 0

    print(f"\nЗатронутые записи ({len(affected)}) — сравните с новыми и решите: подтверждается / уточняется / опровергается:")
    for e in affected:
        print(f"  {e['id']} [{e['type']}] {e['claim']}")

    aff_ids = {e["id"] for e in affected}
    # гипотезы и прогнозы, которые опираются на затронутые записи
    dependent = [e for e in evidence.values() if e.get("status") == "active" and e["id"] not in aff_ids | new_ids
                 and aff_ids & set(re.findall(r"E\d{3,}", e.get("basis") or ""))]
    if dependent:
        print("\nЗависимые гипотезы и прогнозы (их basis ссылается на затронутые записи):")
        for e in dependent:
            print(f"  {e['id']} [{e['type']}] {e['claim']}")
        aff_ids |= {e["id"] for e in dependent}

    print("\nМеста в результатах, которые нужно пересмотреть:")
    found = False
    for name in RESULT_FILES:
        path = tdir / name
        if not path.exists():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hit = aff_ids & set(E_RE.findall(line))
            if hit:
                found = True
                mark = "  ⚠ РЕШЕНИЕ" if name in ("decision.md", "decisions.md") else ""
                print(f"  {name}:{n} [{', '.join(sorted(hit))}]{mark}  {line.strip()[:100]}")
    if not found:
        print("  нет")
    print("\nЕсли затронуто основание решения — не меняйте решение сами, сообщите пользователю (skills/revise.md, шаг 5).")
    return 0


if __name__ == "__main__":
    main_wrapper(main)
