"""Состояние задачи: где мы, что сделано, чего ждём от человека.

Команды (task — имя папки в projects/):
  init     <task> "<вопрос задачи>"           создать задачу
  status   <task> [--json]                    где остановились — вызывать в начале каждой сессии
  start    <task> "<действие>" [--stage S] [--model M]   начать шаг, печатает его номер
  done     <task> <шаг> [файл ...]            шаг завершён, какие файлы создал или изменил
  fail     <task> <шаг> "<ошибка>"            шаг не удался
  wait     <task> "<вопрос>" [--options A B]  агент ждёт ответа человека
  answer   <task> "<ответ>"                   человек ответил, ожидание снято
  stage    <task> <этап> <статус>             сменить статус этапа (pending/in_progress/waiting_human/done/skipped)
  question <task> add "<вопрос>" "<почему важно>"
  question <task> close <Q-id> answered|dropped
  list                                         все задачи и их этапы
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime

from common import (STAGES, PROJECTS, ROOT, ToolError, append_log, load_state, main_wrapper,
                    now_iso, save_state, task_dir)

STAGE_STATUSES = ["pending", "in_progress", "waiting_human", "done", "skipped"]


def find_step(state: dict, step_id: int) -> dict:
    for s in state["steps"]:
        if s["id"] == step_id:
            return s
    raise ToolError(f"Шаг {step_id} не найден. Номера шагов: "
                    f"{', '.join(str(s['id']) for s in state['steps']) or 'шагов ещё нет'}.")


def cmd_init(a) -> None:
    tdir = task_dir(a.task, must_exist=False)
    if (tdir / "state.json").exists():
        raise ToolError(f"Задача «{a.task}» уже существует. Продолжить: python scripts/state.py status {a.task}")
    (tdir / "sources").mkdir(parents=True, exist_ok=True)
    ts = now_iso()
    state = {
        "schema_version": 1, "task_id": a.task, "title": a.title,
        "created": ts, "updated": ts, "stage": STAGES[0],
        "stages": {s: ("in_progress" if i == 0 else "pending") for i, s in enumerate(STAGES)},
        "steps": [], "waiting_for_human": None, "open_questions": [],
    }
    save_state(tdir, state)
    (tdir / "evidence.jsonl").touch()
    (tdir / "cost.csv").write_text(
        "timestamp,step_id,stage,model,input_tokens,output_tokens,usd,estimated\n", encoding="utf-8")
    append_log(tdir, "", STAGES[0], "init", f"задача создана: {a.title}")
    print(f"Задача создана: projects/{a.task}/. Текущий этап: 01-intake.")


def cmd_status(a) -> None:
    tdir = task_dir(a.task)
    st = load_state(tdir)
    if a.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return
    print(f"Задача: {st['task_id']} — {st['title']}")
    print(f"Текущий этап: {st['stage']}")
    marks = {"done": "✓", "in_progress": "…", "waiting_human": "?", "pending": " ", "skipped": "-"}
    print("Этапы: " + "  ".join(f"[{marks[v]}] {k}" for k, v in st["stages"].items()))
    if st["waiting_for_human"]:
        w = st["waiting_for_human"]
        print(f"\n>>> ЖДЁМ ЧЕЛОВЕКА (с {w['since']}): {w['question']}")
        if w.get("options"):
            print("    варианты: " + " | ".join(w["options"]))
    unfinished = [s for s in st["steps"] if s["status"] in ("in_progress", "failed")]
    if unfinished:
        print("\nНезавершённые шаги:")
        for s in unfinished:
            extra = f" — ошибка: {s['error']}" if s["error"] else ""
            print(f"  #{s['id']} [{s['status']}] {s['stage']}: {s['action']}{extra}")
    done = [s for s in st["steps"] if s["status"] == "done"]
    print(f"\nЗавершено шагов: {len(done)} из {len(st['steps'])}")
    for s in done[-5:]:
        print(f"  #{s['id']} {s['stage']}: {s['action']} → {', '.join(s['outputs']) or '—'}")
    open_q = [q for q in st["open_questions"] if q["status"] == "open"]
    if open_q:
        print("\nОткрытые вопросы:")
        for q in open_q:
            print(f"  {q['id']}. {q['text']} (важно: {q['matters_because']})")
    print("\nПравило: шаги done не повторять; начать с ожидания человека, затем с незавершённых шагов.")


def cmd_start(a) -> None:
    tdir = task_dir(a.task)
    st = load_state(tdir)
    stage = a.stage or st["stage"]
    if stage not in STAGES:
        raise ToolError(f"Неизвестный этап «{stage}». Этапы: {', '.join(STAGES)}")
    new_id = max((s["id"] for s in st["steps"]), default=0) + 1
    st["steps"].append({"id": new_id, "stage": stage, "action": a.action, "status": "in_progress",
                        "started": now_iso(), "finished": None, "outputs": [],
                        "model": a.model, "error": None})
    if st["stages"][stage] == "pending":
        st["stages"][stage] = "in_progress"
    st["stage"] = stage
    save_state(tdir, st)
    append_log(tdir, new_id, stage, "started", a.action)
    print(new_id)


def cmd_done(a) -> None:
    tdir = task_dir(a.task)
    st = load_state(tdir)
    step = find_step(st, a.step)
    if step["status"] == "done":
        raise ToolError(f"Шаг {a.step} уже завершён — повторять не нужно.")
    missing = [f for f in a.outputs if not (tdir / f).exists()]
    if missing:
        raise ToolError(f"Файлы не найдены в projects/{a.task}/: {', '.join(missing)}")
    step.update(status="done", finished=now_iso(), outputs=a.outputs, error=None)
    save_state(tdir, st)
    append_log(tdir, a.step, step["stage"], "done", f"{step['action']} → {', '.join(a.outputs) or '—'}")
    print(f"Шаг {a.step} завершён.")


def cmd_fail(a) -> None:
    tdir = task_dir(a.task)
    st = load_state(tdir)
    step = find_step(st, a.step)
    step.update(status="failed", finished=now_iso(), error=a.error)
    save_state(tdir, st)
    append_log(tdir, a.step, step["stage"], "failed", a.error)
    print(f"Шаг {a.step} отмечен как неудачный. Сообщите пользователю и предложите обход.")


def cmd_wait(a) -> None:
    tdir = task_dir(a.task)
    st = load_state(tdir)
    st["waiting_for_human"] = {"question": a.question, "since": now_iso()}
    if a.options:
        st["waiting_for_human"]["options"] = a.options
    st["stages"][st["stage"]] = "waiting_human"
    save_state(tdir, st)
    append_log(tdir, "", st["stage"], "waiting", a.question)
    print("Вопрос сохранён. Задайте его пользователю и остановитесь до ответа.")


def cmd_answer(a) -> None:
    tdir = task_dir(a.task)
    st = load_state(tdir)
    if not st["waiting_for_human"]:
        raise ToolError("Агент сейчас ничего не ждёт от человека.")
    q = st["waiting_for_human"]["question"]
    st["waiting_for_human"] = None
    if st["stages"][st["stage"]] == "waiting_human":
        st["stages"][st["stage"]] = "in_progress"
    save_state(tdir, st)
    append_log(tdir, "", st["stage"], "answered", f"«{q}» → {a.answer}")
    print("Ответ записан, ожидание снято.")


def cost_reminder(tdir, st: dict, stage_code: str) -> str:
    """Если за этап в cost.csv не появилось ни одной строки — напомнить записать оценку.
    В Claude Code строки пишет хук; в средах без хука это забывают (GigaCode, Cursor)."""
    starts = [s.get("started") for s in st["steps"] if s["stage"] == stage_code and s.get("started")]
    if not starts:
        return ""
    try:
        since = min(datetime.fromisoformat(x) for x in starts)
        rows = list(csv.DictReader((tdir / "cost.csv").open(encoding="utf-8")))
        if any(r.get("timestamp") and datetime.fromisoformat(r["timestamp"]) >= since for r in rows):
            return ""
    except (OSError, ValueError, TypeError):
        pass
    return (f"ВНИМАНИЕ: расход этапа {stage_code} не записан (среда без хука?). Запиши оценку: "
            f"python scripts/cost.py add {tdir.name} --model <модель> --chars <объём прочитанного и написанного текста> --stage {stage_code}")


def cmd_stage(a) -> None:
    tdir = task_dir(a.task)
    st = load_state(tdir)
    if a.stage_code not in STAGES:
        raise ToolError(f"Неизвестный этап «{a.stage_code}». Этапы: {', '.join(STAGES)}")
    if a.status not in STAGE_STATUSES:
        raise ToolError(f"Неизвестный статус «{a.status}». Статусы: {', '.join(STAGE_STATUSES)}")
    idx = STAGES.index(a.stage_code)
    if a.status in ("done", "skipped"):
        if any(s["stage"] == a.stage_code and s["status"] == "in_progress" for s in st["steps"]):
            raise ToolError(f"На этапе {a.stage_code} есть незавершённые шаги — сначала done или fail.")
        st["stages"][a.stage_code] = a.status
        nxt = next((s for s in STAGES[idx + 1:] if st["stages"][s] in ("pending", "in_progress")), None)
        if nxt:
            st["stage"] = nxt
            if st["stages"][nxt] == "pending":
                st["stages"][nxt] = "in_progress"
        msg = f"этап {a.stage_code} → {a.status}" + (f"; следующий: {nxt}" if nxt else "; все этапы пройдены")
    else:
        st["stages"][a.stage_code] = a.status
        st["stage"] = a.stage_code
        reopened = []
        if a.status == "in_progress":  # возврат к этапу: следующие снова ждут
            for s in STAGES[idx + 1:]:
                if st["stages"][s] != "pending":
                    st["stages"][s] = "pending"
                    reopened.append(s)
        msg = f"этап {a.stage_code} → {a.status}" + (f"; снова pending: {', '.join(reopened)}" if reopened else "")
    save_state(tdir, st)
    append_log(tdir, "", a.stage_code, "stage", msg)
    print(msg)
    if a.status == "done":
        reminder = cost_reminder(tdir, st, a.stage_code)
        if reminder:
            print(reminder)


def cmd_question(a) -> None:
    tdir = task_dir(a.task)
    st = load_state(tdir)
    if a.action == "add":
        if len(a.args) != 2:
            raise ToolError('Формат: question <task> add "<вопрос>" "<почему важно>"')
        nums = [int(q["id"][1:]) for q in st["open_questions"]]
        qid = f"Q{max(nums, default=0) + 1}"
        st["open_questions"].append({"id": qid, "text": a.args[0], "matters_because": a.args[1], "status": "open"})
        msg = f"{qid} добавлен: {a.args[0]}"
    elif a.action == "close":
        if len(a.args) != 2 or a.args[1] not in ("answered", "dropped"):
            raise ToolError("Формат: question <task> close <Q-id> answered|dropped")
        q = next((q for q in st["open_questions"] if q["id"] == a.args[0]), None)
        if not q:
            raise ToolError(f"Вопрос {a.args[0]} не найден.")
        q["status"] = a.args[1]
        msg = f"{q['id']} → {a.args[1]}"
    else:
        raise ToolError("Действие: add или close.")
    save_state(tdir, st)
    append_log(tdir, "", st["stage"], "question", msg)
    print(msg)


def cmd_list(a) -> None:
    found = False
    for p in sorted(PROJECTS.glob("*/state.json")):
        st = json.loads(p.read_text(encoding="utf-8"))
        wait = " (ждёт человека)" if st["waiting_for_human"] else ""
        print(f"{st['task_id']}: {st['stage']}{wait} — {st['title']}")
        found = True
    if not found:
        print("Задач нет.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("task"); s.add_argument("title"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("status"); s.add_argument("task"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("start"); s.add_argument("task"); s.add_argument("action")
    s.add_argument("--stage"); s.add_argument("--model"); s.set_defaults(fn=cmd_start)
    s = sub.add_parser("done"); s.add_argument("task"); s.add_argument("step", type=int)
    s.add_argument("outputs", nargs="*"); s.set_defaults(fn=cmd_done)
    s = sub.add_parser("fail"); s.add_argument("task"); s.add_argument("step", type=int); s.add_argument("error"); s.set_defaults(fn=cmd_fail)
    s = sub.add_parser("wait"); s.add_argument("task"); s.add_argument("question")
    s.add_argument("--options", nargs="+"); s.set_defaults(fn=cmd_wait)
    s = sub.add_parser("answer"); s.add_argument("task"); s.add_argument("answer"); s.set_defaults(fn=cmd_answer)
    s = sub.add_parser("stage"); s.add_argument("task"); s.add_argument("stage_code"); s.add_argument("status"); s.set_defaults(fn=cmd_stage)
    s = sub.add_parser("question"); s.add_argument("task"); s.add_argument("action"); s.add_argument("args", nargs="*"); s.set_defaults(fn=cmd_question)
    s = sub.add_parser("list"); s.set_defaults(fn=cmd_list)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main_wrapper(main)
