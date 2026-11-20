"""Мост прибыли, граница решения, вложения и окупаемость выбранного изменения. Числа эффекта — из options.py,
календарь — D22. Входы — бриф [E…] и допущения D… (hypothesis).

  python projects/demo/calc/profit.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from options import row, EFFECT_MONTHS, MONTH_PROFIT, S  # noqa: E402

BASE, TARGET = 279.0, 285.0        # [E003]
WARN_PER_MONTH = 7250 * 0.6 * 0.4  # D2, D6: предупреждений в месяц на всех подходящих группах
SMS_SHARE, SMS_COST = 0.3, 1.5     # D14
SUPPORT = 200 / 6 * 150            # D14: 200 спорных обращений за полгода × 150 руб. — в месяц
PM_COST = 0.4                      # D15, млн руб. за чел.-мес.
ROLES = {"разработка (апрель — 15 мая)": {2: 2.5}, "тестирование (до 31 мая)": {2: 0.5},
         "дизайнер 0,5 ставки, Q1–Q2": {1: 1.5, 2: 1.5}, "аналитик 0,5 ставки, Q1–Q4": {1: 1.5, 2: 1.5, 3: 1.5, 4: 1.5}}


def direct(months):
    """Прямые расходы, млн руб.: SMS по предупреждениям + спорные обращения."""
    return months * (WARN_PER_MONTH * SMS_SHARE * SMS_COST + SUPPORT) / 1e6


def main():
    print(f"Мост прибыли планового года (эффект {EFFECT_MONTHS} «полных» месяца), млн руб.")
    d = direct(EFFECT_MONTHS)
    print(f"  прямые расходы: {WARN_PER_MONTH:.0f} предупр./мес × {SMS_SHARE:.0%} SMS × {SMS_COST} руб. + "
          f"{200 / 6:.0f} обращ./мес × 150 руб. = {d / EFFECT_MONTHS:.3f} млн/мес × {EFFECT_MONTHS} мес. = {d:.3f}")
    for i, name in enumerate(("основной", "неблагоприятный")):
        m = row(i)["v3"]
        gain = m * MONTH_PROFIT / 1e6
        print(f"  {name:15s}: {BASE} + {gain:.3f} ({m:.0f} доп. мес. × 500 руб.) − {d:.3f} = {BASE + gain - d:.2f}; до цели {TARGET - (BASE + gain - d):.2f}")
    need = (TARGET - BASE) * 1e6 / MONTH_PROFIT + d * 1e6 / MONTH_PROFIT
    prevented = row(0)["prevented"]
    print(f"\nГраница: нужно {need:,.0f} доп. месяцев; при {prevented:,.0f} предотвращённых перебоях это "
          f"{need / prevented:.1f} мес. на случай (допущено {S['months_saved'][0]})".replace(",", " "))

    print("\nЧувствительность (основной сценарий, по одному допущению):")
    g = row(0)["v3"] * MONTH_PROFIT / 1e6
    for label, gg, dd in (("охват 45 % вместо 60 %", g * 0.45 / 0.6, d * 0.45 / 0.6), ("0,1 мес. на перебой вместо 0,2", g / 2, d),
                          ("прямые расходы ×2", g, 2 * d)):
        print(f"  {label:32s}: {BASE + gg - dd:.2f}")

    print("\nВложения по ролям и кварталам:")
    q = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    total = 0.0
    for role, by_q in ROLES.items():
        pm = sum(by_q.values()); total += pm
        for k, v in by_q.items():
            q[k] += v * PM_COST
        print(f"  {role:32s}: {pm:.1f} чел.-мес. = {pm * PM_COST:.1f} млн руб.")
    print(f"  итого {total:.1f} чел.-мес. = {total * PM_COST:.1f} млн руб.; по кварталам: " + ", ".join(f"Q{k} {v:.1f}" for k, v in q.items()))

    print("\nОкупаемость (основной сценарий). Допущение: после расширения эффект и расходы держатся без затрат на сопровождение.")
    full_q = (row(0)["v3"] / EFFECT_MONTHS * 3) * MONTH_PROFIT / 1e6 - direct(3)   # квартал работы на всех подходящих
    cum_i = cum_g = 0.0
    year1 = row(0)["v3"] * MONTH_PROFIT / 1e6 - d
    gains = {1: 0, 2: 0, 3: year1 * 2.5 / 5.5, 4: year1 * 3 / 5.5}
    for k in range(1, 13):
        cum_i += q.get(k, 0)
        cum_g += gains.get(k, full_q)
        print(f"  Q{k:<2} вложения {cum_i:4.1f}  прибыль {cum_g:5.2f}  разница {cum_g - cum_i:+.2f}")
    left = cum_i - cum_g
    print(f"  после Q12 не хватает {left:.2f} млн; ещё ~{left / full_q:.0f} кв. → окупаемость примерно через {12 + left / full_q:.0f} кв.")
    print(f"  одна разработка (1,0 млн) окупается за ~{2 + 1.0 / full_q:.0f} кв.")

    dev_extra = row(0)["v6c"]
    print(f"\nСтоимость дополнительной подключённой группы: {total * PM_COST:.1f} млн / {dev_extra:.0f} = "
          f"{total * PM_COST * 1e6 / dev_extra / 1000:.0f} тыс. руб. (только разработка — {1.0e6 / dev_extra / 1000:.0f} тыс.)")


if __name__ == "__main__":
    main()
