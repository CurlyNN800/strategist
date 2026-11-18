"""Реестр утверждений evidence.jsonl: добавить, отозвать, найти, показать связи.

  python scripts/evidence.py add <task> --type fact --claim "..." --source S001 --where "стр. 3" \\
         --topics retention,pricing --confidence high
  python scripts/evidence.py add <task> --type hypothesis --claim "..." --basis "E003, E005: ..." --topics retention
  python scripts/evidence.py revoke <task> E007 --by E010 --reason "релиз вышел позже начала падения"
  python scripts/evidence.py list <task> [--topic T] [--type fact] [--all]
  python scripts/evidence.py search <task> "отток после обновления" [--all] [--limit 10]
  python scripts/evidence.py show <task> E005      источник, на чём основана, что на неё опирается, где использована

id назначается автоматически, запись проверяется по схеме до сохранения —
в реестр не попадёт fact без источника или гипотеза без основания.
"""
from __future__ import annotations

import argparse
import json
import re

from jsonschema import Draft202012Validator

from common import SCHEMAS, ToolError, load_evidence, load_sources, load_state, main_wrapper, task_dir, today


def save_all(tdir, records: list[dict]) -> None:
    tmp = tdir / "evidence.jsonl.tmp"
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    tmp.replace(tdir / "evidence.jsonl")


def check(rec: dict) -> None:
    schema = json.loads((SCHEMAS / "evidence.schema.json").read_text(encoding="utf-8"))
    errs = [f"{'/'.join(map(str, e.path)) or 'запись'}: {e.message}" for e in Draft202012Validator(schema).iter_errors(rec)]
    if errs:
        raise ToolError("Запись не прошла проверку: " + "; ".join(errs))


def cmd_add(a) -> None:
    tdir = task_dir(a.task)
    records = load_evidence(tdir)
    nums = [int(r["id"][1:]) for r in records if r.get("id", "").startswith("E")]
    rid = f"E{max(nums, default=0) + 1:03d}"
    if a.type == "fact" and not (a.source and a.where):
        raise ToolError("Факт без источника не записывается: укажите --source S… и --where «где в источнике». "
                        "Нет источника — это hypothesis с --basis.")
    if a.type in ("hypothesis", "forecast") and not a.basis:
        raise ToolError(f"Для {a.type} нужно --basis: на чём основано (метки E… и/или рассуждение).")
    if a.type == "synthetic" and not a.source:
        raise ToolError("Для synthetic укажите --source — сессию модельного респондента в sources/.")
    if a.source:
        sources = {s["id"]: s for s in load_sources(tdir)}
        if a.source not in sources:
            raise ToolError(f"Источника {a.source} нет в sources.yaml — сначала fetch_source.py или extract.py.")
        if sources[a.source].get("kind") == "synthetic" and a.type == "fact":
            raise ToolError(f"{a.source} — синтетический источник: тип записи должен быть synthetic, не fact.")
    rec = {"id": rid, "claim": a.claim, "type": a.type, "source": a.source, "where": a.where,
           "basis": a.basis, "confidence": a.confidence, "status": "active", "revoked_by": None,
           "revoked_reason": None, "topics": [t.strip() for t in a.topics.split(",") if t.strip()],
           "stage": a.stage or load_state(tdir)["stage"], "added": today()}
    check(rec)
    records.append(rec)
    save_all(tdir, records)
    print(f"{rid} добавлена ({a.type}). Ссылайтесь на неё в тексте как [{rid}].")


def cmd_revoke(a) -> None:
    tdir = task_dir(a.task)
    records = load_evidence(tdir)
    rec = next((r for r in records if r["id"] == a.id), None)
    if not rec:
        raise ToolError(f"Записи {a.id} нет.")
    if rec["status"] == "revoked":
        raise ToolError(f"{a.id} уже отозвана: {rec['revoked_reason']}")
    rec.update(status="revoked", revoked_by=a.by, revoked_reason=a.reason)
    check(rec)
    save_all(tdir, records)
    if (tdir / "decisions.yaml").exists():  # отметить «устарело» у оснований решений в decisions.md
        from decision import load as load_decisions, render
        render(tdir, load_decisions(tdir))
    print(f"{a.id} отозвана. Найдите места, где она использована: python scripts/revise.py {a.task} {a.id}")


def cmd_list(a) -> None:
    tdir = task_dir(a.task)
    for r in load_evidence(tdir):
        if not a.all and r["status"] != "active":
            continue
        if a.topic and a.topic not in r.get("topics", []):
            continue
        if a.type and r["type"] != a.type:
            continue
        src = f" ← {r['source']}" if r.get("source") else ""
        rev = " [ОТОЗВАНА]" if r["status"] == "revoked" else ""
        print(f"{r['id']} [{r['type']}, {r['confidence']}]{rev} {r['claim']}{src}")


WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.I)
STOP = {"и", "в", "во", "на", "по", "с", "со", "не", "что", "как", "для", "из", "за", "от", "до", "о", "об",
        "а", "но", "или", "ли", "же", "the", "of", "and", "to", "in"}


def stems(text: str) -> set[str]:
    """Грубая основа слова: первые 5 букв. «оттока», «отток», «оттоку» совпадут без словарей."""
    return {w[:5] for w in (m.lower().replace("ё", "е") for m in WORD_RE.findall(text or "")) if w not in STOP}


def record_text(r: dict, sources: dict) -> str:
    src = sources.get(r.get("source") or "", {})
    return " ".join(str(x) for x in (r.get("claim"), r.get("where"), r.get("basis"), " ".join(r.get("topics", [])),
                                     src.get("title"), r.get("revoked_reason")) if x)


def search(tdir, query: str, include_revoked: bool = False, limit: int = 10) -> list[tuple[float, dict]]:
    """Поиск по формулировке (основы слов) и темам. Совпадение темы весит больше слова в тексте."""
    sources = {s["id"]: s for s in load_sources(tdir)}
    q = stems(query)
    if not q:
        raise ToolError("Пустой запрос: укажите слова для поиска.")
    hits = []
    for r in load_evidence(tdir):
        if r["status"] != "active" and not include_revoked:
            continue
        words = stems(record_text(r, sources))
        topic_words = stems(" ".join(t.replace("-", " ").replace("_", " ") for t in r.get("topics", [])))
        score = len(q & words) + 0.5 * len(q & topic_words)
        if score:
            hits.append((score / len(q), r))
    hits.sort(key=lambda x: (-x[0], x[1]["id"]))
    return hits[:limit]


def links(tdir, rid: str) -> dict:
    """Связи записи: источник, основания (basis), зависимые записи, места в результатах и решениях."""
    from validate import E_RE, RESULT_FILES
    records = {r["id"]: r for r in load_evidence(tdir)}
    if rid not in records:
        raise ToolError(f"Записи {rid} нет.")
    rec = records[rid]
    sources = {s["id"]: s for s in load_sources(tdir)}
    upstream = [i for i in dict.fromkeys(re.findall(r"E\d{3,}", rec.get("basis") or "")) if i in records]
    downstream = [r["id"] for r in records.values() if rid in re.findall(r"E\d{3,}", r.get("basis") or "")]
    used = []
    for name in RESULT_FILES:
        path = tdir / name
        if path.exists():
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if rid in E_RE.findall(line):
                    used.append((name, n, line.strip()))
    return {"record": rec, "source": sources.get(rec.get("source") or ""), "upstream": [records[i] for i in upstream],
            "downstream": [records[i] for i in downstream], "used": used}


def fmt_rec(r: dict) -> str:
    rev = " [ОТОЗВАНА]" if r["status"] == "revoked" else ""
    src = f" ← {r['source']}" if r.get("source") else ""
    return f"{r['id']} [{r['type']}, {r['confidence']}]{rev} {r['claim']}{src}"


def cmd_search(a) -> None:
    hits = search(task_dir(a.task), a.query, a.all, a.limit)
    if not hits:
        print("Ничего не найдено. Попробуйте другие слова или темы: python scripts/evidence.py list <task>")
        return
    for score, r in hits:
        print(f"{score:.0%}  {fmt_rec(r)}")


def cmd_show(a) -> None:
    info = links(task_dir(a.task), a.id)
    r = info["record"]
    print(fmt_rec(r))
    if r["status"] == "revoked":
        print(f"  Отозвана: {r.get('revoked_reason')} (заменена: {r.get('revoked_by')})")
    s = info["source"]
    if s:
        print(f"  Источник: {s['id']} — {s.get('title', '')} ({s.get('url') or s.get('local')}); место: {r.get('where')}")
    if r.get("basis"):
        print(f"  Основание: {r['basis']}")
    for title, items in (("Опирается на", info["upstream"]), ("На неё опираются", info["downstream"])):
        if items:
            print(f"  {title}:")
            for x in items:
                print(f"    {fmt_rec(x)}")
    print("  Где использована:" if info["used"] else "  В результатах пока не использована.")
    for name, n, line in info["used"]:
        print(f"    {name}:{n}  {line[:100]}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add"); s.add_argument("task")
    s.add_argument("--type", required=True, choices=["fact", "hypothesis", "forecast", "synthetic"])
    s.add_argument("--claim", required=True); s.add_argument("--source"); s.add_argument("--where")
    s.add_argument("--basis"); s.add_argument("--topics", required=True)
    s.add_argument("--confidence", default="medium", choices=["high", "medium", "low"])
    s.add_argument("--stage"); s.set_defaults(fn=cmd_add)
    s = sub.add_parser("revoke"); s.add_argument("task"); s.add_argument("id")
    s.add_argument("--by", required=True); s.add_argument("--reason", required=True); s.set_defaults(fn=cmd_revoke)
    s = sub.add_parser("list"); s.add_argument("task"); s.add_argument("--topic"); s.add_argument("--type")
    s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("search"); s.add_argument("task"); s.add_argument("query")
    s.add_argument("--all", action="store_true", help="искать и среди отозванных")
    s.add_argument("--limit", type=int, default=10); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("show"); s.add_argument("task"); s.add_argument("id"); s.set_defaults(fn=cmd_show)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main_wrapper(main)
