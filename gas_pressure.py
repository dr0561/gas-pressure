"""가스 압력 센서 보정 계산기.

센서가 보여주는 값(표시값)을 실제 압력(기준 게이지 값)에 맞추는 선형 보정을 계산한다.

  실제압력 = 기울기(gain) × 표시값 + 오프셋(offset)

- 1점 보정: 기준점 하나(예: 120 bar ↔ 88). 오프셋은 0 으로 가정하고 기울기만 구한다.
- 2점 보정: 기준점 두 개(예: 0 bar ↔ 0.4, 120 bar ↔ 88). 기울기와 오프셋을 함께 구한다.

표시값이 설정 범위에 비례해서 틀어진 경우(센서 실제 범위와 설정 범위가 다른 경우)는
실제 센서 범위를 역산해서 알려준다.

사용 예
  python gas_pressure.py                                  # 대화형: 실제·표시값 → 새 최대 설정값
  python gas_pressure.py --max 150 --fix 120 88           # 같은 계산을 한 줄로
  python gas_pressure.py --range 0 150 --point 120 88
  python gas_pressure.py --range 0 150 --point 0 0.4 --point 120 88 --read 75
"""

import argparse
import sys

# 센서 최대값 설정 상한
SETTING_LIMIT = 999

# 압력 트랜스미터 흔한 정격 범위 (bar). 역산한 범위와 가까운 것을 후보로 보여준다.
STANDARD_RANGES = [10, 16, 25, 40, 60, 100, 150, 160, 200, 250, 300, 400]


def fit(points):
    """기준점 [(실제압력, 표시값), ...] → (gain, offset)."""
    if len(points) == 1:
        actual, shown = points[0]
        if shown == 0:
            raise ValueError("표시값이 0 이면 1점 보정을 할 수 없습니다.")
        return actual / shown, 0.0

    (a1, s1), (a2, s2) = points[0], points[-1]
    if s1 == s2:
        raise ValueError("두 기준점의 표시값이 같으면 기울기를 구할 수 없습니다.")
    gain = (a2 - a1) / (s2 - s1)
    return gain, a1 - gain * s1


def new_max(lo, hi, actual, shown):
    """지금 설정(lo~hi)에서 실제 actual 일 때 shown 이 표시되면, 맞추기 위한 새 최대 설정값.

    표시값 = lo + (실제 - lo) / (센서최대 - lo) × (hi - lo)  를 센서최대에 대해 푼 것.
    최저(lo)는 맞다고 가정한다.
    """
    if shown <= lo:
        raise ValueError("표시값이 설정 최저값 이하이면 계산할 수 없습니다.")
    if actual <= lo:
        raise ValueError("실제 압력이 설정 최저값 이하이면 계산할 수 없습니다.")
    return lo + (actual - lo) * (hi - lo) / (shown - lo)


def shown_after(lo, hi, setting, actual, shown):
    """최대 설정을 setting 으로 바꿨을 때 같은 압력에서 나올 표시값."""
    return lo + (shown - lo) * (setting - lo) / (hi - lo)


def max_report(lo, hi, actual, shown):
    m = new_max(lo, hi, actual, shown)
    print()
    print(f"  지금 설정 {lo:g} ~ {hi:g} bar,  실제 {actual:g} bar  ↔  표시 {shown:g} bar")
    print(f"  계산: {lo:g} + ({actual:g} - {lo:g}) × ({hi:g} - {lo:g}) ÷ ({shown:g} - {lo:g})")
    print(f"  ▶ 새 최대 설정값 = {m:.1f} bar")
    if m > SETTING_LIMIT:
        print(f"  ※ 설정 상한 {SETTING_LIMIT} 을 넘습니다. 입력값이나 센서 연결을 다시 확인하세요.")
        return
    if abs(m - hi) / (hi - lo) < 0.005:
        print("  (지금 설정과 차이가 0.5% 미만이라 바꿀 필요가 거의 없습니다.)")
    lo_i, hi_i = int(m), int(m) + 1
    print("  소수점 입력이 안 되면:")
    for v in (lo_i, hi_i):
        after = shown_after(lo, hi, v, actual, shown)
        print(f"    {v:>4} → 표시 {after:.1f} bar (오차 {after - actual:+.1f})")
    print("  ※ 최저값(0점)이 맞다는 가정입니다. 0 bar 에서 표시가 0 이 아니면 0점부터 맞추세요.")
    print("  ※ 설정을 바꾼 뒤 다시 확인할 때는 '지금 설정 최대'에 바꾼 값을 넣어야 합니다.")
    print()


def corrected(shown, gain, offset):
    return gain * shown + offset


def to_ma(value, lo, hi):
    """설정 범위 기준 4–20 mA 환산."""
    return 4 + 16 * (value - lo) / (hi - lo)


def report(lo, hi, points, gauge_max, reads):
    gain, offset = fit(points)
    span = hi - lo

    print()
    print("== 입력 ==")
    print(f"  센서 설정 범위 : {lo:g} ~ {hi:g} bar")
    print(f"  레귤레이터 게이지 최대 : {gauge_max:g} bar")
    for actual, shown in points:
        print(f"  기준점 : 실제 {actual:g} bar ↔ 표시 {shown:g}  "
              f"({to_ma(shown, lo, hi):.2f} mA 상당)")

    print()
    print("== 보정식 ==")
    print(f"  실제압력 = {gain:.5f} × 표시값 {offset:+.4f}")
    dev = (1 / gain - 1) * 100
    print(f"  (표시값이 실제보다 {abs(dev):.1f}% {'낮게' if dev < 0 else '높게'} 나옴)")

    # 오프셋이 0 이라는 가정에서 센서 실제 범위 역산:
    #   표시값 = (실제 / 실제범위) × 설정범위  →  실제범위 = 설정범위 × gain
    true_span = span * gain
    nearest = min(STANDARD_RANGES, key=lambda r: abs(r - true_span))
    print()
    print("== 범위 설정 점검 (오프셋 0 가정) ==")
    print(f"  센서 실제 범위 역산 : 약 {lo:g} ~ {lo + true_span:.1f} bar")
    print(f"  가까운 정격 범위    : {lo:g} ~ {nearest:g} bar  "
          f"(이 값이면 {points[-1][0]:g} bar 에서 표시 "
          f"{points[-1][0] / nearest * span + lo:.1f} 예상)")
    print("  → 센서 명판/데이터시트의 범위를 확인하고, 설정 범위를 거기에 맞추는 것이 먼저입니다.")
    print("    보정식(gain)으로 덮는 것은 원인을 확인한 뒤의 차선책입니다.")

    if len(points) == 1:
        print()
        print("  ※ 1점 보정은 오프셋을 0 으로 가정합니다. 실린더 밸브를 잠그고 배관을 0 bar 로")
        print("    뺀 상태의 표시값을 두 번째 기준점으로 넣으면(--point 0 <표시값>) 오프셋까지 잡힙니다.")

    warnings = []
    if any(a >= gauge_max * 0.75 for a, _ in points):
        warnings.append(
            f"기준 압력이 게이지 최대({gauge_max:g} bar)의 75% 이상입니다. 눈금 끝 근처라 "
            "기준값 자체의 오차가 클 수 있고, 게이지가 끝에서 멈춰 있을 수도 있습니다.")
    if any(a > hi for a, _ in points):
        warnings.append("기준 압력이 센서 설정 범위를 넘습니다.")
    if warnings:
        print()
        print("== 주의 ==")
        for w in warnings:
            print(f"  - {w}")

    if reads:
        print()
        print("== 표시값 → 실제 압력 ==")
        print(f"  {'표시값':>8}  {'실제(bar)':>10}")
        for r in reads:
            print(f"  {r:>8g}  {corrected(r, gain, offset):>10.1f}")
    print()


def ask(prompt, default=None):
    while True:
        text = input(f"{prompt}" + (f" [{default}]" if default is not None else "") + ": ").strip()
        if not text and default is not None:
            return float(default)
        try:
            return float(text)
        except ValueError:
            print("  숫자를 입력하세요.")


def interactive():
    print("센서 최대값 보정 계산기 (빈 칸 Enter = [ ] 안의 값)")
    lo = ask("지금 설정 최저 (bar)", 0)
    hi = ask("지금 설정 최대 (bar)", 150)
    while True:
        actual = ask("실제 압력 (게이지, bar)", None)
        shown = ask("센서 표시값 (bar)", None)
        try:
            max_report(lo, hi, actual, shown)
        except ValueError as e:
            print(f"  {e}")
        if input("다른 값으로 다시 계산? (y/N): ").strip().lower() != "y":
            break


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        interactive()
        return

    p = argparse.ArgumentParser(description="가스 압력 센서 보정 계산기")
    p.add_argument("--range", nargs=2, type=float, metavar=("LO", "HI"), default=[0, 150],
                   help="센서 설정 범위 bar (기본 0 150)")
    p.add_argument("--gauge-max", type=float, default=120, help="레귤레이터 게이지 최대 bar (기본 120)")
    p.add_argument("--max", type=float, help="지금 센서 설정 최대 bar (--fix 와 함께, 최저는 --range LO)")
    p.add_argument("--fix", nargs=2, type=float, metavar=("ACTUAL", "SHOWN"),
                   help="실제압력 표시값 → 새 최대 설정값 계산")
    p.add_argument("--point", nargs=2, type=float, action="append",
                   metavar=("ACTUAL", "SHOWN"), help="기준점: 실제압력 표시값 (1~2번)")
    p.add_argument("--read", type=float, nargs="+", default=[], help="실제 압력으로 바꿀 표시값들")
    args = p.parse_args(argv)

    lo, hi = args.range
    if args.fix:
        if args.max is not None:
            hi = args.max
        if hi <= lo:
            p.error("설정 최대는 최저보다 커야 합니다.")
        try:
            max_report(lo, hi, *args.fix)
        except ValueError as e:
            p.error(str(e))
        return
    if not args.point:
        p.error("--fix 또는 --point 가 필요합니다.")
    if len(args.point) > 2:
        p.error("--point 는 최대 2번까지입니다.")
    if hi <= lo:
        p.error("--range 는 LO < HI 여야 합니다.")
    points = sorted((a, s) for a, s in args.point)
    try:
        report(lo, hi, points, args.gauge_max, args.read)
    except ValueError as e:
        p.error(str(e))


if __name__ == "__main__":
    main()
