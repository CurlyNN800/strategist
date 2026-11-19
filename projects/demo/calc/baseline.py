"""Разбор исходных показателей брифа S001 (стр. 3). Все входы — из таблицы брифа [E003]–[E007].

  python projects/demo/calc/baseline.py
"""
# Базовый год: план / оценка; плановый год: без изменений / цель
ACTIVE = dict(plan=5000, est=4000, nochange=5000, target=8000)        # E004
CONNECTED = dict(plan=7500, est=6500, nochange=8000, target=12000)    # E005
OWNERS = dict(plan=1000, est=800, nochange=1000, target=2000)         # E006
ACTIVATION = dict(plan=0.50, est=0.42, nochange=0.45, target=0.60)    # E007
PROFIT = dict(plan=282, est=275, nochange=279, target=285)            # E003, млн руб.
HOUSEHOLDS_AVAILABLE, OWNERS_AVAILABLE = 100_000, 40_000              # E002
PROFIT_PER_EXTRA_MONTH = 500                                          # E015, руб.


def share(a, c):
    return a / c


def main():
    print("1. Доля активных среди подключённых групп")
    for k in ("plan", "est", "nochange", "target"):
        print(f"   {k:9s}: {ACTIVE[k]:>5} / {CONNECTED[k]:>6} = {share(ACTIVE[k], CONNECTED[k]):.1%}")

    print("\n2. Разложение отставания базового года по активным группам (оценка − план)")
    gap = ACTIVE["est"] - ACTIVE["plan"]
    s_plan, s_est = share(ACTIVE["plan"], CONNECTED["plan"]), share(ACTIVE["est"], CONNECTED["est"])
    from_count = (CONNECTED["est"] - CONNECTED["plan"]) * s_plan
    from_share = CONNECTED["est"] * (s_est - s_plan)
    print(f"   всего: {gap:+.0f} групп")
    print(f"   из-за меньшего числа подключённых: {from_count:+.0f} ({from_count / gap:.0%})")
    print(f"   из-за меньшей доли активных:       {from_share:+.0f} ({from_share / gap:.0%})")

    print("\n3. Что требует цель планового года по активности")
    need_share = share(ACTIVE["target"], CONNECTED["target"])
    print(f"   при 12 000 подключённых нужна доля активных {need_share:.1%} "
          f"(без изменений {share(ACTIVE['nochange'], CONNECTED['nochange']):.1%})")
    print(f"   если подключённых останется 8 000, для 8 000 активных нужна доля {ACTIVE['target'] / CONNECTED['nochange']:.0%} — невозможно")

    print("\n4. Подключения: путь к цели")
    net = CONNECTED["target"] - CONNECTED["est"]
    gap_nc = CONNECTED["target"] - CONNECTED["nochange"]
    print(f"   чистый прирост к цели: {net:+} групп; разрыв к прогнозу без изменений: {gap_nc:+}")
    print(f"   владельцы: цель {OWNERS['target']} против {OWNERS['nochange']} без изменений, разрыв {OWNERS['target'] - OWNERS['nochange']:+}")

    print("\n5. Охват доступной базы")
    for name, n, base in [("семьи, оценка базового года", CONNECTED["est"], HOUSEHOLDS_AVAILABLE),
                          ("семьи, цель", CONNECTED["target"], HOUSEHOLDS_AVAILABLE),
                          ("владельцы, оценка", OWNERS["est"], OWNERS_AVAILABLE),
                          ("владельцы, цель", OWNERS["target"], OWNERS_AVAILABLE)]:
        print(f"   {name:28s}: {n:>6} / {base:>6} = {n / base:.1%}")

    print("\n6. Прибыль")
    need = (PROFIT["target"] - PROFIT["nochange"]) * 1e6
    print(f"   не хватает {need / 1e6:.0f} млн руб. = {need / PROFIT_PER_EXTRA_MONTH:,.0f} доп. оплаченных месяцев по {PROFIT_PER_EXTRA_MONTH} руб.".replace(",", " "))
    print(f"   отставание базового года: {PROFIT['est'] - PROFIT['plan']:+} млн руб. ({(PROFIT['est'] - PROFIT['plan']) / PROFIT['plan']:.1%})")


if __name__ == "__main__":
    main()
