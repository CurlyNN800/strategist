"""Самопроверка репозитория одной командой.

  python scripts/selftest.py

Во временной копии образца projects/_example проверяет все скрипты: состояние, реестр, источники,
валидатор (на чистых и на специально испорченных данных), пересмотр, стоимость, сборку отчёта.
Образец и ваши задачи не меняются. Код выхода 0 — всё работает.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from common import PROJECTS, ROOT, main_wrapper

PY = sys.executable
TASK = "_selftest"
results: list[tuple[str, bool, str]] = []


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  {'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail and not ok else ""))


def expect(name: str, args: list[str], code: int = 0, contains: str | None = None) -> str:
    r = run(*args)
    out = r.stdout + r.stderr
    ok = r.returncode == code and (contains is None or contains in out)
    check(name, ok, f"код {r.returncode}, вывод: {out.strip()[:200]}")
    return out


def append_line(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text + "\n")


def mcp_tools_ok() -> bool:
    """Запустить scripts/mcp_server.py как MCP-клиент и проверить список инструментов."""
    code = """
import asyncio, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def m():
    p = StdioServerParameters(command=sys.executable, args=["scripts/mcp_server.py"])
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            t = await s.list_tools()
            print(len(t.tools), "evidence_search" in [x.name for x in t.tools])

asyncio.run(m())
"""
    try:
        r = subprocess.run([PY, "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0 and "True" in r.stdout


REQUIRED = {"yaml": "pyyaml", "jsonschema": "jsonschema", "requests": "requests", "markdownify": "markdownify",
            "pypdf": "pypdf", "docx": "python-docx", "openpyxl": "openpyxl", "pandas": "pandas", "mcp": "mcp"}


def missing_packages() -> list[str]:
    import importlib.util
    return [pkg for mod, pkg in REQUIRED.items() if importlib.util.find_spec(mod) is None]


def main() -> int:
    missing = missing_packages()
    if missing:
        print(f"Не установлены пакеты: {', '.join(missing)}.\n"
              f"Выполните: {Path(PY).name} -m pip install -r requirements.txt — и запустите самопроверку снова.")
        return 1
    tdir = PROJECTS / TASK
    shutil.rmtree(tdir, ignore_errors=True)
    shutil.copytree(PROJECTS / "_example", tdir)
    state = json.loads((tdir / "state.json").read_text(encoding="utf-8"))
    state["task_id"] = TASK
    (tdir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        print("Чистые данные:")
        expect("образец проходит валидатор", ["scripts/validate.py", "_example"], 0, "Проверка пройдена")
        expect("статус показывает упавший шаг", ["scripts/state.py", "status", TASK], 0, "failed")
        expect("повтор завершённого шага запрещён", ["scripts/state.py", "done", TASK, "1"], 1)
        expect("профиль таблицы", ["scripts/analyze.py", TASK, "S002"], 0, "Пропусков")
        expect("отчёт о расходах", ["scripts/cost.py", "report", TASK], 0, "Итого")

        print("Реестр:")
        expect("факт без источника не записывается", ["scripts/evidence.py", "add", TASK, "--type", "fact",
               "--claim", "x", "--topics", "t"], 1, "без источника")
        expect("факт из синтетики не записывается", ["scripts/evidence.py", "add", TASK, "--type", "fact",
               "--claim", "x", "--topics", "t", "--source", "S003", "--where", "w"], 1, "синтетический")
        expect("корректный факт записывается", ["scripts/evidence.py", "add", TASK, "--type", "fact",
               "--claim", "Обновление 4.0 вышло 15.09.2026", "--topics", "notifications", "--source", "S001",
               "--where", "тест"], 0, "E010")

        print("База знаний:")
        expect("поиск по формулировке находит запись", ["scripts/evidence.py", "search", TASK,
               "жалобы на уведомления"], 0, "E005")
        expect("связи записи: где использована", ["scripts/evidence.py", "show", TASK, "E005"], 0, "situation.md:")

        print("Решения:")
        expect("решение записывается с основаниями", ["scripts/decision.py", "add", TASK, "--title", "Тест",
               "--grounds", "E005,E007", "--owner", "руководитель продукта", "--metric", "D30",
               "--review-if", "D30 не вырос", "--review-by", "2099-01-01"], 0, "D1")
        expect("просроченное обязательство видно", ["scripts/decision.py", "commit", TASK, "D1", "--what", "Запуск",
               "--owner", "команда", "--due", "2000-01-01"], 0, "C1")
        expect("«что решать» показывает просрочку", ["scripts/decision.py", "check", TASK], 0, "Просрочено")

        print("Пересмотр:")
        expect("новые данные находят затронутые выводы", ["scripts/revise.py", TASK, "E010"], 0, "situation.md")
        expect("отзыв записи", ["scripts/evidence.py", "revoke", TASK, "E007", "--by", "E010",
               "--reason", "тест"], 0)
        expect("валидатор ловит вывод на отозванной гипотезе", ["scripts/validate.py", TASK], 1, "отозвана")
        expect("отозванное основание решения помечено", ["scripts/decision.py", "check", TASK], 0,
               "Основание устарело")
        check("MCP-сервер отдаёт инструменты", mcp_tools_ok())

        print("Испорченные данные:")
        shutil.rmtree(tdir); shutil.copytree(PROJECTS / "_example", tdir)
        (tdir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        append_line(tdir / "situation.md", "- Рынок вырос на 12% [E099].")
        expect("метка на несуществующую запись", ["scripts/validate.py", TASK], 1, "E099")
        shutil.copyfile(PROJECTS / "_example" / "situation.md", tdir / "situation.md")
        (tdir / "product-strategy.md").write_text("# П\n\n**P1.** Пользователь сам выбирает частоту [E005].\n", encoding="utf-8")
        (tdir / "comms-strategy.md").write_text("# К\n\n## Подтверждение\n\n- Гарантируем рост мотивации [P7].\n", encoding="utf-8")
        expect("обещание без пункта продукта", ["scripts/validate.py", TASK], 1, "P7")
        (tdir / "comms-strategy.md").write_text("# К\n\n## Подтверждение\n\n- Напоминания — когда удобно вам [P1].\n", encoding="utf-8")
        append_line(tdir / "situation.md", "- Конверсия 5% у новых пользователей.")
        expect("число без источника — предупреждение", ["scripts/validate.py", TASK], 0, "число без метки")

        print("Отчёт:")
        (tdir / "summary.md").write_text("# Кратко\n\n**Рекомендуем:** вернуть настройку частоты [E005].\n", encoding="utf-8")
        expect("сборка отчёта", ["scripts/build_report.py", TASK], 0, "Собран report.md")
        rpath = tdir / "report.md"
        report = rpath.read_text(encoding="utf-8") if rpath.exists() else ""
        check("в отчёте раскрыты метки и источники", "Приложение А" in report and "S001" in report)

        print("Требования брифа:")
        (tdir / "requirements.md").write_text(
            "# Требования\n\n- **R1.** Назвать первых клиентов — S001\n- **R2.** План по кварталам — S001\n",
            encoding="utf-8")
        (tdir / "deliverable.md").write_text(
            "# Итог\n\n## 1. Клиент\n\nПервые клиенты — новые пользователи [E005]. [R1]\n", encoding="utf-8")
        expect("непокрытое требование — ошибка", ["scripts/validate.py", TASK], 1, "R2")
        append_line(tdir / "deliverable.md", "\n## 2. План\n\nПервый квартал — проверка [E005]. [R2]")
        expect("все требования закрыты", ["scripts/validate.py", TASK], 0, "Проверка пройдена")
        expect("отчёт по структуре брифа", ["scripts/build_report.py", TASK], 0, "deliverable.md")
        expect("чистая версия для руководителя", ["scripts/build_report.py", TASK, "--clean"], 0, "report-clean.md")
        clean = (tdir / "report-clean.md").read_text(encoding="utf-8")
        check("в чистой версии нет служебных меток, есть сноски", "[R1]" not in clean and "[E005]" not in clean and "[^1]" in clean)
    finally:
        shutil.rmtree(tdir, ignore_errors=True)

    failed = [r for r in results if not r[1]]
    print(f"\nПройдено {len(results) - len(failed)} из {len(results)}.")
    return 1 if failed else 0


if __name__ == "__main__":
    main_wrapper(main)
