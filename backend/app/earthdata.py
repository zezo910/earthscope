"""
Answers the website's `earthData` requests (Explore / Compare pages) from the team's own
NASA dataset (data/processed/earthscope.db) instead of the Base44 NASA POWER function.

The site sends {variable, lat, lon, startYear, endYear}. If the point is one of our regions and
the variable is one we analysed, we answer here; otherwise main.py forwards the call to Base44.
"""
import datetime as dt
import math

from .core import conn

# site variable -> (our variable, unit shown, annual aggregation, provider info)
VARS = {
    "temperature": ("t2m", "°C", "mean", "MERRA-2", "M2TMNXSLV v5.12.4", "T2M"),
    "precipitation": ("precip", "mm/year", "sum", "GPM IMERG", "GPM_3IMERGM v07", "precipitation"),
    "soil_moisture": ("soil_moisture", "%", "pct", "FLDAS Noah", "FLDAS_NOAH01_C_GL_M_001", "SoilMoi00_10cm"),
}

# exact points from the site's region list that don't fall inside one of our boxes
PRESETS = [((0.0, 0.0), "global"), ((-3.5, -62.0), "amazon")]

# our boxes (west, south, east, north); the smallest box that contains the point wins
BOXES = {
    "cairo": (30.9, 29.8, 31.6, 30.3), "nile_delta": (30.0, 30.2, 32.0, 31.3),
    "east_oweinat": (28.53, 22.12, 28.93, 22.67), "los_angeles": (-118.7, 33.7, -117.7, 34.3),
    "dhaka": (90.2, 23.6, 90.6, 24.0), "amazon": (-64, -12, -61, -9), "egypt": (24.7, 22, 36.9, 31.7),
}
PAD = 0.25  # degrees of tolerance for map clicks
SCALE = {"mean": 1, "sum": 12, "pct": 100}  # annual value = monthly mean x this (soil moisture shown as %)


def find_region(lat, lon):
    for (plat, plon), reg in PRESETS:
        if abs(lat - plat) < 0.06 and abs(lon - plon) < 0.06:
            return reg
    hits = [(abs((e - w) * (n - s)), r) for r, (w, s, e, n) in BOXES.items()
            if w - PAD <= lon <= e + PAD and s - PAD <= lat <= n + PAD]
    return min(hits)[1] if hits else None


def load(series_id):
    with conn() as c:
        if not c.execute("SELECT 1 FROM series WHERE id = ?", (series_id,)).fetchone():
            return None
        rows = c.execute("SELECT ym, raw FROM monthly WHERE series_id = ? ORDER BY ym", (series_id,)).fetchall()
    return [(int(r["ym"][:4]), int(r["ym"][5:7]), r["raw"]) for r in rows if r["raw"] is not None]


# ---- statistics in pure Python (no numpy/scipy needed, so it runs on any Python version)
def _median(v):
    v = sorted(v); n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _betacf(a, b, x):
    qab, qap, qam, c, d = a + b, a + 1, a - 1, 1.0, 1 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > 1e-30 else 1e-30); h = d
    for m in range(1, 300):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-30 else 1e-30)
            c = 1 + aa / c; c = c if abs(c) > 1e-30 else 1e-30
            h *= d * c
        if abs(d * c - 1) < 1e-12:
            break
    return h


def _t_two_sided_p(t, df):
    """Two-sided p-value of Student's t (regularized incomplete beta)."""
    x = df / (df + t * t)
    if x <= 0:
        return 0.0
    lbeta = math.lgamma(df / 2) + math.lgamma(0.5) - math.lgamma(df / 2 + 0.5)
    front = math.exp(math.log(x) * df / 2 + math.log(1 - x) * 0.5 - lbeta)
    if x < (df / 2 + 1) / (df / 2 + 0.5 + 2):
        return min(1.0, front * _betacf(df / 2, 0.5, x) / (df / 2))
    return min(1.0, 1 - front * _betacf(0.5, df / 2, 1 - x) / 0.5)


def analyse(years, values, start, end):
    x, y = [float(v) for v in years], [float(v) for v in values]
    n = len(x)
    # Mann-Kendall (normal approximation with tie correction)
    s = sum((y[j] > y[i]) - (y[j] < y[i]) for i in range(n - 1) for j in range(i + 1, n))
    ties = {}
    for v in y:
        ties[v] = ties.get(v, 0) + 1
    var = (n * (n - 1) * (2 * n + 5) - sum(c * (c - 1) * (2 * c + 5) for c in ties.values())) / 18
    z = 0.0 if s == 0 else (s - (1 if s > 0 else -1)) / math.sqrt(var)
    p_mk = math.erfc(abs(z) / math.sqrt(2))
    tau = s / (n * (n - 1) / 2)
    # Sen's slope + 95% CI
    slopes = sorted((y[j] - y[i]) / (x[j] - x[i]) for i in range(n - 1) for j in range(i + 1, n) if x[j] != x[i])
    sen = _median(slopes)
    icpt = _median(y) - sen * _median(x)
    ca = 1.959964 * math.sqrt(var)
    lo_i, hi_i = int(round((len(slopes) - ca) / 2)), int(round((len(slopes) + ca) / 2))
    lo, hi = slopes[max(0, min(len(slopes) - 1, lo_i))], slopes[max(0, min(len(slopes) - 1, hi_i))]
    # OLS t-test
    xb, yb = sum(x) / n, sum(y) / n
    sxx = sum((a - xb) ** 2 for a in x); sxy = sum((a - xb) * (b - yb) for a, b in zip(x, y))
    syy = sum((b - yb) ** 2 for b in y)
    b1 = sxy / sxx
    resid = sum((b - (yb + b1 * (a - xb))) ** 2 for a, b in zip(x, y))
    r2 = 1 - resid / syy if syy else 0.0
    se = math.sqrt(resid / (n - 2) / sxx) if n > 2 else float("inf")
    p_ols = _t_two_sided_p(b1 / se, n - 2) if se > 0 else 0.0
    sig_mk, sig_ols = p_mk < 0.05, p_ols < 0.05
    direction = ("increasing" if sen > 0 else "decreasing") if (sig_mk or sig_ols) else "none"
    first, last = y[0], y[-1]
    return dict(
        method="Mann-Kendall + Sen's slope + OLS (EarthScope team pipeline)",
        startYear=int(start), endYear=int(end), n=n,
        slope=sen, intercept=icpt, slopePerDecade=sen * 10, ciLow=lo, ciHigh=hi,
        pValue=p_mk, significant=bool(sig_mk and sig_ols), direction=direction,
        r2=r2, mean=yb, firstValue=first, lastValue=last,
        changeFirstLast=last - first, percentChange=((last - first) / abs(first) * 100) if first else None,
        tests=dict(mannKendall=dict(tau=tau, p=p_mk), regression=dict(slope=b1, p=p_ols, r2=r2)),
    )


def answer(body):
    """Return the site's earthData response built from our data, or None to fall back to Base44."""
    try:
        var, lat, lon = body["variable"], float(body["lat"]), float(body["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if var not in VARS:
        return None
    ours, unit, agg, prov, dataset, param = VARS[var]
    region = find_region(lat, lon)
    rows = load(f"{ours}__{region}") if region else None
    if not rows:                      # we have no series for this place/variable: use NASA POWER
        return None

    y0 = int(body.get("startYear") or rows[0][0])
    y1 = int(body.get("endYear") or rows[-1][0])
    by_year = {}
    for y, m, v in rows:
        by_year.setdefault(y, []).append(v)
    annual = []
    for y in sorted(by_year):
        vs = by_year[y]
        if y0 <= y <= y1 and len(vs) >= 10:                  # same rule as the pipeline
            mean = sum(vs) / len(vs)
            annual.append(dict(year=y, value=round(mean * SCALE[agg], 4)))
    if len(annual) < 5:
        return None
    a0, a1 = annual[0]["year"], annual[-1]["year"]
    monthly = [dict(year=y, month=m, value=round(v * (100 if agg == "pct" else 1), 4)) for y, m, v in rows if a0 <= y <= a1]
    result = dict(
        variable=var, lat=lat, lon=lon, unit=unit, simulated=False,
        retrievedAt=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        provider=dict(name=f"EarthScope team dataset · {prov}", dataset=dataset, parameter=param,
                      url="https://giovanni.gsfc.nasa.gov/"),
        source="earthscope", meta=dict(region=region, series=f"{ours}__{region}"),
        annual=annual, monthly=monthly,
        analysis=analyse([a["year"] for a in annual], [a["value"] for a in annual], a0, a1),
    )
    return _clean(result)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o
