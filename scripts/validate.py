"""Проверка задачи перед показом результата пользователю.

  python scripts/validate.py <task> [--strict]

ОШИБКИ (код выхода 1) — результат показывать нельзя:
  - state.json или записи evidence.jsonl не соответствуют схемам; повторяющиеся id;
  - fact без источника, ссылка на несуществующий источник, нет файла источника;
  - fact из синтетического источника;
  - метка [E…] в тексте ведёт на несуществующую запись;
  - метка отозванной записи используется вне раздела «Отброшено»;
  - метка [P…] в comms-strategy.md не найдена в product-strategy.md.
ПРЕДУПРЕЖДЕНИЯ (с --strict тоже ошибки):
  - строка с числом без метки [E…]/[P…];
  - синтетическая запись цитируется без слова «синтетика»;
  - в options.md меньше трёх вариантов или нет «оставить как есть»;
  - обещание в comms-strategy.md без ссылки на пункт продукта;
  - файл источника изменился после загрузки (sha256).
"""
from __future__ import annotations

import argparse
import json
import re

from jsonschema import Draft202012Validator

from common import SCHEMAS, ToolError, load_evidence, load_sources, main_wrapper, sha256_file, task_dir

E_RE = re.compile(r"\[(E\d{3,})\]")
P_RE = re.compile(r"\[(P\d+)\]")
P_DEF_RE = re.compile(r"\*\*(P\d+)\.\*\*")
RESULT_FILES = ["situation.md", "options.md", "decision.md", "product-strategy.md",
                "comms-strategy.md", "validation-plan.md", "decisions.md", "summary.md"]
NUMBER_CHECK_FILES = {"situation.md", "options.md", "product-strategy.md", "comms-strategy.md",
                      "validation-plan.md", "summary.md"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task"); p.add_argument("--strict", action="store_true")
    a = p.parse_args()
    tdir = task_dir(a.task)
    errors: list[str] = []
    warnings: list[str] = []

    # --- state.json ---
    st_schema = json.loads((SCHEMAS / "state.schema.json").read_text(encoding="utf-8"))
    try:
        state = json.loads((tdir / "state.json").read_text(encoding="utf-8"))
        for e in Draft202012Validator(st_schema).iter_errors(state):
            errors.append(f"state.json: {'/'.join(map(str, e.path)) or '(корень)'}: {e.message}")
    except FileNotFoundError:
        errors.append("state.json: файла нет")

    # --- sources.yaml ---
    sources = {s["id"]: s for s in load_sources(tdir)}
    for sid, s in sources.items():
        local = tdir / s.get("local", "")
        if not s.get("local") or not local.is_file():
            errors.append(f"sources.yaml: {sid}: нет локальной копии {s.get('local')}")
        elif s.get("sha256") and sha256_file(local) != s["sha256"]:
            warnings.append(f"sources.yaml: {sid}: файл {s['local']} изменился после загрузки (sha256 не совпадает)")

    # --- evidence.jsonl ---
    ev_schema = json.loads((SCHEMAS / "evidence.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(ev_schema)
    evidence: dict[str, dict] = {}
    for rec in load_evidence(tdir):
        rid = rec.get("id", "?")
        if rid in evidence:
            errors.append(f"evidence.jsonl: {rid}: id повторяется")
        evidence[rid] = rec
        for e in validator.iter_errors(rec):
            errors.append(f"evidence.jsonl: {rid}: {'/'.join(map(str, e.path)) or 'запись'}: {e.message}")
        src = rec.get("source")
        if src and src not in sources:
            errors.append(f"evidence.jsonl: {rid}: источник {src} не найден в sources.yaml")
        if rec.get("type") == "fact" and src in sources and sources[src].get("kind") == "synthetic":
            errors.append(f"evidence.jsonl: {rid}: тип fact, но источник {src} синтетический — должен быть synthetic")
        if rec.get("type") == "synthetic" and src in sources and sources[src].get("kind") not in ("synthetic",):
            warnings.append(f"evidence.jsonl: {rid}: тип synthetic, но источник {src} не помечен kind: synthetic")

    # --- метки в текстах ---
    p_defs: set[str] = set()
    prod = tdir / "product-strategy.md"
    if prod.exists():
        p_defs = set(P_DEF_RE.findall(prod.read_text(encoding="utf-8")))

    for name in RESULT_FILES:
        path = tdir / name
        if not path.exists():
            continue
        section = ""
        in_code = False
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            if line.startswith("#"):
                section = line.lower()
                continue
            where = f"{name}:{n}"
            if "[E…]" in line or "[P…]" in line or re.search(r"<[^>]*…[^>]*>", line):
                warnings.append(f"{where}: незаполненное место из шаблона: «{line.strip()[:60]}»")
            e_refs = E_RE.findall(line)
            for rid in e_refs:
                rec = evidence.get(rid)
                if not rec:
                    errors.append(f"{where}: метка [{rid}] — такой записи нет в evidence.jsonl")
                elif rec.get("status") == "revoked" and name in ("decision.md", "decisions.md") \
                        and "устарел" not in line.lower():
                    errors.append(f"{where}: основание решения [{rid}] отозвано ({rec.get('revoked_reason')}). "
                                  f"Решение не меняйте сами: сообщите пользователю и запишите рядом «основание устарело»")
                elif rec.get("status") == "revoked" and name not in ("decision.md", "decisions.md") \
                        and "отброш" not in section and "отозван" not in line.lower():
                    errors.append(f"{where}: [{rid}] отозвана ({rec.get('revoked_reason')}) — обновите вывод "
                                  f"или перенесите в раздел «Отброшено»")
                elif rec.get("type") == "synthetic" and "синтет" not in line.lower():
                    warnings.append(f"{where}: [{rid}] — синтетика; прямо назовите её синтетикой, "
                                    f"она не подтверждает спрос")
            p_refs = P_RE.findall(line)
            if name == "comms-strategy.md":
                for pid in p_refs:
                    if pid not in p_defs:
                        errors.append(f"{where}: [{pid}] — в product-strategy.md нет пункта **{pid}.**")
                if re.search(r"обеща|сообщени|подтвержд", section) and line.strip().startswith(("-", "*", "1", "2", "3")) \
                        and not p_refs:
                    warnings.append(f"{where}: обещание без ссылки на пункт продукта [P…]")
            if name in NUMBER_CHECK_FILES and re.search(r"\d", line) and not e_refs and not p_refs:
                stripped = line.strip()
                if stripped and not re.fullmatch(r"\|?[\s|:-]+\|?", stripped) \
                        and not re.fullmatch(r"[-*]?\s*\[[ x]\].*", stripped) \
                        and re.search(r"\d+[.,]?\d*\s*(%|п\.п\.|руб|₽|\$|млн|млрд|тыс|раз|пользоват|отзыв|человек|дн)", stripped):
                    warnings.append(f"{where}: число без метки [E…]: «{stripped[:80]}»")

    # --- варианты ---
    opts = tdir / "options.md"
    if opts.exists():
        text = opts.read_text(encoding="utf-8")
        n_opts = len(re.findall(r"^##\s+(Вариант|В\d|\d)", text, flags=re.M | re.I))
        if n_opts < 3:
            warnings.append(f"options.md: найдено вариантов: {n_opts} (заголовки «## Вариант …»), нужно не меньше трёх")
        if "оставить как есть" not in text.lower():
            warnings.append("options.md: нет варианта «Оставить как есть»")

    # --- итог ---
    for e in errors:
        print(f"ОШИБКА  {e}")
    for w in warnings:
        print(f"ВНИМАНИЕ {w}")
    used = {rid for name in RESULT_FILES if (tdir / name).exists()
            for rid in E_RE.findall((tdir / name).read_text(encoding="utf-8"))}
    print(f"\nИтог: ошибок {len(errors)}, предупреждений {len(warnings)}. "
          f"Записей в реестре: {len(evidence)}, из них цитируется: {len(used & set(evidence))}. "
          f"Источников: {len(sources)}.")
    if errors or (a.strict and warnings):
        print("Результат показывать нельзя — исправьте ошибки и запустите проверку снова.")
        return 1
    print("Проверка пройдена.")
    return 0


if __name__ == "__main__":
    main_wrapper(main)
