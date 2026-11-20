"""Собрать итоговый отчёт report.md из результатов этапов.

  python scripts/build_report.py <task> [--clean]

--clean дополнительно собирает report-clean.md — версию для руководителя: без служебных меток [R…] и [P…],
ссылки [E…] превращены в сноски с утверждением и источником. Ничего не теряется: те же утверждения, читать легче.

Порядок: summary.md (5–7 строк для руководителя) → ситуация → варианты → решение →
продуктовая и коммуникационная стратегии → план проверки → журнал решений →
приложения: реестр цитируемых утверждений, источники, стоимость.
Если в задаче есть deliverable.md (итоговый документ по структуре, которую требует бриф), отчёт
строится из него: deliverable.md → приложения. Рабочие файлы этапов остаются в папке задачи.
Отчёт читается без остальных файлов: все метки [E…] раскрыты в приложении.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import re

from common import ToolError, load_evidence, load_sources, load_state, main_wrapper, now_iso, task_dir
from validate import E_RE

SECTIONS = [("summary.md", "Кратко для руководителя"), ("situation.md", "Картина ситуации"),
            ("options.md", "Варианты"), ("decision.md", "Решение"),
            ("product-strategy.md", "Продуктовая стратегия"), ("comms-strategy.md", "Коммуникационная стратегия"),
            ("validation-plan.md", "План проверки"), ("decisions.md", "Журнал решений")]
TYPE_RU = {"fact": "факт", "hypothesis": "гипотеза", "forecast": "прогноз", "synthetic": "синтетика"}


def demote(md: str) -> str:
    """Убрать первый заголовок файла и сдвинуть остальные на уровень ниже."""
    lines = md.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    out = []
    for line in lines:
        if line.startswith("> Пример формата"):
            continue
        out.append("#" + line if re.match(r"#{1,5} ", line) else line)
    return "\n".join(out).strip()


def demote_keep(md: str) -> str:
    """Итоговый документ: убрать его заголовок первого уровня, остальные уровни не трогать."""
    lines = md.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def make_clean(body: str, evidence: dict, sources: dict, cost_text: str) -> str:
    """Версия для чтения: [R…]/[P…] убраны, группы [E…] — одна сноска с перечнем утверждений."""
    notes: list[str] = []
    seen: dict[tuple, int] = {}

    def repl(m: re.Match) -> str:
        ids = tuple(E_RE.findall(m.group(0)))
        if ids not in seen:
            seen[ids] = len(notes) + 1
            parts = []
            for rid in ids:
                e = evidence.get(rid, {})
                src = e.get("source")
                where = f", {e['where']}" if e.get("where") else ""
                kind = TYPE_RU.get(e.get("type", ""), "")
                origin = f"{src}{where}" if src else (e.get("basis") or "")
                parts.append(f"{kind}: {e.get('claim', rid)} — {origin}")
            notes.append(f"[^{seen[ids]}]: " + " · ".join(parts))
        return f"[^{seen[ids]}]"

    out_lines = []
    in_code = False
    skip = False
    for line in body.splitlines():
        if line.startswith("## "):
            skip = line.startswith("## Соответствие требованиям")
        if skip:
            continue
        if line.strip().startswith("```"):
            in_code = not in_code
        if not in_code:
            line = re.sub(r"\s*\[(R|P)\d+\]", "", line)
            line = line.replace("каждая ссылка раскрыта в приложении А", "каждая ссылка раскрыта в сноске")
            line = re.sub(r"(?:\s*\[E\d{3,}\])+", lambda m: repl(m), line)
            if re.fullmatch(r"\s*", line) and out_lines and re.fullmatch(r"\s*", out_lines[-1]):
                continue
        out_lines.append(line)
    src_lines = [f"- **{sid}** {s.get('title', '')}. {s.get('url') or s.get('original_file') or ''}" for sid, s in sources.items()]
    return ("\n".join(out_lines) + "\n\n---\n\n**Источники**\n\n" + "\n".join(src_lines)
            + "\n\n" + "\n".join(notes) + "\n")  # стоимость работы агента — только в report.md


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task")
    p.add_argument("--clean", action="store_true", help="ещё и report-clean.md для руководителя")
    a = p.parse_args()
    tdir = task_dir(a.task)
    state = load_state(tdir)
    evidence = {e["id"]: e for e in load_evidence(tdir)}
    sources = {s["id"]: s for s in load_sources(tdir)}

    deliverable = tdir / "deliverable.md"
    title = state["title"]
    if deliverable.exists():
        first = deliverable.read_text(encoding="utf-8").lstrip().splitlines()[0]
        title = first[2:].strip() if first.startswith("# ") else title
    parts = [f"# {title}", f"_Отчёт агента «Стратег» · задача `{state['task_id']}` · собран {now_iso()[:16].replace('T', ' ')}_"]
    missing = []
    sections = SECTIONS
    if deliverable.exists():
        parts.append(demote_keep(deliverable.read_text(encoding="utf-8")))
        sections = []
        print("Отчёт собран по deliverable.md (структура брифа); рабочие файлы этапов — в папке задачи.")
    for fname, title in sections:
        path = tdir / fname
        if path.exists():
            parts.append(f"## {title}\n\n{demote(path.read_text(encoding='utf-8'))}")
        elif fname not in ("decisions.md",):
            missing.append(fname)
    if "summary.md" in missing and not deliverable.exists():
        print("ВНИМАНИЕ: нет summary.md — напишите 5–7 строк для руководителя и соберите отчёт снова.")

    body = "\n\n".join(parts)
    used = sorted(set(E_RE.findall(body)), key=lambda x: int(x[1:]))
    rows = ["| Метка | Тип | Утверждение | Источник | Уверенность |", "| --- | --- | --- | --- | --- |"]
    for rid in used:
        e = evidence.get(rid)
        if not e:
            raise ToolError(f"Метка [{rid}] не найдена в evidence.jsonl — запустите validate.py.")
        src = e.get("source") or "—"
        where = f", {e['where']}" if e.get("where") else ""
        status = " (отозвано)" if e.get("status") == "revoked" else ""
        claim = e["claim"].replace("|", "/")
        rows.append(f"| {rid} | {TYPE_RU.get(e['type'], e['type'])}{status} | {claim} | {src}{where} | {e['confidence']} |")
    appendix = ["## Приложение А. Утверждения, на которые ссылается отчёт", "\n".join(rows)]

    src_used = sorted({evidence[r]["source"] for r in used if evidence[r].get("source")})
    src_lines = []
    for sid in src_used:
        s = sources.get(sid, {})
        ref = s.get("url") or s.get("original_file") or s.get("local", "")
        note = f" — {s['notes']}" if s.get("notes") else ""
        synth = " **(синтетика)**" if s.get("kind") == "synthetic" else ""
        src_lines.append(f"- **{sid}** {s.get('title', '')}{synth}. {ref}. Загружено {s.get('retrieved', '?')}{note}")
    appendix += ["## Приложение Б. Источники", "\n".join(src_lines) or "_нет_"]

    import cost  # отчёт о расходах печатаем в строку
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        import sys
        argv, sys.argv = sys.argv, ["cost.py", "report", a.task]
        try:
            cost.main()
        finally:
            sys.argv = argv
    appendix += ["## Приложение В. Стоимость работы агента", buf.getvalue().strip()]

    report = body + "\n\n---\n\n" + "\n\n".join(appendix) + "\n"
    (tdir / "report.md").write_text(report, encoding="utf-8")
    if a.clean:
        clean = make_clean(body, evidence, sources, buf.getvalue().strip())
        (tdir / "report-clean.md").write_text(clean, encoding="utf-8")
        print("Собран report-clean.md: версия для руководителя, ссылки на утверждения — сносками.")
    n_parts = len(re.findall(r"^## ", "\n\n".join(parts[2:]), flags=re.M))
    print(f"Собран report.md: разделов {n_parts}, утверждений {len(used)}, источников {len(src_used)}.")
    if missing:
        print("Нет файлов: " + ", ".join(m for m in missing))
    return 0


if __name__ == "__main__":
    main_wrapper(main)
