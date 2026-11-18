"""Хук Claude Code (событие Stop): автоматически пишет токены в cost.csv активной задачи.

Подключён в .claude/settings.json. Активная задача — та, чей state.json менялся последним
(не считая _example). Хук никогда не мешает работе: при любой ошибке молча выходит с кодом 0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from common import PROJECTS, load_state, now_iso
    from cost import append_row, load_models, price_usd, resolve_model

    event = json.loads(sys.stdin.read() or "{}")
    transcript = Path(event.get("transcript_path", ""))
    if not transcript.is_file():
        return
    states = [p for p in PROJECTS.glob("*/state.json") if p.parent.name != "_example"]
    if not states:
        return
    tdir = max(states, key=lambda p: p.stat().st_mtime).parent
    stage = load_state(tdir)["stage"]

    cursor_path = tdir / ".cost_cursor.json"
    cursor = json.loads(cursor_path.read_text(encoding="utf-8")) if cursor_path.exists() else {}

    # Основной диалог + транскрипты субагентов (<сессия>/subagents/*.jsonl): без них не видно,
    # что извлечение фактов шло на дешёвой модели.
    files = [transcript, *sorted(transcript.with_suffix("").glob("subagents/*.jsonl"))]
    totals: dict[str, list[int]] = {}
    for path in files:
        key = str(path)
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[cursor.get(key, 0):]:
            try:
                msg = json.loads(line).get("message") or {}
            except json.JSONDecodeError:
                continue
            usage = msg.get("usage") if isinstance(msg, dict) else None
            if not usage:
                continue
            t = totals.setdefault(msg.get("model", "unknown"), [0, 0, 0])
            t[0] += usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
            t[1] += usage.get("output_tokens", 0)
            t[2] += usage.get("cache_read_input_tokens", 0)
        cursor[key] = len(lines)

    cfg = load_models()
    for model, (inp, out, cache_read) in totals.items():
        name, mcfg = resolve_model(model, cfg)
        usd = price_usd(mcfg, inp, out, cache_read)
        append_row(tdir, {"timestamp": now_iso(), "step_id": "", "stage": stage, "model": name,
                          "input_tokens": inp + cache_read, "output_tokens": out,
                          "usd": "" if usd is None else usd, "estimated": "false"})
    cursor_path.write_text(json.dumps(cursor), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # хук не должен ломать сессию
        pass
    sys.exit(0)
