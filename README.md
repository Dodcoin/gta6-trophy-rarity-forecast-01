# Forecast how many GTA VI players earn each trophy in week one

[![make.fun](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Dodcoin/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Dodcoin/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)

Entry for the [make.fun competition](https://make.fun/bounty/gta6-trophy-rarity-forecast-01):
forecast, for every Grand Theft Auto VI PlayStation 5 trophy, its earn rate on
Exophase at 2026-11-26 00:00 UTC — the percent of the players Exophase tracks
who will have earned it one week after launch — as five quantiles per trophy
(5%, 25%, 50%, 75%, 95%), scored by pinball loss on the logit scale.

## How it works

`main.py` (Python 3.13, standard library only) reads each case file in
`$MAKEFUN_INPUT_DIR` (default `/input/`) and writes one forecast per case to
`$MAKEFUN_OUTPUT_DIR` (default `/output/`).

For each trophy it models the earn rate on the logit scale as a straight line
against log elapsed time since release, fitted by least squares over the
case's recorded reads:

- When the history shows real movement, the fitted slope drives the
  extrapolation to the target, shrunk toward a prior slope.
- When the history is flat (e.g. launch night, before Exophase's first
  refresh), a prior slope takes over, set by what the trophy asks for:
  story chapters and named missions grow fastest, easy one-off activities
  next, long grinds and collectibles slowest, the platinum slowest of all.
- A short-horizon refresh adjustment pulls the median down a little when the
  target is only hours away: Exophase refreshes its counts in jumps, and a
  jump shortly after the checkpoint mostly dilutes rates as newly tracked
  players (who have barely played) join the denominator. The adjustment fades
  to nothing over a multi-day horizon, where progression dominates.
- Medians are capped by plausible ceilings per trophy kind (the platinum
  cannot plausibly be earned by many players in a week; an early chapter
  trophy can).
- The spread is a logit-scale sigma that grows with the square root of the
  horizon in days, plus the fit's residual and a prior-uncertainty term, so
  the 5-day final forecast is honestly much wider than a 90-minute one.

The program is fully offline, uses no network and calls no model, and is
deterministic: two runs on the same case write byte-identical output.

## Run locally

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## License

MIT — see [LICENSE](LICENSE).
