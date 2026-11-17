"""Общие функции для скриптов агента. Форматы — docs/architecture.md."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
SCHEMAS = ROOT / "docs" / "schemas"

STAGES = ["01-intake", "02-collect", "03-research", "04-options",
          "05-decision", "06-strategy", "07-validation"]

MSK = timezone(timedelta(hours=3))

# Windows-консоль по умолчанию не всегда печатает кириллицу
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


class ToolError(Exception):
    """Ошибка, о которой нужно понятно сообщить агенту (код выхода 1)."""


def now_iso() -> str:
    return datetime.now(MSK).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(MSK).date().isoformat()


def task_dir(task_id: str, must_exist: bool = True) -> Path:
    if not re.fullmatch(r"_?[a-z0-9][a-z0-9-]*", task_id):
        raise ToolError(f"Некорректный task_id «{task_id}»: латиница в нижнем регистре, цифры, дефис.")
    path = PROJECTS / task_id
    if must_exist and not path.is_dir():
        raise ToolError(f"Задача «{task_id}» не найдена: нет папки {path.relative_to(ROOT)}. "
                        f"Создайте её: python scripts/state.py init {task_id} \"<вопрос>\"")
    return path


# ---------- state.json ----------

def load_state(tdir: Path) -> dict:
    path = tdir / "state.json"
    if not path.exists():
        raise ToolError(f"Нет файла {path.relative_to(ROOT)}.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(tdir: Path, state: dict) -> None:
    state["updated"] = now_iso()
    tmp = tdir / "state.json.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(tdir / "state.json")  # атомарная замена: файл не останется полузаписанным


# ---------- log.md ----------

def append_log(tdir: Path, step: int | str, stage: str, status: str, text: str) -> None:
    path = tdir / "log.md"
    if not path.exists():
        path.write_text("# Журнал задачи\n\n", encoding="utf-8")
    stamp = datetime.now(MSK).strftime("%Y-%m-%d %H:%M")
    step_txt = f"step {step}" if step != "" else "-"
    line = f"{stamp} | {step_txt} | {stage} | {status} | {text}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


# ---------- sources.yaml ----------

def load_sources(tdir: Path) -> list[dict]:
    path = tdir / "sources.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or []


def save_sources(tdir: Path, sources: list[dict]) -> None:
    header = "# Реестр источников задачи. Формат: docs/architecture.md §5\n"
    body = yaml.safe_dump(sources, allow_unicode=True, sort_keys=False, width=1000)
    (tdir / "sources.yaml").write_text(header + body, encoding="utf-8")


def next_source_id(sources: list[dict]) -> str:
    nums = [int(s["id"][1:]) for s in sources if re.fullmatch(r"S\d+", str(s.get("id", "")))]
    return f"S{(max(nums) + 1) if nums else 1:03d}"


def sha256_file(path: Path) -> str:
    """Хэш содержимого. Переводы строк приводятся к LF: Git на Windows меняет их на CRLF,
    и без этого хэш текстового источника «менялся» бы после клонирования."""
    data = path.read_bytes()
    if path.suffix.lower() in {".md", ".txt", ".csv", ".json", ".jsonl", ".yaml", ".yml", ".html"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


# ---------- evidence.jsonl ----------

def load_evidence(tdir: Path) -> list[dict]:
    path = tdir / "evidence.jsonl"
    if not path.exists():
        return []
    records = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ToolError(f"evidence.jsonl, строка {n}: не JSON ({e.msg}).")
    return records


def main_wrapper(fn) -> None:
    """Запуск команды: понятная ошибка и код выхода 1 вместо трассировки."""
    try:
        code = fn()
        sys.exit(code or 0)
    except ToolError as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        sys.exit(1)
