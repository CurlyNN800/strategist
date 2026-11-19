"""Мост прибыли, граница решения и окупаемость варианта 6. Входы — бриф [E…] и допущения D… (hypothesis).

  python projects/demo/calc/profit.py
"""
BASE = 279.0                    # млн руб., без изменений [E003]
TARGET = 285.0                  # [E003]
MONTH = 500                     # руб. [E015]
EXTRA_MONTHS = {"основной": 587, "неблагоприятный": 55}   # calc/options.py, В6 = В3 по прибыли [E045]
WARNINGS_PER_YEAR = 8000 * 0.6 * 0.4 * 12 / 2   # D2, D6: предупреждений за полгода работы
SMS_SHARE, SMS_COST = 0.3, 1.5  # D14: 30 % предупреждений уходит SMS по 1,5 руб., остальные — push бесплатно
SUPPORT_EXTRA = 200 * 150       # D14: 200 доп. обращений по спорным операциям × 150 руб. за полгода
PM_COST = 0.4                   # D15: полная стоимость 1 чел.-мес., млн руб.
DEV_PM, TEST_PM = 2.5, 0.5       # разработка и тестирование [E046]
DESIGN_PM = ANALYST_PM = 0.5 * 6  # по 0,5 ставки на Q1–Q2: 0,5 × 6 мес. = 3 чел.-мес. каждому [E017]
PILOT_PM = DEV_PM + TEST_PM + DESIGN_PM + ANALYST_PM


def main():
    print("Мост прибыли планового года, млн руб.")
    direct = (WARNINGS_PER_YEAR * SMS_SHARE * SMS_COST + SUPPORT_EXTRA) / 1e6
    for name, m in EXTRA_MONTHS.items():
        gain = m * MONTH / 1e6
        total = BASE + gain - direct
        print(f"  {name:15s}: {BASE} + {gain:.2f} (доп. месяцы) − {direct:.2f} (прямые расходы) = {total:.2f}; "
              f"до цели {TARGET - total:.2f}")
    need = (TARGET - BASE) * 1e6 + direct * 1e6
    print(f"\nГраница: с учётом прямых расходов нужно {need / MONTH:,.0f} доп. оплаченных месяцев.".replace(",", " "))
    print("  формула: доп. месяцы = номера × перебоев на номер × доля при свободном остатке × доля вовремя × месяцев на случай × доля года")
    print(f"  значение, которое предстоит узнать: месяцев на предотвращённый перебой (нужно 4,1+ при допущенных 0,2)")

    print("\nВложения (разработка отдельно)")
    invest = PILOT_PM * PM_COST
    for name, pm in (("разработка", DEV_PM), ("тестирование", TEST_PM), ("дизайнер 0,5 ставки Q1–Q2", DESIGN_PM),
                     ("аналитик 0,5 ставки Q1–Q2", ANALYST_PM)):
        print(f"  {name:28s}: {pm:.1f} чел.-мес. = {pm * PM_COST:.1f} млн руб.")
    print(f"  итого: {PILOT_PM} чел.-мес. × {PM_COST} млн = {invest:.1f} млн руб. (вложения Q1 — {(DESIGN_PM + ANALYST_PM) / 2 * PM_COST:.1f}, Q2 — {invest - (DESIGN_PM + ANALYST_PM) / 2 * PM_COST:.1f})")
    print("\nОкупаемость по кварталам, основной сценарий (накопленные вложения против накопленной прибыли после прямых расходов), млн руб.")
    per_q = (EXTRA_MONTHS["основной"] * MONTH / 1e6 - direct) / 2
    cum_inv = cum_gain = 0.0
    q1_inv = (DESIGN_PM + ANALYST_PM) / 2 * PM_COST
    for q in range(1, 13):
        cum_inv += q1_inv if q == 1 else (invest - q1_inv if q == 2 else 0)
        cum_gain += per_q if q >= 3 else 0
        print(f"  Q{q:<2} вложения {cum_inv:4.1f}  прибыль {cum_gain:5.2f}  разница {cum_gain - cum_inv:+.2f}")
    q_pay = 2 + invest / per_q
    print(f"  прибыль {per_q:.3f} млн руб./кв. → окупаемость примерно через {q_pay:.0f} кварталов; за 3 года вернётся {per_q * 10:.2f} млн руб.")
    print(f"  только разработка ({DEV_PM * PM_COST:.1f} млн) окупается за {2 + DEV_PM * PM_COST / per_q:.0f} кв.")

    print("\nЧувствительность прибыли планового года, млн руб. (основной сценарий, меняем по одному)")
    base_gain = EXTRA_MONTHS["основной"] * MONTH / 1e6
    for label, g, dc in (("охват 45 % вместо 60 % (слабее спрос)", base_gain * 0.45 / 0.6, direct),
                         ("0,1 мес. на перебой вместо 0,2 (удержание)", base_gain * 0.5, direct),
                         ("прямые расходы ×2 (обслуживание)", base_gain, direct * 2)):
        print(f"  {label:44s}: {BASE + g - dc:.2f}")

if __name__ == "__main__":
    main()
