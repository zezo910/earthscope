#!/usr/bin/env python3
"""
Trend Detective report (stand-alone analysis, not used by the website)
=====================================================================
data/raw/*.csv  ->  analysis/output/<region>__<variable>.json + index.json + summary.csv (+ plots/*.png)

How to run (from the repo root)
  1. The NASA CSVs live in data/raw/ (keep Giovanni's file names; name each AppEEARS
     request after its region, e.g. east_oweinat__ndvi.csv).
  2. pip install -r backend/requirements.txt
  3. python analysis/trend_report.py          (options: --raw --out --plots --no-plots)

What it does for every (region, variable)
  monthly series -> remove the seasonal cycle (anomalies) -> annual mean of the anomalies
  -> Mann-Kendall p-value, Sen's slope (+95% CI), OLS slope with t-test p-value and 95% CI
  -> verdict: significant / weak_evidence / no_evidence / too_short
  -> years of data needed to detect the trend (Weatherhead et al. 1998)
  -> Benjamini-Hochberg FDR across all series (for views that scan many series at once)
  -> a plain-language summary sentence and a PNG plot per series

Code written with AI assistance (Claude) and reviewed by the team.
"""
import argparse
import io
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent

# ----------------------------------------------------------------------------- config
REGIONS = {
    "global":       {"name": "Global", "name_ar": "العالم", "type": "global",
                     "bbox": (-180, -90, 180, 90)},
    "egypt":        {"name": "Egypt", "name_ar": "مصر", "type": "desert country",
                     "bbox": (24.7, 22.0, 36.9, 31.7), "shape": "Egypt"},
    "cairo":        {"name": "Greater Cairo", "name_ar": "القاهرة الكبرى", "type": "large city",
                     "bbox": (30.9, 29.8, 31.6, 30.3)},
    "nile_delta":   {"name": "Nile Delta", "name_ar": "الدلتا", "type": "farmland",
                     "bbox": (30.0, 30.2, 32.0, 31.3)},
    "east_oweinat": {"name": "East Oweinat", "name_ar": "شرق العوينات", "type": "reclaimed desert",
                     "bbox": (28.53, 22.12, 28.93, 22.67)},
    "los_angeles":  {"name": "Los Angeles", "name_ar": "لوس أنجلوس", "type": "large city",
                     "bbox": (-118.7, 33.7, -117.7, 34.3)},
    "dhaka":        {"name": "Dhaka", "name_ar": "دكا", "type": "large city",
                     "bbox": (90.2, 23.6, 90.6, 24.0)},
    "amazon":       {"name": "Amazon (Rondônia)", "name_ar": "الأمازون (روندونيا)", "type": "rainforest",
                     "bbox": (-64, -12, -61, -9)},
}

VARIABLES = {
    "t2m": {
        "name": "Air temperature (2 m)", "name_ar": "حرارة الهوا (2م)",
        "definition": "How warm the air is about 2 m above the ground.",
        "source": "MERRA-2 reanalysis (NASA GMAO)",
        "citation": "GMAO (2015), MERRA-2 tavgM_2d_slv_Nx V5.12.4, GES DISC, doi:10.5067/AP1B0BA5PD2K",
        "ids": ["M2TMNXSLV_5_12_4_T2M", "M2SDNXSLV_5_12_4_T2MMEAN"],
        "keyword": "M2TMNXSLV", "tool": "giovanni",
        "start": "1980-01-01", "end": "2025-12-31",
        "units": "°C", "annual_units": "°C", "annual_scale": 1, "pct": False,
        "regions": ["global", "egypt", "cairo", "nile_delta", "east_oweinat",
                    "los_angeles", "dhaka", "amazon"],
    },
    "precip": {
        "name": "Precipitation", "name_ar": "المطر",
        "definition": "How much rain falls, in millimetres.",
        "source": "GPM IMERG Final Run V07 (NASA/JAXA)",
        "citation": "Huffman et al. (2023), GPM IMERG Final Precipitation L3 1 month 0.1° V07, GES DISC, "
                    "doi:10.5067/GPM/IMERG/3B-MONTH/07",
        "ids": ["GPM_3IMERGM_07_precipitation"],
        "keyword": "GPM_3IMERGM", "tool": "giovanni",
        "start": "1998-01-01", "end": "2024-12-31",
        "units": "mm/month", "annual_units": "mm/year", "annual_scale": 12, "pct": True,
        "regions": ["global", "egypt", "los_angeles", "dhaka", "amazon"],
        "bbox_override": {"global": (-180, -60, 180, 60)},
    },
    "soil_moisture": {
        "name": "Soil moisture (top 10 cm)", "name_ar": "رطوبة التربة",
        "definition": "How much of the top 10 cm of soil is water (m³ of water per m³ of soil).",
        "source": "FLDAS Noah land model (NASA, GLDAS family)",
        "citation": "McNally (2018), FLDAS Noah Land Surface Model L4 Global Monthly 0.1° (MERRA-2 and CHIRPS), "
                    "GES DISC, doi:10.5067/5NHC22T9375G",
        "ids": ["FLDAS_NOAH01_C_GL_M_001_SoilMoi00_10cm_tavg"],
        "keyword": "FLDAS", "tool": "giovanni",
        "start": "1982-01-01", "end": "2025-12-31",
        "units": "m³/m³", "annual_units": "m³/m³", "annual_scale": 1, "pct": True,
        "regions": ["global", "los_angeles", "dhaka", "amazon"],
    },
    "water_vapor": {
        "name": "Water vapor (whole air column)", "name_ar": "بخار المية",
        "definition": "All the water vapor in the air above a spot, as mm of water if it all fell as rain.",
        "source": "AIRS on Aqua (NASA JPL)",
        "citation": "AIRS project (2019), Aqua/AIRS L3 Monthly Standard Physical Retrieval 1° V7.0, GES DISC, "
                    "doi:10.5067/UBENJB9D3T2H",
        "ids": ["AIRS3STM_7_0_TotH2OVap_A"],
        "keyword": "AIRS3STM", "tool": "giovanni",
        "start": "2003-01-01", "end": "2025-12-31",
        "units": "mm", "annual_units": "mm", "annual_scale": 1, "pct": True,
        "regions": ["global", "egypt", "amazon"],
    },
    "no2": {
        "name": "Nitrogen dioxide (NO2)", "name_ar": "NO2",
        "definition": "A polluting gas from car exhaust, power plants and factories, measured in the lower air.",
        "source": "OMI on Aura (NASA/KNMI)",
        "citation": "Krotkov et al. (2019), OMI/Aura NO2 Cloud-Screened Tropospheric Column L3 Global 0.25° V3 "
                    "(OMNO2d), GES DISC, doi:10.5067/Aura/OMI/DATA3007",
        "ids": ["OMNO2d_003_ColumnAmountNO2TropCloudScreened"],
        "keyword": "OMNO2d", "tool": "giovanni",
        "start": "2005-01-01", "end": "2025-12-31",
        "units": "×10^15 molecules/cm²", "annual_units": "×10^15 molecules/cm²",
        "annual_scale": 1, "pct": True,
        "regions": ["cairo", "los_angeles", "dhaka"],
    },
    "ndvi": {
        "name": "Vegetation greenness (NDVI)", "name_ar": "خضرة النبات (NDVI)",
        "definition": "How green and dense plants are, from -1 to 1: bare desert is about 0.1, "
                      "dense crops are above 0.6.",
        "source": "MODIS Terra MOD13A3 v061 (NASA LP DAAC, via AppEEARS)",
        "citation": "Didan (2021), MODIS/Terra Vegetation Indices Monthly L3 Global 1km SIN Grid V061, "
                    "LP DAAC, doi:10.5067/MODIS/MOD13A3.061",
        "ids": ["_1_km_monthly_NDVI"],
        "keyword": "MOD13A3.061", "tool": "appeears",
        "start": "2001-01-01", "end": "2025-12-31",
        "units": "NDVI", "annual_units": "NDVI", "annual_scale": 1, "pct": True,
        "regions": ["east_oweinat", "nile_delta"],
    },
}

GIOVANNI_URL = ("https://giovanni.gsfc.nasa.gov/giovanni/#service=ArAvTs"
                "&starttime={start}T00:00:00Z&endtime={end}T23:59:59Z"
                "&bbox={bbox}&data={data}&dataKeyword={keyword}")
APPEEARS_URL = "https://appeears.earthdatacloud.nasa.gov/task/area"

MIN_YEARS = 10              # fewer full years: no verdict
OK_YEARS = 20               # fewer full years: verdict with a warning
MIN_MONTHS_PER_YEAR = 10    # a year with fewer valid months is dropped
MIN_DAYS_PER_MONTH = 5      # daily data (OMI NO2): fewer valid days -> month is missing
ALPHA = 0.05

METHOD = {
    "series": "Monthly area averages; seasonal cycle removed by subtracting each calendar month's mean; "
              "trend tests run on annual means of the monthly anomalies.",
    "tests": "Mann-Kendall (Kendall's tau vs. time) and OLS t-test, both two-sided at alpha = 0.05. "
             "Rate of change = Sen's slope with 95% CI.",
    "verdict": "significant = both tests p < 0.05; weak_evidence = only one; no_evidence = neither; "
               f"too_short = fewer than {MIN_YEARS} full years.",
    "years_needed": "Weatherhead et al. (1998): n* = [3.3*sigma_N/|w0| * sqrt((1+phi)/(1-phi))]^(2/3), "
                    "sigma_N and phi from detrended monthly anomalies; 90% detection probability at 5% level.",
    "multiple_testing": "Benjamini-Hochberg false discovery rate across all series (q = 0.05).",
    "references": [
        "Mann (1945) Econometrica 13:245-259", "Kendall (1975) Rank Correlation Methods",
        "Sen (1968) J. Am. Stat. Assoc. 63:1379-1389",
        "Weatherhead et al. (1998) J. Geophys. Res. 103(D14):17149-17161, doi:10.1029/98JD00995",
        "Benjamini & Hochberg (1995) J. R. Stat. Soc. B 57:289-300",
    ],
}


def fmt_bbox(b):
    return ",".join(f"{v:g}" for v in b)


def region_bbox(vslug, rslug):
    return VARIABLES[vslug].get("bbox_override", {}).get(rslug, REGIONS[rslug]["bbox"])


def downloads():
    """Every file the team downloads: one per (variable, region)."""
    out = []
    for vslug, v in VARIABLES.items():
        for rslug in v["regions"]:
            bbox = region_bbox(vslug, rslug)
            if v["tool"] == "giovanni":
                url = GIOVANNI_URL.format(start=v["start"], end=v["end"], bbox=fmt_bbox(bbox),
                                          data=v["ids"][0], keyword=v["keyword"])
            else:
                url = APPEEARS_URL
            out.append({"variable": vslug, "region": rslug, "bbox": bbox, "url": url,
                        "file": f"{rslug}__{vslug}.csv", "tool": v["tool"]})
    return out


# ----------------------------------------------------------------------------- reading raw files
ID_TO_VAR = {i: vslug for vslug, v in VARIABLES.items() for i in v["ids"]}
BBOX_IN_NAME = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)([EW])_(\d{1,2}(?:\.\d+)?)([NS])_"
                          r"(\d{1,3}(?:\.\d+)?)([EW])_(\d{1,2}(?:\.\d+)?)([NS])")
HEADER_LINE = re.compile(r'^\s*"?(?:time|date)"?\s*,', re.I)
COMMON_FILLS = (-9999.0, -9999.9, -999.0)


def _signed(value, hemi):
    v = float(value)
    return -v if hemi in "WS" else v


def bbox_from_name(name):
    m = BBOX_IN_NAME.search(name)
    if not m:
        return None
    return (_signed(m[1], m[2]), _signed(m[3], m[4]), _signed(m[5], m[6]), _signed(m[7], m[8]))


def bbox_from_text(text):
    nums = re.findall(r"-?\d+(?:\.\d+)?", text or "")
    return tuple(float(x) for x in nums[:4]) if len(nums) >= 4 else None


def read_giovanni(path):
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    hdr = next((i for i, line in enumerate(lines) if HEADER_LINE.match(line)), None)
    if hdr is None:
        return None
    meta = {}
    for line in lines[:hdr]:
        if ":," in line:
            key, val = line.split(":,", 1)
            meta[key.strip().strip('"')] = val.strip().strip('"')
    df = pd.read_csv(io.StringIO("\n".join(lines[hdr:])))
    if df.shape[1] < 2:
        return None
    tcol, vcol = df.columns[0], df.columns[1]
    out = pd.DataFrame({"date": pd.to_datetime(df[tcol], errors="coerce"),
                        "value": pd.to_numeric(df[vcol], errors="coerce")}).dropna(subset=["date"])
    fill = None
    for key, val in meta.items():
        if key.lower().startswith("fill value"):
            try:
                fill = float(val)
            except ValueError:
                pass
    vals = out["value"].to_numpy(dtype=float)
    bad = np.abs(vals) > 1e29
    for fv in (fill,) + COMMON_FILLS:
        if fv is not None:
            bad |= np.isclose(vals, fv, rtol=1e-6, atol=0.0)
    out.loc[bad, "value"] = np.nan

    url = next((v for k, v in meta.items() if "url" in k.lower()), "")
    bbox = None
    for key, val in meta.items():
        if "bounding box" in key.lower():
            bbox = bbox_from_text(val)
    if bbox is None and "bbox=" in url:
        bbox = bbox_from_text(url.split("bbox=", 1)[1].split("&", 1)[0])
    if bbox is None:
        bbox = bbox_from_name(path.name)
    title = next((v for k, v in meta.items() if k.lower().startswith("title")), "")
    m = re.search(r"\]\s*([^\s,]+)\s+over", title)
    return {"kind": "giovanni", "var_id": re.sub(r"^mean_", "", str(vcol).strip()),
            "bbox": bbox, "units_hint": m[1] if m else None, "title": title,
            "url": url, "df": out}


def read_appeears(path):
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    cols = {str(c).lower().strip(): c for c in df.columns}
    if "date" not in cols or "mean" not in cols:
        return None
    if "dataset" in cols:
        df = df[df[cols["dataset"]].astype(str).str.contains("NDVI", case=False)]
    out = pd.DataFrame({"date": pd.to_datetime(df[cols["date"]], errors="coerce"),
                        "value": pd.to_numeric(df[cols["mean"]], errors="coerce")}).dropna(subset=["date"])
    return {"kind": "appeears", "var_id": "_1_km_monthly_NDVI", "bbox": None,
            "units_hint": None, "title": "", "url": APPEEARS_URL, "df": out}


def closest_region(bbox, vslug):
    if bbox is None:
        return None, None
    if bbox[2] - bbox[0] >= 300:                      # spans the globe
        return "global", 0.0
    candidates = VARIABLES[vslug]["regions"] if vslug else list(REGIONS)
    best, dist = None, None
    for r in candidates:
        rb = region_bbox(vslug, r) if vslug else REGIONS[r]["bbox"]
        d = max(abs(a - b) for a, b in zip(bbox, rb))
        if dist is None or d < dist:
            best, dist = r, d
    return (best, dist) if dist is not None and dist <= 1.01 else (None, dist)


def identify(path, rec):
    """Return (region, variable, how) for a raw file, or (None, None, reason)."""
    stem = path.stem.lower()
    m = re.match(r"^([a-z_]+?)__([a-z0-9_]+?)(?:[_\-.]?part\d+)?$", stem)
    if m and m[1] in REGIONS and m[2] in VARIABLES:
        return m[1], m[2], "file name"
    vslug = "ndvi" if rec["kind"] == "appeears" else ID_TO_VAR.get(rec["var_id"])
    if vslug is None:
        vslug = next((vs for i, vs in ID_TO_VAR.items() if i.lower() in stem), None)
    if vslug is None:
        return None, None, f"unknown variable '{rec['var_id']}'"
    norm = re.sub(r"[^a-z0-9]+", "_", stem)
    named = next((r for r in sorted(REGIONS, key=len, reverse=True) if r in norm), None)
    if rec["kind"] == "appeears":
        return (named, vslug, "request name") if named else (None, vslug, "AppEEARS file: name the request after the region")
    region, dist = closest_region(rec["bbox"], vslug)
    if region:
        return region, vslug, f"bbox (off by {dist:.2f}°)"
    if named:
        return named, vslug, "file name"
    for r in VARIABLES[vslug]["regions"]:          # e.g. a country shape named in the title
        if REGIONS[r]["name"].lower() in rec["title"].lower():
            return r, vslug, "title"
    return None, vslug, f"no region matches bbox {rec['bbox']}"


# ----------------------------------------------------------------------------- series building
def to_monthly(df):
    s = df.set_index("date")["value"].sort_index()
    s = s[~s.index.duplicated(keep="first")]
    daily = len(s) > 2 and pd.Series(s.index).diff().median() < pd.Timedelta(days=20)
    if daily:
        g = s.resample("MS")
        m = g.mean().where(g.count() >= MIN_DAYS_PER_MONTH)
    else:
        idx = s.index.to_period("M").to_timestamp()
        m = s.groupby(idx).mean()
    m.index.name = "date"
    return m.astype(float), bool(daily)


def convert_units(vslug, m, units_hint):
    notes = []
    valid = m.dropna()
    if valid.empty:
        return m, notes
    if vslug == "t2m" and valid.median() > 150:
        m, notes = m - 273.15, ["K -> °C"]
    elif vslug == "precip":
        unit = (units_hint or "mm/hr").lower()
        days = np.asarray(m.index.days_in_month, dtype=float)
        if "hr" in unit or "hour" in unit:
            m, notes = m * 24.0 * days, [f"{unit} -> mm/month"]
        elif "day" in unit:
            m, notes = m * days, [f"{unit} -> mm/month"]
        else:
            notes = [f"units '{unit}' treated as mm/month"]
        if units_hint is None:
            notes.append("units not found in file: assumed mm/hr (check the summary's mean value)")
    elif vslug == "no2" and valid.median() > 1e10:
        m, notes = m / 1e15, ["molecules/cm² -> ×10^15 molecules/cm²"]
    elif vslug == "ndvi" and valid.median() > 2:
        m, notes = m * 1e-4, ["NDVI scale factor 0.0001 applied"]
    return m, notes


def annualize(m, vslug):
    scale = VARIABLES[vslug]["annual_scale"]
    m = m.dropna()
    counts = m.groupby(m.index.year).size()
    years = sorted(int(y) for y in counts.index)
    while years and counts[years[0]] < 12:          # partial first year
        years.pop(0)
    while years and counts[years[-1]] < 12:         # partial last year (e.g. ongoing year)
        years.pop()
    keep = [y for y in years if counts[y] >= MIN_MONTHS_PER_YEAR]
    dropped = sorted(int(y) for y in counts.index if int(y) not in keep)
    m = m[m.index.year.isin(keep)]
    clim = m.groupby(m.index.month).mean()
    anom = m - clim.reindex(m.index.month).to_numpy()
    by_year = m.index.year
    annual = pd.DataFrame({
        "mean": m.groupby(by_year).mean() * scale,
        "anomaly": anom.groupby(anom.index.year).mean() * scale,
        "n_months": m.groupby(by_year).size(),
    })
    annual.index.name = "year"
    return m, anom, annual, clim, dropped


# ----------------------------------------------------------------------------- statistics
def years_needed(anom, slope_per_year):
    """Weatherhead et al. (1998): years needed to detect slope (90% probability, 5% level)."""
    if anom.size < 24 or not slope_per_year:
        return math.inf, None, None
    t = np.asarray(anom.index.year + (anom.index.month - 0.5) / 12.0, dtype=float)
    fit = stats.linregress(t, anom.to_numpy(dtype=float))
    resid = pd.Series(anom.to_numpy(dtype=float) - (fit.intercept + fit.slope * t), index=anom.index)
    full = resid.reindex(pd.date_range(resid.index.min(), resid.index.max(), freq="MS"))
    phi = full.autocorr(lag=1)
    phi = float(np.clip(phi if np.isfinite(phi) else 0.0, -0.9, 0.9))
    sigma = float(resid.std(ddof=1))
    n_star = ((3.3 * sigma / abs(slope_per_year)) * math.sqrt((1 + phi) / (1 - phi))) ** (2.0 / 3.0)
    return n_star, sigma, phi


def trend_stats(annual, anom, vslug):
    v = VARIABLES[vslug]
    yrs = annual.index.to_numpy(dtype=float)
    y = annual["anomaly"].to_numpy(dtype=float)
    n = int(len(y))
    res = {"n_years": n,
           "length_flag": "too_short" if n < MIN_YEARS else ("short" if n < OK_YEARS else "ok")}
    if n < 3:
        res.update({"verdict": "too_short", "direction": "no_clear_trend"})
        return res
    tau, p_mk = stats.kendalltau(yrs, y)
    ts = stats.theilslopes(y, yrs, alpha=0.95)
    lr = stats.linregress(yrs, y)
    tcrit = stats.t.ppf(0.975, n - 2)
    sig_mk, sig_ols = p_mk < ALPHA, lr.pvalue < ALPHA
    if n < MIN_YEARS:
        verdict = "too_short"
    elif sig_mk and sig_ols:
        verdict = "significant"
    elif sig_mk or sig_ols:
        verdict = "weak_evidence"
    else:
        verdict = "no_evidence"
    direction = "no_clear_trend"
    if verdict in ("significant", "weak_evidence"):
        direction = "increasing" if ts[0] > 0 else "decreasing"
    n_star, sigma, phi = years_needed(anom, ts[0] / v["annual_scale"])
    mean_level = float(annual["mean"].mean())
    pct = (ts[0] * 10 / abs(mean_level) * 100) if (v["pct"] and mean_level) else None
    res.update({
        "verdict": verdict, "direction": direction,
        "sen_slope_per_decade": ts[0] * 10, "sen_ci95_per_decade": [ts[2] * 10, ts[3] * 10],
        "sen_intercept": ts[1],
        "ols_slope_per_decade": lr.slope * 10,
        "ols_ci95_per_decade": [(lr.slope - tcrit * lr.stderr) * 10, (lr.slope + tcrit * lr.stderr) * 10],
        "ols_p": lr.pvalue, "mk_tau": tau, "mk_p": p_mk,
        "pct_of_mean_per_decade": pct,
        "total_change": ts[0] * (yrs[-1] - yrs[0]),
        "mean_level": mean_level,
        "years_needed": n_star if math.isfinite(n_star) else None,
        "period_enough": bool(n >= n_star) if math.isfinite(n_star) else False,
        "extra_years_needed": max(0, math.ceil(n_star - n)) if math.isfinite(n_star) else None,
        "noise_sigma_monthly": sigma, "noise_lag1_autocorr": phi,
    })
    return res


def bh_fdr(pvals):
    p = np.asarray(pvals, dtype=float)
    n = p.size
    if n == 0:
        return p
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(q, 0, 1)
    return out


# ----------------------------------------------------------------------------- plain-language text
def fmt_num(x):
    ax = abs(x)
    if ax == 0:
        return "0"
    if ax >= 100:
        return f"{x:,.0f}"
    if ax >= 10:
        return f"{x:.1f}"
    if ax >= 1:
        return f"{x:.2f}"
    return f"{x:.2g}"


def fmt_p(p):
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def summary_text(vslug, rslug, tr, y0, y1):
    v, r = VARIABLES[vslug], REGIONS[rslug]
    where = "worldwide (global average)" if rslug == "global" else f"over {r['name']}"
    units, n = v["annual_units"], tr["n_years"]
    if tr["verdict"] == "too_short" or "sen_slope_per_decade" not in tr:
        return f"Only {n} years of {v['name']} data {where}: too short to judge a trend (at least {MIN_YEARS} are needed)."
    rate = tr["sen_slope_per_decade"]
    word = "rising" if rate > 0 else "falling"
    pct = tr.get("pct_of_mean_per_decade")
    rel = f", about {abs(pct):.0f}% of its average level," if pct is not None and abs(pct) >= 0.5 else ""
    if tr["verdict"] == "significant":
        text = (f"{v['name']} {where} is {word} by about {fmt_num(abs(rate))} {units}{rel} per decade ({y0}–{y1}). "
                f"This trend is statistically significant ({fmt_p(tr['mk_p'])}): it is very unlikely to be chance.")
    elif tr["verdict"] == "weak_evidence":
        text = (f"{v['name']} {where} may be {word} (about {fmt_num(abs(rate))} {units} per decade, {y0}–{y1}), "
                f"but the evidence is weak: one of our two tests finds it significant and the other does not.")
    else:
        text = (f"{v['name']} {where} shows no clear trend ({y0}–{y1}). The estimated change of "
                f"{fmt_num(rate)} {units} per decade could be chance ({fmt_p(tr['mk_p'])}).")
        need = tr.get("years_needed")
        if need and need > n and need < 200:
            text += f" If it kept going at this rate, about {math.ceil(need)} years of data would be needed to detect it; we have {n}."
    if tr["length_flag"] == "short":
        text += f" The record is short ({n} years), so treat this with caution."
    return text


# ----------------------------------------------------------------------------- output
def clean(x):
    """JSON-safe: numpy -> python, NaN/inf -> None, floats to 6 significant digits."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        x = float(x)
        return None if not math.isfinite(x) else float(f"{x:.6g}")
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def plot_series(path, vslug, rslug, monthly, annual, tr):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    v, r = VARIABLES[vslug], REGIONS[rslug]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6.2))
    a1.plot(monthly.index, monthly.values, lw=0.7, color="#9aa9b5", label="monthly")
    a1.plot(monthly.rolling(12, center=True, min_periods=9).mean(), lw=2, color="#1b5b8e", label="12-month mean")
    a1.set_ylabel(v["units"])
    a1.legend(frameon=False, fontsize=8, loc="upper left")
    a1.grid(alpha=0.3)
    yrs = annual.index.to_numpy(dtype=float)
    a2.axhline(0, color="#586776", lw=0.8)
    a2.bar(yrs, annual["anomaly"], width=0.8, color="#b9c6d2")
    if "sen_slope_per_decade" in tr:
        slope = tr["sen_slope_per_decade"] / 10
        a2.plot(yrs, tr["sen_intercept"] + slope * yrs, color="#c0392b", lw=2,
                label=f"Sen's slope: {fmt_num(tr['sen_slope_per_decade'])} {v['annual_units']}/decade")
        a2.legend(frameon=False, fontsize=8, loc="upper left")
    a2.set_ylabel(f"annual anomaly ({v['annual_units']})")
    a2.grid(alpha=0.3)
    fig.suptitle(f"{v['name']} — {r['name']}   [{tr['verdict'].replace('_', ' ')}]", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Trend Detective: raw CSVs -> trend JSON, summary table and plots")
    ap.add_argument("--raw", default=str(REPO_ROOT / "data" / "raw"))
    ap.add_argument("--out", default=str(HERE / "output"))
    ap.add_argument("--plots", default=str(HERE / "output" / "plots"))
    ap.add_argument("--no-plots", action="store_true")
    a = ap.parse_args(argv)
    raw, out, plots = Path(a.raw), Path(a.out), Path(a.plots)
    if not raw.is_dir():
        sys.exit(f"Folder '{raw}' not found. Put the downloaded CSV files in it.")
    out.mkdir(parents=True, exist_ok=True)
    if not a.no_plots:
        plots.mkdir(parents=True, exist_ok=True)

    groups, problems = {}, []
    for path in sorted(raw.glob("*.csv")):
        low = path.name.lower()
        if "statistics-qa" in low or "granule" in low:
            continue
        rec = read_giovanni(path) or read_appeears(path)
        if rec is None:
            problems.append(f"{path.name}: not a Giovanni time series or AppEEARS statistics file")
            continue
        region, vslug, how = identify(path, rec)
        if region is None:
            problems.append(f"{path.name}: {how}. Rename it to <region>__<variable>.csv")
            continue
        g = groups.setdefault((region, vslug), {"recs": [], "files": [], "how": set()})
        g["recs"].append(rec)
        g["files"].append(path.name)
        g["how"].add(how)

    series = []
    for (rslug, vslug), g in sorted(groups.items()):
        v = VARIABLES[vslug]
        df = pd.concat([rec["df"] for rec in g["recs"]], ignore_index=True)
        monthly, daily = to_monthly(df)
        units_hint = next((rec["units_hint"] for rec in g["recs"] if rec["units_hint"]), None)
        monthly, notes = convert_units(vslug, monthly, units_hint)
        kept, anom, annual, clim, dropped = annualize(monthly, vslug)
        if annual.empty:
            problems.append(f"{rslug}/{vslug}: no complete year of data")
            continue
        tr = trend_stats(annual, anom, vslug)
        y0, y1 = int(annual.index.min()), int(annual.index.max())
        tr["summary"] = summary_text(vslug, rslug, tr, y0, y1)
        mrec = pd.DataFrame({"value": monthly, "anomaly": anom.reindex(monthly.index)})
        doc = {
            "region": {"slug": rslug, **REGIONS[rslug], "bbox": list(region_bbox(vslug, rslug))},
            "variable": {"slug": vslug, **{k: v[k] for k in ("name", "name_ar", "definition", "source",
                                                             "citation", "units", "annual_units")},
                         "dataset_id": v["ids"][0]},
            "period": {"start_year": y0, "end_year": y1, "n_years": tr["n_years"]},
            "monthly": [{"date": d.strftime("%Y-%m"), "value": row["value"], "anomaly": row["anomaly"]}
                        for d, row in mrec.iterrows()],
            "annual": [{"year": int(y), "mean": row["mean"], "anomaly": row["anomaly"],
                        "n_months": int(row["n_months"])} for y, row in annual.iterrows()],
            "climatology": {int(k): val for k, val in clim.items()},
            "trend": tr,
            "quality": {"raw_files": g["files"], "matched_by": sorted(g["how"]), "daily_input": daily,
                        "months_valid": int(kept.size), "years_dropped": dropped, "unit_notes": notes},
            "source": {"tool": "AppEEARS" if v["tool"] == "appeears" else "Giovanni (Time Series, Area-Averaged)",
                       "reproduce_url": next((rec["url"] for rec in g["recs"] if rec["url"]), "")},
        }
        series.append(doc)

    # multiple testing across everything we analysed
    ps = [s["trend"].get("mk_p", np.nan) for s in series]
    finite = [i for i, p in enumerate(ps) if p is not None and np.isfinite(p)]
    q = bh_fdr([ps[i] for i in finite])
    for i, qi in zip(finite, q):
        series[i]["trend"]["mk_p_fdr"] = qi
        series[i]["trend"]["significant_after_fdr"] = bool(qi < ALPHA)

    index = []
    for s in series:
        r, vv, tr = s["region"]["slug"], s["variable"]["slug"], s["trend"]
        fname = f"{r}__{vv}.json"
        (out / fname).write_text(json.dumps(clean(s), ensure_ascii=False, indent=1), encoding="utf-8")
        index.append({"region": r, "variable": vv, "file": fname,
                      "start_year": s["period"]["start_year"], "end_year": s["period"]["end_year"],
                      "n_years": tr["n_years"], "verdict": tr["verdict"], "direction": tr["direction"],
                      "rate_per_decade": tr.get("sen_slope_per_decade"),
                      "units": VARIABLES[vv]["annual_units"], "mk_p": tr.get("mk_p"),
                      "mk_p_fdr": tr.get("mk_p_fdr"), "summary": tr["summary"]})
        if not a.no_plots:
            try:
                import matplotlib  # noqa: F401
            except ImportError:
                print("matplotlib not installed: skipping plots (pip install matplotlib)")
                a.no_plots = True
                continue
            monthly = pd.Series([m["value"] for m in s["monthly"]],
                                index=pd.to_datetime([m["date"] for m in s["monthly"]]), dtype=float)
            annual = pd.DataFrame(s["annual"]).set_index("year")
            plot_series(plots / f"{r}__{vv}.png", vv, r, monthly, annual, tr)

    expected = {(d["region"], d["variable"]) for d in downloads()}
    missing = sorted(expected - set(groups))
    meta = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "regions": REGIONS, "variables": {k: {kk: vv for kk, vv in v.items() if kk != "regions"}
                                              for k, v in VARIABLES.items()},
            "method": METHOD, "series": index,
            "missing": [f"{r}__{v}" for r, v in missing]}
    (out / "index.json").write_text(json.dumps(clean(meta), ensure_ascii=False, indent=1), encoding="utf-8")
    pd.DataFrame(index).drop(columns=["summary"]).to_csv(out / "summary.csv", index=False)

    print("\n%-13s %-14s %9s %10s %12s %8s  %s" % ("region", "variable", "years", "mean", "rate/decade",
                                                  "MK p", "verdict"))
    for s in series:
        tr = s["trend"]
        rate, level, p = tr.get("sen_slope_per_decade"), tr.get("mean_level"), tr.get("mk_p")
        span = "%d-%d" % (s["period"]["start_year"], s["period"]["end_year"])
        print("%-13s %-14s %9s %10s %12s %8s  %s" % (
            s["region"]["slug"], s["variable"]["slug"], span,
            fmt_num(level) if level is not None else "", fmt_num(rate) if rate is not None else "",
            "%.3f" % p if p is not None else "", tr["verdict"]))
    print(f"\n{len(series)} series -> {out}/  (index.json, summary.csv)" + ("" if a.no_plots else f", plots -> {plots}/"))
    if missing:
        print(f"Not downloaded yet ({len(missing)}): " + ", ".join(f"{r}__{v}" for r, v in missing))
    for p in problems:
        print("WARNING:", p)


if __name__ == "__main__":
    main()
