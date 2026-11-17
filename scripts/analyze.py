"""Проверка таблицы перед расчётами: столбцы, типы, пропуски, периоды, дубли.

  python scripts/analyze.py <task> <S…|путь к CSV внутри задачи>

Сам расчёт агент пишет отдельным скриптом в projects/<task>/calc/<имя>.py, который читает
CSV из sources/ и печатает результат; в evidence.jsonl в поле where указывается
«calc/<имя>.py», чтобы любую цифру можно было пересчитать одной командой.
"""
from __future__ import annotations

import argparse
import re

import pandas as pd

from common import ToolError, load_sources, main_wrapper, task_dir


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task"); p.add_argument("table")
    a = p.parse_args()
    tdir = task_dir(a.task)
    if re.fullmatch(r"S\d+", a.table):
        s = next((s for s in load_sources(tdir) if s["id"] == a.table), None)
        if not s:
            raise ToolError(f"Источник {a.table} не найден.")
        path = tdir / s["local"]
    else:
        path = tdir / a.table
    if path.suffix.lower() != ".csv" or not path.exists():
        raise ToolError(f"Нужен CSV-файл задачи, а не {path.name}. XLSX сначала добавьте через extract.py.")

    df = pd.read_csv(path)
    print(f"{path.name}: строк {len(df)}, столбцов {len(df.columns)}")
    dup = int(df.duplicated().sum())
    if dup:
        print(f"⚠ полных дублей строк: {dup}")
    print("\n| Столбец | Тип | Пропусков | Мин | Макс | Пример |\n| --- | --- | ---: | --- | --- | --- |")
    for col in df.columns:
        s = df[col]
        miss = int(s.isna().sum())
        if pd.api.types.is_numeric_dtype(s):
            lo, hi = s.min(), s.max()
        else:
            lo = hi = ""
        example = s.dropna().iloc[0] if s.notna().any() else ""
        print(f"| {col} | {s.dtype} | {miss} | {lo} | {hi} | {example} |")

    for col in df.columns:
        vals = df[col].dropna().astype(str)
        if len(vals) and vals.str.fullmatch(r"\d{4}-\d{2}(-\d{2})?").all():
            per = pd.to_datetime(vals, errors="coerce").sort_values()
            gaps = per.diff().dt.days.dropna()
            print(f"\nПериод в «{col}»: {vals.min()} … {vals.max()}, значений {len(vals)}"
                  + (f"; ⚠ неравные интервалы ({int(gaps.min())}–{int(gaps.max())} дн.)"
                     if len(gaps) and gaps.max() - gaps.min() > 3 else ""))
    print("\nПроверьте перед расчётом: единицы (доли или %, рубли или тыс.), период каждой строки, "
          "что означают пропуски (нет данных ≠ ноль).")
    return 0


if __name__ == "__main__":
    main_wrapper(main)
