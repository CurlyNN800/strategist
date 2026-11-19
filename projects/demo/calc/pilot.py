"""Размер и темп набора пилота варианта 6 (две проверки). Формула: n ≈ 16·p·(1−p)/d² на группу
(α = 5 %, мощность 80 %, knowledge/methods/experiments.md). Единица — семейная группа.

  python projects/demo/calc/pilot.py
"""
from math import ceil, sqrt

CREATED_PER_YEAR = 6000      # D10 [E044]
ACTIVATION_NC = 0.45         # без изменений [E007]
CONNECTED = 7250             # средн. подключённых групп в Q2: (6 500 + 8 000) / 2 [E005]
ELIGIBLE = 0.6               # D2 [E033]: доля групп, где помощь возможна (берём как долю номеров)
WARNED_PER_MONTH = 0.4       # D6 [E037]
LIMIT_RATE = 0.25            # D13: доля номеров с ограничением за 7 дней после первого низкого остатка — допущение
DESIGN_EFFECT = 1.2          # D13: ~2 участника на группу, результаты внутри группы связаны [E032]


def n_per_arm(p, d, de=1.0):
    return ceil(16 * p * (1 - p) / d ** 2 * de)


def main():
    print("Темп считаем по средней численности Q2; поток «впервые подходящих» со временем убывает — сроки ниже нижняя граница.")
    print("Проверка А. Запуск группы: доля активированных за 14 дней (все созданные группы, включая без ответа)")
    per_month = CREATED_PER_YEAR / 12
    for d in (0.05, 0.07):
        n = n_per_arm(ACTIVATION_NC, d)
        months = 2 * n / per_month
        print(f"  заметить +{d:.0%}: {n} групп на вариант, {2 * n} всего; при {per_month:.0f} новых групп в месяц — "
              f"набор {months:.1f} мес. + 14 дней наблюдения")
    enrol = 3 * per_month / 2
    mde = sqrt(16 * ACTIVATION_NC * (1 - ACTIVATION_NC) / enrol)
    print(f"  за 3 месяца 2-го квартала наберём ~{enrol:.0f} групп на вариант → заметим эффект от {mde:.1%} (п.п.)")
    enrol6 = 6 * per_month / 2
    print(f"  за Q2+Q3 (6 мес.) — ~{enrol6:.0f} на вариант → эффект от {sqrt(16 * ACTIVATION_NC * (1 - ACTIVATION_NC) / enrol6):.1%}")

    print("\nПроверка Б. Сигнал до перебоя: доля номеров с ограничением из-за исчерпания объёма за 7 дней после первого низкого остатка")
    weekly_first = CONNECTED * ELIGIBLE * WARNED_PER_MONTH / 4.3
    for d in (0.03, 0.05):
        n = n_per_arm(LIMIT_RATE, d, DESIGN_EFFECT)
        weeks = 2 * n / weekly_first
        print(f"  заметить −{d:.0%} при базе {LIMIT_RATE:.0%}: {n} групп на вариант, {2 * n} всего; "
              f"впервые подходящих групп в неделю ~{weekly_first:.0f} → набор {weeks:.1f} нед. + 7 дней наблюдения")


if __name__ == "__main__":
    main()
