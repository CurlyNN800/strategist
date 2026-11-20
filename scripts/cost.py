"""Учёт стоимости задачи.

  python scripts/cost.py add <task> --model M --in N --out N [--step S] [--stage E] [--usd X]
  python scripts/cost.py add <task> --model M --chars N [--step S]   оценка по длине текста (estimated=true)
  python scripts/cost.py report <task>

Цены моделей — config/models.yaml. Если среда не отдаёт токены, используйте --chars:
токены оцениваются как символы / 3 (грубо для русского текста) и помечаются estimated.
В Claude Code токены пишутся автоматически хуком scripts/hooks/claude_cost_hook.py.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import yaml

from common import ROOT, ToolError, load_state, main_wrapper, now_iso, task_dir

FIELDS = ["timestamp", "step_id", "stage", "model", "input_tokens", "output_tokens", "usd", "estimated"]


def load_models() -> dict:
    path = ROOT / "config" / "models.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {"models": {}}


def resolve_model(name: str, cfg: dict) -> tuple[str, dict | None]:
    models = cfg.get("models") or {}
    if name in models:
        return name, models[name]
    for key, m in models.items():
        if any(sub and sub.lower() in name.lower() for sub in (m.get("match") or [])):
            return key, m
    return name, None


def price_usd(model_cfg: dict | None, inp: int, out: int, cache_read: int = 0) -> float | None:
    if not model_cfg or model_cfg.get("input") is None or model_cfg.get("output") is None:
        return None
    cr = model_cfg.get("cache_read") if model_cfg.get("cache_read") is not None else model_cfg["input"]
    return round((inp * model_cfg["input"] + out * model_cfg["output"] + cache_read * cr) / 1_000_000, 5)


def append_row(tdir: Path, row: dict) -> None:
    path = tdir / "cost.csv"
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def cmd_add(a) -> None:
    tdir = task_dir(a.task)
    state = load_state(tdir)
    estimated = a.chars is not None
    if estimated:
        inp, out = a.chars // 3, 0
    elif a.inp is None or a.out is None:
        raise ToolError("Укажите --in и --out (токены) или --chars (оценка по длине текста).")
    else:
        inp, out = a.inp, a.out
    key, mcfg = resolve_model(a.model, load_models())
    usd = a.usd if a.usd is not None else price_usd(mcfg, inp, out)
    append_row(tdir, {"timestamp": now_iso(), "step_id": a.step or "", "stage": a.stage or state["stage"],
                      "model": key, "input_tokens": inp, "output_tokens": out,
                      "usd": "" if usd is None else usd, "estimated": str(estimated).lower()})
    msg = f"Записано: {key}, {inp} вх. / {out} вых. токенов"
    msg += f", ${usd}" if usd is not None else " — цена модели не задана в config/models.yaml"
    print(msg)


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def cmd_report(a) -> None:
    tdir = task_dir(a.task)
    path = tdir / "cost.csv"
    if not path.exists():
        print("Расходов пока нет.")
        return
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        print("Расходов пока нет.")
        return
    by_stage, by_model = defaultdict(lambda: [0, 0, 0.0]), defaultdict(lambda: [0, 0, 0.0])
    tot = [0, 0, 0.0]
    unpriced = est = 0
    for r in rows:
        i, o = int(r["input_tokens"] or 0), int(r["output_tokens"] or 0)
        u = float(r["usd"]) if r["usd"] else 0.0
        unpriced += not r["usd"]
        est += r["estimated"] == "true"
        for bucket in (by_stage[r["stage"]], by_model[r["model"]], tot):
            bucket[0] += i; bucket[1] += o; bucket[2] += u

    def table(title: str, data: dict) -> None:
        print(f"\n| {title} | Вход, токенов | Выход, токенов | $ |\n| --- | ---: | ---: | ---: |")
        for k, (i, o, u) in sorted(data.items()):
            print(f"| {k} | {fmt(i)} | {fmt(o)} | {u:.3f} |")

    tok_txt = (f"{fmt(tot[0])} входных токенов, выходные не измерены" if tot[1] == 0 and est
               else f"{fmt(tot[0])} входных и {fmt(tot[1])} выходных токенов")
    print(f"**Итого: ${tot[2]:.3f}** — {tok_txt}, записей: {len(rows)}.")
    table("Этап", by_stage)
    table("Модель", by_model)
    if est:
        print(f"\nОценочных записей (среда не отдала токены): {est}.")
    if unpriced:
        print(f"Записей без цены: {unpriced} — впишите цены в config/models.yaml.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add"); s.add_argument("task"); s.add_argument("--model", required=True)
    s.add_argument("--in", dest="inp", type=int); s.add_argument("--out", type=int)
    s.add_argument("--chars", type=int); s.add_argument("--usd", type=float)
    s.add_argument("--step", type=int); s.add_argument("--stage"); s.set_defaults(fn=cmd_add)
    s = sub.add_parser("report"); s.add_argument("task"); s.set_defaults(fn=cmd_report)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main_wrapper(main)
