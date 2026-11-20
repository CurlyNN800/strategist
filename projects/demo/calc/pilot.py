"""Пилот выбранного изменения: размер, темп набора с убыванием пула, сроки от реальной даты старта (1 июня, D22).
n ≈ 16·p·(1−p)/d² на вариант (α = 5 %, мощность 80 %, knowledge/methods/experiments.md). Единица — семейная группа.
Проверка А (запуск) — только новые группы; проверка Б (сигнал) — только группы, созданные до пилота: схемы не пересекаются.

  python projects/demo/calc/pilot.py
"""
from math import ceil, log, sqrt

CREATED_PER_MONTH = 6000 / 12    # D10 [E044]
ACTIVATION_NC = 0.45             # [E007]
CONNECTED_Q2 = 7250              # средн. подключённых групп [E005]
SCEN = {"основной": (0.6, 0.4), "неблагоприятный": (0.45, 0.3)}   # D2 доля подходящих, D6 доля групп с низким остатком за месяц
LIMIT_RATE, DE = 0.25, 1.2       # D13 [E047]


def n_arm(p, d, de=1.0):
    return ceil(16 * p * (1 - p) / d ** 2 * de)


def mde(p, n, de=1.0):
    return sqrt(16 * p * (1 - p) * de / n)


def main():
    print("Проверка А. Запуск группы (новые группы с 1 июня, окно 14 дней, набор заканчивается за 14 дней до даты решения)")
    for date, months in (("30.09", 3.5), ("30.11", 5.5)):
        n = CREATED_PER_MONTH * months / 2
        print(f"  к {date}: ~{n:.0f} групп на вариант → различим рост от {mde(ACTIVATION_NC, n):.1%}")
    print(f"  для +5 п.п. нужно {n_arm(ACTIVATION_NC, 0.05)} на вариант = {2 * n_arm(ACTIVATION_NC, 0.05) / CREATED_PER_MONTH:.1f} мес. набора")

    print("\nПроверка Б. Сигнал до перебоя (группы, созданные до пилота; окно 7 дней)")
    need = 2 * n_arm(LIMIT_RATE, 0.05, DE)
    for name, (elig, monthly) in SCEN.items():
        pool = CONNECTED_Q2 * elig
        weekly = monthly / 4.3
        share = need / pool
        if share >= 1:
            print(f"  {name}: пул {pool:.0f} групп меньше нужных {need} — −5 п.п. не различить; предел {mde(LIMIT_RATE, pool / 2, DE):.1%}")
            continue
        weeks = log(1 - share) / log(1 - weekly)
        print(f"  {name}: пул {pool:.0f} групп, нужно {need} ({share:.0%}); с убыванием пула набор {weeks:.0f} нед. + 7 дней; "
              f"предел при всём пуле {mde(LIMIT_RATE, pool / 2, DE):.1%}")


if __name__ == "__main__":
    main()
