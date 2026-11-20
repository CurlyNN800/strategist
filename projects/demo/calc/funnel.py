"""Сведение подключений семейных групп за плановый год: начало + новые − выбывшие = конец.
Без изменений и с вариантом 6. Входы — бриф [E005][E007], остальное — допущения D10, D16–D18.

  python projects/demo/calc/funnel.py
"""
START, END_NC = 6500, 8000          # [E005]
CREATED = 6000                      # D10 [E044]
ACCEPT = 0.50                       # D18: доля созданных групп, где приглашение приняли
ACTIVATION = 0.45                   # без изменений [E007]
CHANNELS = {"приложение (экран создания группы)": 0.70, "сотрудники продаж": 0.20, "служба поддержки": 0.10}  # D17
ANYWAY = {"приложение (экран создания группы)": 0.6, "сотрудники продаж": 0.4, "служба поддержки": 0.5}  # D21: доля, создавших бы группу и без показа
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from options import row  # noqa: E402

V6_EXTRA_CONNECTED, V6_EXTRA_ACTIVE, ACTIVE_NC = round(row(0)["v6c"]), round(row(0)["v6a"]), 5000   # options.py, [E039]


def main():
    new = CREATED * ACCEPT
    churn = START + new - END_NC
    print("Без изменений:")
    print(f"  создано групп {CREATED}; приняли приглашение {ACCEPT:.0%} → новых подключённых {new:.0f}; "
          f"активировано за 14 дней {CREATED * ACTIVATION:.0f} ({ACTIVATION:.0%})")
    print(f"  {START} + {new:.0f} − {churn:.0f} (выбыли, {churn / START:.0%} от начала года) = {END_NC}")
    print("  по каналам (правило отнесения: последний канал, где организатор увидел предложение за 30 дней до создания группы):")
    for ch, s in CHANNELS.items():
        conn = new * s
        print(f"    {ch:36s}: создано {CREATED * s:>5.0f}, подключено {conn:>5.0f}, первое действие {CREATED * s * ACTIVATION:>5.0f}, "
              f"создано благодаря показу предложения (сейчас) {conn * (1 - ANYWAY[ch]):>4.0f}")
    end6 = END_NC + V6_EXTRA_CONNECTED
    print("\nВариант 6:")
    print(f"  {START} + {new + V6_EXTRA_CONNECTED:.0f} − {churn:.0f} = {end6} (прирост к «без изменений» +{V6_EXTRA_CONNECTED} — "
          f"только за счёт лучшего запуска, а не всех подключений года)")
    active6 = ACTIVE_NC + V6_EXTRA_ACTIVE
    from_count = V6_EXTRA_CONNECTED * ACTIVE_NC / END_NC
    print(f"  активные: {ACTIVE_NC} + {V6_EXTRA_ACTIVE} = {active6} = {active6 / end6:.1%} от {end6} подключённых")
    print(f"  из прироста активных: {from_count:.0f} — от числа групп, {V6_EXTRA_ACTIVE - from_count:.0f} — от роста доли активных")
    print(f"\nРазрыв к цели 12 000 подключённых: {12000 - end6}; к цели 8 000 активных: {8000 - active6}")
    print(f"Даже при нулевом уходе групп: +{churn:.0f}; через долю принятых приглашений нужно +{(12000 - end6) / CREATED:.0%} п.п.")
    for price in (2, 5):
        print(f"Цена закрытия разрыва привлечением при {price} тыс. руб. за новую подключённую группу: "
              f"{(12000 - end6) * price / 1000:.1f} млн руб. (допущение о цене)")


if __name__ == "__main__":
    main()
