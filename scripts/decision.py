"""Поддержка решений после выбора: решения, обязательства, «что решать сейчас».

  python scripts/decision.py add <task> --title "Вернуть настройку частоты уведомлений" --option 2 \\
         --grounds E005,E007 --owner "руководитель продукта" --metric "удержание D30 новых когорт" \\
         --review-if "D30 не выросло на 2 п.п. за 8 недель" --review-by 2027-01-31
  python scripts/decision.py commit <task> D1 --what "Выпустить настройку частоты" --owner "команда мобильного" \\
         --due 2026-12-15 [--ref P2]
  python scripts/decision.py close <task> C1 [--note "выпущено в 4.2"]
  python scripts/decision.py check <task>     что решить сейчас: устаревшие основания, сроки пересмотра,
                                              просроченные обязательства, вопросы к человеку
  python scripts/decision.py list <task>

Хранилище — decisions.yaml; после каждой команды пересобирается читаемый decisions.md
(его проверяют validate.py и revise.py). Ответственный — роль, а не имя: персональные данные
в репозиторий не пишем. Решение принимает человек: скрипт только записывает его выбор и следит за ним.
"""
from __future__ import annotations

import argparse
import re
from datetime import date, timedelta

import yaml

from common import ToolError, append_log, load_evidence, load_state, main_wrapper, task_dir, today

SOON_DAYS = 7


def load(tdir) -> dict:
    path = tdir / "decisions.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    return data or {"decisions": [], "commitments": []}


def save(tdir, data: dict) -> None:
    header = "# Реестр решений и обязательств. Меняется только через scripts/decision.py\n"
    tmp = tdir / "decisions.yaml.tmp"
    tmp.write_text(header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8")
    tmp.replace(tdir / "decisions.yaml")
    render(tdir, data)


def parse_date(s: str | None, field: str) -> str | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        raise ToolError(f"{field}: дата в формате ГГГГ-ММ-ДД, получено «{s}».")


def render(tdir, data: dict) -> None:
    ev = {e["id"]: e for e in load_evidence(tdir)}
    out = ["# Журнал решений", "",
           "<!-- Файл собирается из decisions.yaml командой scripts/decision.py — не правьте вручную. -->", ""]
    for d in data["decisions"]:
        out += [f"## {d['id']}. {d['title']}", "",
                f"- **Вариант:** {d.get('option') or '—'}; **решили:** {d['decided']}",
                f"- **Ответственный:** {d['owner']}",
                f"- **Метрика:** {d['metric']}",
                f"- **Пересмотреть, если:** {d['review_if']}" + (f" (не позже {d['review_by']})" if d.get("review_by") else ""),
                "- **Основания:** " + ", ".join(
                    f"[{g}]" + (" — устарело" if ev.get(g, {}).get("status") == "revoked" else "") for g in d["grounds"]),
                f"- **Статус:** {d['status']}", ""]
        cs = [c for c in data["commitments"] if c["decision"] == d["id"]]
        if cs:
            out += ["| Обязательство | Ответственный | Срок | Связь | Статус |", "| --- | --- | --- | --- | --- |"]
            for c in cs:
                ref = f"[{c['ref']}]" if c.get("ref") else "—"
                out.append(f"| {c['id']}. {c['what']} | {c['owner']} | {c.get('due') or '—'} | {ref} | {c['status']} |")
            out.append("")
    (tdir / "decisions.md").write_text("\n".join(out), encoding="utf-8")


def next_id(items: list[dict], prefix: str) -> str:
    nums = [int(i["id"][1:]) for i in items if re.fullmatch(prefix + r"\d+", i["id"])]
    return f"{prefix}{max(nums, default=0) + 1}"


def cmd_add(a) -> None:
    tdir = task_dir(a.task)
    data = load(tdir)
    ev = {e["id"]: e for e in load_evidence(tdir)}
    grounds = [g.strip() for g in a.grounds.split(",") if g.strip()]
    if not grounds:
        raise ToolError("Укажите --grounds: записи E…, на которые опирается решение (их отслеживает пересмотр).")
    for g in grounds:
        if g not in ev:
            raise ToolError(f"Основания {g} нет в evidence.jsonl.")
        if ev[g]["status"] == "revoked":
            raise ToolError(f"{g} отозвана ({ev[g].get('revoked_reason')}) — на неё нельзя опирать решение.")
    did = next_id(data["decisions"], "D")
    data["decisions"].append({"id": did, "title": a.title, "option": a.option, "decided": today(), "owner": a.owner,
                              "metric": a.metric, "review_if": a.review_if,
                              "review_by": parse_date(a.review_by, "--review-by"), "grounds": grounds,
                              "status": "active"})
    save(tdir, data)
    append_log(tdir, "", load_state(tdir)["stage"], "decision", f"{did}: {a.title}; основания {', '.join(grounds)}")
    print(f"{did} записано. Добавьте обязательства: python scripts/decision.py commit {a.task} {did} --what … --owner … --due …")


def cmd_commit(a) -> None:
    tdir = task_dir(a.task)
    data = load(tdir)
    if not any(d["id"] == a.decision for d in data["decisions"]):
        raise ToolError(f"Решения {a.decision} нет — сначала decision.py add.")
    cid = next_id(data["commitments"], "C")
    data["commitments"].append({"id": cid, "decision": a.decision, "what": a.what, "owner": a.owner,
                                "due": parse_date(a.due, "--due"), "ref": a.ref, "status": "open", "note": None})
    save(tdir, data)
    append_log(tdir, "", load_state(tdir)["stage"], "commitment", f"{cid} ({a.decision}): {a.what}, срок {a.due or '—'}")
    print(f"{cid} записано.")


def cmd_close(a) -> None:
    tdir = task_dir(a.task)
    data = load(tdir)
    c = next((c for c in data["commitments"] if c["id"] == a.id), None)
    if not c:
        raise ToolError(f"Обязательства {a.id} нет.")
    c.update(status="done", note=a.note, closed=today())
    save(tdir, data)
    append_log(tdir, "", load_state(tdir)["stage"], "commitment", f"{a.id} выполнено" + (f": {a.note}" if a.note else ""))
    print(f"{a.id} закрыто.")


def agenda(tdir) -> list[tuple[str, str]]:
    """Что требует внимания человека сейчас — список (раздел, пункт). Пустой список — всё спокойно."""
    data = load(tdir)
    state = load_state(tdir)
    ev = {e["id"]: e for e in load_evidence(tdir)}
    now = date.fromisoformat(today())
    items: list[tuple[str, str]] = []
    w = state.get("waiting_for_human")
    if w:
        items.append(("Ждёт вашего ответа", f"{w['question']} (с {w['since'][:10]})"))
    for d in data["decisions"]:
        if d["status"] != "active":
            continue
        for g in d["grounds"]:
            e = ev.get(g)
            if not e:
                items.append(("Основание устарело", f"{d['id']}: записи {g} больше нет в реестре"))
            elif e["status"] == "revoked":
                items.append(("Основание устарело",
                              f"{d['id']} «{d['title']}»: [{g}] отозвана — {e.get('revoked_reason')}. "
                              f"Пересмотреть решение? (skills/revise.md, шаг 5)"))
        if d["grounds"] and all(ev.get(g, {}).get("type") in ("hypothesis", "forecast", "synthetic") for g in d["grounds"]):
            items.append(("Слабые основания", f"{d['id']}: опирается только на гипотезы и прогнозы — "
                                              f"проверьте их по validation-plan.md"))
        if d.get("review_by") and date.fromisoformat(d["review_by"]) <= now:
            items.append(("Пора пересмотреть", f"{d['id']} «{d['title']}»: срок {d['review_by']}; "
                                               f"условие: {d['review_if']}; метрика: {d['metric']}"))
    for c in data["commitments"]:
        if c["status"] != "open" or not c.get("due"):
            continue
        due = date.fromisoformat(c["due"])
        if due < now:
            items.append(("Просрочено", f"{c['id']} ({c['decision']}) {c['what']} — {c['owner']}, срок был {c['due']}"))
        elif due <= now + timedelta(days=SOON_DAYS):
            items.append(("Скоро срок", f"{c['id']} ({c['decision']}) {c['what']} — {c['owner']}, до {c['due']}"))
    for q in state.get("open_questions", []):
        if q.get("status") == "open":
            items.append(("Открытые вопросы", f"{q['id']}: {q['text']} — {q.get('matters_because', '')}"))
    return items


def cmd_check(a) -> None:
    tdir = task_dir(a.task)
    if (tdir / "decisions.yaml").exists():
        render(tdir, load(tdir))  # пометки «устарело» актуальны на момент проверки
    items = agenda(tdir)
    if not items:
        print("Решать сейчас нечего: основания решений действуют, сроки не наступили, вопросов к вам нет.")
        return
    urgent = sum(1 for s, _ in items if s not in ("Открытые вопросы", "Скоро срок"))
    print(f"Требует внимания: {urgent} срочных, {len(items) - urgent} к сведению.")
    section = None
    for s, text in items:
        if s != section:
            print(f"\n{s}:")
            section = s
        print(f"  - {text}")


def cmd_list(a) -> None:
    tdir = task_dir(a.task)
    data = load(tdir)
    if not data["decisions"]:
        print("Решений пока нет.")
        return
    for d in data["decisions"]:
        print(f"{d['id']} [{d['status']}] {d['title']} — {d['owner']}; основания {', '.join(d['grounds'])}")
        for c in data["commitments"]:
            if c["decision"] == d["id"]:
                print(f"   {c['id']} [{c['status']}] {c['what']} — {c['owner']}, срок {c.get('due') or '—'}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add"); s.add_argument("task"); s.add_argument("--title", required=True)
    s.add_argument("--option"); s.add_argument("--grounds", required=True); s.add_argument("--owner", required=True)
    s.add_argument("--metric", required=True); s.add_argument("--review-if", dest="review_if", required=True)
    s.add_argument("--review-by", dest="review_by"); s.set_defaults(fn=cmd_add)
    s = sub.add_parser("commit"); s.add_argument("task"); s.add_argument("decision")
    s.add_argument("--what", required=True); s.add_argument("--owner", required=True)
    s.add_argument("--due"); s.add_argument("--ref", help="пункт стратегии P… или запись E…"); s.set_defaults(fn=cmd_commit)
    s = sub.add_parser("close"); s.add_argument("task"); s.add_argument("id"); s.add_argument("--note")
    s.set_defaults(fn=cmd_close)
    s = sub.add_parser("check"); s.add_argument("task"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("list"); s.add_argument("task"); s.set_defaults(fn=cmd_list)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main_wrapper(main)
