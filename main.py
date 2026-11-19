#!/usr/bin/env python3
"""Forecast GTA VI trophy earn rates on Exophase one week after launch.

Reads each case file in $MAKEFUN_INPUT_DIR (default /input/) and writes one
forecast per case to $MAKEFUN_OUTPUT_DIR (default /output/).

Method, per trophy: model the earn rate on the logit scale as a straight line
against log elapsed time since release, fitted by least squares over the
case's recorded reads. When the history moves, the fitted slope drives the
extrapolation to the target, shrunk toward a prior slope. When the history is
flat, the prior slope takes over: story chapters and named missions grow
fastest, easy one-off activities next, long grinds and collectibles slowest,
the platinum slowest of all. A short-horizon refresh adjustment pulls the
median down a little when the target is only hours away (Exophase refreshes
its counts in jumps, and a jump shortly after the checkpoint mostly dilutes
rates as newly tracked players join the denominator); it fades to nothing
over a multi-day horizon, where progression dominates. The spread is a
logit-scale sigma growing with the square root of the horizon in days, plus
the fit residual and a prior-uncertainty term.

Fully offline, standard library only, deterministic.
"""

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

Z = (-1.6448536269514722, -0.6744897501960817, 0.0,
     0.6744897501960817, 1.6448536269514722)


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def logit(p):
    p = min(max(p, 0.01), 99.99) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(v):
    if v >= 0:
        return 100.0 / (1.0 + math.exp(-v))
    e = math.exp(v)
    return 100.0 * e / (1.0 + e)


def classify(trophy):
    """Return (prior_slope, ceiling_percent) from tier, name, description."""
    tier = (trophy.get("tier") or "").lower()
    text = ((trophy.get("name") or "") + " " +
            (trophy.get("description") or "")).lower()
    if tier == "platinum":
        return 0.40, 2.5
    if "100% completion" in text or "100 percent" in text:
        return 0.30, 6.0
    if "complete chapter" in text:
        return 1.60, 80.0
    if text.strip().endswith("complete the final mission."):
        return 1.30, 30.0
    grind_marks = ("250 ", "100 locations", "100 vehicles", "50 challenges",
                   "20 different", "gold medal", "every location",
                   "every spot", "3 collectible", "8 mission strands",
                   "5 bank vaults", "all shooting range", "100%")
    if any(m in text for m in grind_marks):
        return 0.45, 20.0
    if text.strip().startswith("complete ") or "complete " in text:
        return 1.15, 60.0
    return 0.85, 60.0


def fit_line(xs, ys):
    """Least-squares slope and intercept of ys on xs; also residual sd."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return 0.0, my, 0.0
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    if n > 2:
        resid = math.sqrt(sum((y - (intercept + slope * x)) ** 2
                              for x, y in zip(xs, ys)) / (n - 2))
    else:
        resid = 0.0
    return slope, intercept, resid


def forecast_case(case):
    trophies = case["trophies"]
    history = case.get("history") or []
    horizon_min = float(case.get("horizon_minutes") or 0)
    horizon_h = horizon_min / 60.0
    horizon_d = horizon_min / 1440.0
    target = parse_time(case["target"])
    release = case.get("game", {}).get("release_date")
    if release:
        origin = datetime.fromisoformat(release).replace(tzinfo=timezone.utc)
    elif history:
        origin = parse_time(history[0]["at"])
    else:
        origin = parse_time(case["at"])

    def hours_to(moment):
        return max((moment - origin).total_seconds() / 3600.0, 0.0)

    x_target = math.log1p(hours_to(target))
    rows = []
    for idx, trophy in enumerate(trophies):
        series = []
        for read in history:
            rates = read.get("rates") or []
            if idx < len(rates) and rates[idx] is not None:
                series.append((hours_to(parse_time(read["at"])),
                               float(rates[idx])))
        last_rate = series[-1][1] if series else 1.0

        # A trophy every tracked player already holds stays near 100%.
        if last_rate >= 99.5:
            rows.append({"id": trophy["id"],
                         "q": [99.2, 99.7, 99.9, 99.97, 99.99]})
            continue

        prior_slope, ceiling = classify(trophy)
        # A ceiling must never sit below where the trophy already is.
        ceiling = max(ceiling, last_rate)
        xs = [math.log1p(h) for h, _ in series]
        ys = [logit(r) for _, r in series]
        if len(series) >= 2:
            slope, _icept, resid = fit_line(xs, ys)
        else:
            slope, resid = 0.0, 0.0
        # A noisy early jump must not extrapolate into an absurd slope:
        # two days of launch data cannot support more than this per log-hour.
        slope = min(max(slope, -2.0), 3.0)
        changes = sum(1 for a, b in zip(series, series[1:])
                      if a[1] != b[1])
        trust = changes / (changes + 4.0) if changes else 0.0
        x_last = xs[-1] if xs else x_target
        # Progression needs time to act; over a few hours it barely moves.
        growth = 1.0 - math.exp(-horizon_h / 24.0)
        # A refresh shortly after the checkpoint dilutes rates; fades fast.
        dilution = -0.40 * math.exp(-horizon_h / 12.0)
        med = logit(last_rate)
        med += trust * slope * (x_target - x_last)
        med += (1.0 - trust) * prior_slope * (x_target - x_last) * growth
        med += dilution
        med = min(med, logit(ceiling))
        med = min(max(med, logit(0.05)), logit(99.9))

        var = (0.55 * math.sqrt(horizon_d)) ** 2
        var += (0.35 * (1.0 - trust)) ** 2
        var += min(resid, 0.8) ** 2
        var += (0.45 * math.exp(-horizon_h / 24.0)) ** 2
        sigma = min(max(math.sqrt(var), 0.25), 2.0)

        qs = []
        prev = 0.01
        for z in Z:
            q = round(min(max(inv_logit(med + z * sigma), 0.01), 99.99), 4)
            q = max(q, prev)
            qs.append(q)
            prev = q
        rows.append({"id": trophy["id"], "q": qs})
    rows.sort(key=lambda r: r["id"])
    return {"trophies": rows}


def main():
    in_dir = Path(os.environ.get("MAKEFUN_INPUT_DIR") or "/input")
    out_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(in_dir.glob("*.in")):
        with open(path, "r", encoding="utf-8") as fh:
            case = json.load(fh)
        result = forecast_case(case)
        out_path = out_dir / (path.stem + ".out")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh)
            fh.write("\n")


if __name__ == "__main__":
    main()
