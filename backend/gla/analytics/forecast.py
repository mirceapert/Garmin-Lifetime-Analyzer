"""Forecasts: tonight's sleep score and night HRV, and the inputs for planning fitness and form.

Tonight's forecast is a small linear model (ridge regression) on what is known by the evening: today's
and yesterday's training load, tennis or a workout finishing after 19:00 today, your form, your last night and your 7-night average, and whether it is a
Friday or Saturday. It is trained on your own history every time you open the page, so it follows every
sync. Its accuracy is measured honestly: trained on the older three quarters of your nights and tested
on the newest quarter, against simply guessing your 7-night average.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import load as ld
from .sleep import OUTCOMES

MIN_TRAIN = 80
RIDGE = 3.0
TARGETS = ("sleep_score", "hrv")
FEATURES = {
    "load_today": "Today's training load",
    "load_yesterday": "Yesterday's training load",
    "form": "Form after today",
    "last_night": "Last night",
    "avg7": "Your 7-night average",
    "tennis_today": "Tennis today",
    "evening_workout": "Workout finishing after 19:00",
    "weekend": "Friday or Saturday night",
    "late_bed_last": "Bedtime last night (vs usual)",
}


def features(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Row for day D: what is known on the evening of D. Target: the night ending on D + 1."""
    y = df[key]
    f = pd.DataFrame(index=df.index)
    f["load_today"] = df["load"]
    f["load_yesterday"] = df["load"].shift(1)
    f["form"] = df["form"].shift(-1)                   # form at the start of D + 1 = after D's training
    # the last row has no D + 1 yet: carry today's training through the fitness model by hand
    if len(df):
        last = df.iloc[-1]
        fit = last.fitness + (last.load - last.fitness) / ld.FITNESS_DAYS
        fat = last.fatigue + (last.load - last.fatigue) / ld.FATIGUE_DAYS
        f.iloc[-1, f.columns.get_loc("form")] = fit - fat
    f["last_night"] = y.ffill(limit=2)
    f["avg7"] = y.rolling(7, min_periods=4).mean()
    f["tennis_today"] = df["tennis"].astype(float)
    f["evening_workout"] = df["evening_workout"].astype(float)
    f["weekend"] = [1.0 if d.weekday() in (4, 5) else 0.0 for d in df.index]
    usual = df["bed_min"].rolling(28, min_periods=10).median().shift(1)
    f["late_bed_last"] = ((df["bed_min"] - usual) / 60).clip(-3, 3).fillna(0)
    f["target"] = y.shift(-1)
    return f


class Ridge:
    def __init__(self, lam: float = RIDGE):
        self.lam = lam

    def fit(self, x: np.ndarray, y: np.ndarray) -> "Ridge":
        self.mu, self.sd = x.mean(0), x.std(0)
        self.sd[self.sd == 0] = 1
        z = (x - self.mu) / self.sd
        self.b0 = y.mean()
        self.w = np.linalg.solve(z.T @ z + self.lam * np.eye(z.shape[1]), z.T @ (y - self.b0))
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.b0 + ((x - self.mu) / self.sd) @ self.w


def tonight(df: pd.DataFrame, key: str, today: date) -> dict:
    meta = OUTCOMES[key]
    f = features(df, key)
    cols = list(FEATURES)
    train = f.dropna(subset=cols + ["target"])
    train = train[train.index < today]
    base = {"key": key, "label": meta["label"], "unit": meta["unit"], "better": meta["better"]}
    if len(train) < MIN_TRAIN:
        return {**base, "ready": False, "nights": int(len(train)), "needed": MIN_TRAIN}
    x, y = train[cols].to_numpy(float), train["target"].to_numpy(float)
    cut = int(len(train) * 0.75)
    m = Ridge().fit(x[:cut], y[:cut])
    err = y[cut:] - m.predict(x[cut:])
    mae = float(np.mean(np.abs(err)))
    mae_base = float(np.mean(np.abs(y[cut:] - train["avg7"].to_numpy(float)[cut:])))
    band = float(np.quantile(np.abs(err), 0.8))
    model = Ridge().fit(x, y)
    # today's row: fill what isn't known yet (no night for today yet means last_night is carried)
    row = f.loc[[d for d in f.index if d <= today][-1:], cols].copy()
    row = row.fillna({"load_today": 0, "load_yesterday": 0, "weekend": 0, "late_bed_last": 0,
                       "tennis_today": 0, "evening_workout": 0})
    if row[cols].isna().any(axis=None):
        return {**base, "ready": False, "nights": int(len(train)), "needed": MIN_TRAIN, "reason": "missing recent nights"}
    xr = row.to_numpy(float)
    pred = float(model.predict(xr)[0])
    z = (xr[0] - model.mu) / model.sd
    contrib = sorted(({"feature": k, "label": FEATURES[k], "value": round(float(xr[0][i]), 1),
                       "effect": round(float(z[i] * model.w[i]), 2)} for i, k in enumerate(cols)),
                     key=lambda c: -abs(c["effect"]))
    night = row.index[0] + timedelta(days=1)
    recent = f.dropna(subset=["target"]).tail(60)
    back = [[(d + timedelta(days=1)).isoformat(), round(float(t), 1), round(float(p), 1)]
            for d, t, p in zip(recent.index, recent["target"], model.predict(recent[cols].fillna(0).to_numpy(float)))]
    return {**base, "ready": True, "night_of": row.index[0].isoformat(), "wake_day": night.isoformat(),
            "prediction": round(pred, 1), "band": round(band, 1), "average": round(float(row["avg7"].iloc[0]), 1),
            "mae": round(mae, 1), "mae_baseline": round(mae_base, 1), "test_nights": int(len(err)),
            "train_nights": int(len(train)), "contributions": contrib, "recent": back}


def load_plan(df: pd.DataFrame, today: date) -> dict:
    """What the planner on the Forecasts tab starts from: today's fitness and fatigue and your recent weeks."""
    if df.empty:
        return {"ready": False}
    hist = df.loc[[d for d in df.index if d <= today]]
    last = hist.iloc[-1]
    recent = hist.tail(56)
    pattern = [0.0] * 7
    for wd in range(7):
        vals = [v for d, v in recent["load"].items() if d.weekday() == wd]
        pattern[wd] = round(float(np.mean(vals)), 1) if vals else 0.0
    weekly = [round(float(hist["load"].iloc[max(0, len(hist) - 7 * (k + 1)):len(hist) - 7 * k].sum()), 1) for k in range(8)][::-1]
    peak = hist["fitness"].idxmax()
    # after today's training: where tomorrow starts
    fit = last.fitness + (last.load - last.fitness) / ld.FITNESS_DAYS
    fat = last.fatigue + (last.load - last.fatigue) / ld.FATIGUE_DAYS
    return {"ready": True, "day": hist.index[-1].isoformat(),
            "fitness": round(float(fit), 1), "fatigue": round(float(fat), 1),
            "form": round(float(fit - fat), 1), "load_today": round(float(last.load), 1),
            "weekday_pattern": pattern, "weekly_loads": weekly, "weekly_average": round(float(np.mean(weekly[-4:])), 1),
            "fitness_days": ld.FITNESS_DAYS, "fatigue_days": ld.FATIGUE_DAYS,
            "peak_fitness": {"day": peak.isoformat(), "value": round(float(hist["fitness"].max()), 1)}}
