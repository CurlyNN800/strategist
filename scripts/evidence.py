"""Реестр утверждений evidence.jsonl: добавить, отозвать, найти.

  python scripts/evidence.py add <task> --type fact --claim "..." --source S001 --where "стр. 3" \\
         --topics retention,pricing --confidence high
  python scripts/evidence.py add <task> --type hypothesis --claim "..." --basis "E003, E005: ..." --topics retention
  python scripts/evidence.py revoke <task> E007 --by E010 --reason "релиз вышел позже начала падения"
  python scripts/evidence.py list <task> [--topic T] [--type fact] [--all]

id назначается автоматически, запись проверяется по схеме до сохранения —
в реестр не попадёт fact без источника или гипотеза без основания.
"""
from __future__ import annotations

import argparse
import json

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
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main_wrapper(main)
