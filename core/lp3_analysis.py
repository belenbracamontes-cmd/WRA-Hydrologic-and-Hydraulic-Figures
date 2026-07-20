"""Log-Pearson Type III flood frequency analysis -- core math and plotting.

Ported from a tkinter/ipywidgets notebook GUI. Streamlit-agnostic on purpose,
same pattern as core/peak_flow.py and core/annual_flow_chart.py.

KEY IMPLEMENTATION NOTES (unchanged from the original):
  - Quantiles use the Wilson-Hilferty (WH) approximation -- same as USGS
    Peakfq. This avoids the bounded-support artifact from scipy.pearson3.isf()
    which produces a spurious linear section at high AEP for negative-skew
    records.
  - Variance of estimate uses Kite (1977) / Bulletin 17C approximation,
    appropriate for systematic records without historical or censored data.
  - For sites with PILFs or historical data, full EMA (Cohn et al. 2001)
    would give slightly different variance values -- implement via PeakFQ.
  - Confidence limits use z (standard normal) per B17C eq. 7-31.
"""

from io import StringIO

import numpy as np
import pandas as pd
import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib import rcParams
from scipy.stats import norm

rcParams["font.family"]     = "Verdana"
rcParams["font.sans-serif"] = ["Verdana"]
rcParams["axes.titlesize"]  = 13
rcParams["axes.labelsize"]  = 11
rcParams["xtick.labelsize"] = 9
rcParams["ytick.labelsize"] = 9

# Standard and extrapolated return periods offered in the UI.
RP_STD = [2, 5, 10, 25, 50, 100]
RP_EXT = [200, 500, 1000]

# AEP ticks for the bottom axis (%, same as Peakfq / B17C Figure 10-13)
AEP_TICKS_PCT = [99.5, 99, 95, 90, 80, 65, 50, 35, 20, 10, 5, 4, 2, 1,
                 0.5, 0.2, 0.1]


# ══════════════════════════════════════════════════════════════════════════
#  LP3 MATH -- Wilson-Hilferty approximation (matches USGS Peakfq)
# ══════════════════════════════════════════════════════════════════════════

def lp3_fit(peak_va_series):
    """
    Fit Log-Pearson Type III to annual peak flows.
    Returns dict: mean_log, std_log, skew_log (sample), n, logq.
    Uses sample statistics (unbiased) per Bulletin 17C.
    """
    q = peak_va_series.dropna().values
    q = q[q > 0]
    logq = np.log10(q)
    n = len(logq)
    mean = np.mean(logq)
    std = np.std(logq, ddof=1)
    skew = (n / ((n - 1) * (n - 2))) * np.sum(((logq - mean) / std) ** 3)
    return {"mean_log": mean, "std_log": std, "skew_log": skew,
            "n": n, "logq": logq}


def wh_K(z, g):
    """
    Wilson-Hilferty frequency factor K for skew g and standard normal deviate z.
    This is the same approximation used by USGS Peakfq / Bulletin 17C.
    K maps z -> the LP3 frequency factor so that log(Q_p) = mean + K*std.
    For g ~ 0, reduces to K = z (normal distribution).
    """
    if abs(g) < 1e-6:
        return z
    return (2.0 / g) * ((1.0 + g * z / 6.0 - g**2 / 36.0)**3 - 1.0)


def lp3_quantile(params, aep):
    """
    LP3 quantile at given AEP using Wilson-Hilferty approximation.
    aep in (0,1). Returns discharge in cfs.
    Uses ppf of 1-aep (survival function equivalent) so small AEP -> large flow.
    """
    z = norm.ppf(1.0 - aep)
    K = wh_K(z, params["skew_log"])
    logq = params["mean_log"] + K * params["std_log"]
    return 10.0 ** logq


def lp3_variance_and_ci(params, aep, alpha=0.05):
    """
    Variance of log-quantile estimate and 2.5%/97.5% confidence limits.

    Variance formula: Kite (1977), Bulletin 17C approximation.
      Var(log Q_p) = s^2 x [(1 + K*g/6 + K^2*(1 - g^2/4)) / n  +  K^2 / (2*(n-1))]
    where K is the WH frequency factor.

    Confidence limits use z (standard normal) per B17C eq. 7-31:
      CI = 10^(log Q_p +/- z_{1-alpha/2} x sqrt(Var))
    This is appropriate for large-sample systematic records.

    Returns: (variance_of_log_estimate, lower_cfs, upper_cfs)
    """
    n = params["n"]
    g = params["skew_log"]
    s = params["std_log"]
    z = norm.ppf(1.0 - aep)
    K = wh_K(z, g)
    logq = params["mean_log"] + K * s

    a = 1.0 + K * g / 6.0 + K**2 * (1.0 - g**2 / 4.0)
    var_logq = s**2 * (abs(a) / n + K**2 / (2.0 * (n - 1)))

    z_crit = norm.ppf(1.0 - alpha / 2.0)
    se = np.sqrt(var_logq)
    lower = 10.0 ** (logq - z_crit * se)
    upper = 10.0 ** (logq + z_crit * se)
    return var_logq, lower, upper


def plotting_positions(logq_sorted, n):
    """Weibull plotting positions: P(X >= x_i) = rank / (n+1), returns in (0,1)."""
    ranks = np.arange(1, n + 1)
    return ranks / (n + 1)


# ══════════════════════════════════════════════════════════════════════════
#  DATA FETCH
# ══════════════════════════════════════════════════════════════════════════

def hydro_year(date):
    return date.year + 1 if date.month >= 10 else date.year


def fetch_usgs_peaks(station_id):
    """Pull USGS peak-flow RDB, return tidy DataFrame [year, peak_va]."""
    urls = [
        f"https://nwis.waterdata.usgs.gov/usa/nwis/peak?site_no={station_id}&agency_cd=USGS&format=rdb",
        f"https://waterdata.usgs.gov/nwis/peak?site_no={station_id}&agency_cd=USGS&format=rdb",
    ]
    resp = None
    for url in urls:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        if "peak_dt" in r.text or "peak_va" in r.text:
            resp = r
            break
    if resp is None:
        raise ValueError(f"No RDB data for station {station_id}.")

    lines = [l for l in resp.text.splitlines() if l.strip() and not l.startswith("#")]
    if len(lines) < 3:
        raise ValueError(f"No data returned for station {station_id}.")

    header = lines[0]
    n_cols = len(header.split("\t"))
    records = lines[2:]
    good = [l for l in records if len(l.split("\t")) == n_cols]
    if not good:
        raise ValueError(f"Station {station_id}: no data rows matched header.")

    df = pd.read_csv(StringIO("\n".join([header] + good)), sep="\t", low_memory=False)
    if "peak_va" not in df.columns or "peak_dt" not in df.columns:
        raise ValueError(f"Columns 'peak_dt'/'peak_va' not found for {station_id}.")

    df = df[["peak_dt", "peak_va"]].dropna(subset=["peak_va"])
    df["peak_va"] = pd.to_numeric(df["peak_va"], errors="coerce")
    df["peak_dt"] = pd.to_datetime(df["peak_dt"], errors="coerce")
    df = df.dropna(subset=["peak_va", "peak_dt"])
    df["year"] = df["peak_dt"].apply(hydro_year)
    return df.groupby("year", as_index=False)["peak_va"].max().dropna(subset=["peak_va"])


# ══════════════════════════════════════════════════════════════════════════
#  PROBABILITY AXIS HELPERS
# ══════════════════════════════════════════════════════════════════════════

def aep_to_normal(aep_pct):
    """AEP% -> standard-normal deviate (for linear probability axis)."""
    p = np.clip(np.asarray(aep_pct, dtype=float) / 100.0, 1e-9, 1 - 1e-9)
    return norm.ppf(p)


# ══════════════════════════════════════════════════════════════════════════
#  MAIN PLOT FUNCTION
# ══════════════════════════════════════════════════════════════════════════

def make_lp3_plot(datasets, custom_title="", show_ci=True, rp_list=None):
    """
    datasets: list of dicts {peak_va, station_id, label, color}
    rp_list: return periods (yr) to tabulate
    Returns: (fig, summary) where summary is a dict label -> list of row dicts.
    """
    if rp_list is None:
        rp_list = RP_STD

    aep_fine_pct = np.concatenate([
        np.linspace(99.5, 95, 50),
        np.linspace(95, 10, 200),
        np.linspace(10, 0.1, 250),
    ])
    aep_fine = aep_fine_pct / 100.0
    x_fine = aep_to_normal(aep_fine_pct)

    fig, ax = plt.subplots(figsize=(14, 8))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    all_summary = {}

    for d in datasets:
        params = lp3_fit(d["peak_va"])
        color = d["color"]
        label = d["label"] or f"Station {d['station_id']}"

        q_curve = np.array([lp3_quantile(params, a) for a in aep_fine])
        ax.semilogy(x_fine, q_curve, color=color, linewidth=2.0,
                    label=f"{label} — LP3 fit", zorder=4)

        if show_ci:
            ci_lo = np.array([lp3_variance_and_ci(params, a)[1] for a in aep_fine])
            ci_hi = np.array([lp3_variance_and_ci(params, a)[2] for a in aep_fine])
            ax.semilogy(x_fine, ci_lo, color=color, linewidth=1.0,
                        linestyle="--", alpha=0.7,
                        label=f"{label} — Lower 2.5% confidence limit")
            ax.semilogy(x_fine, ci_hi, color=color, linewidth=1.0,
                        linestyle="--", alpha=0.7,
                        label=f"{label} — Upper 97.5% confidence limit")
            ax.fill_between(x_fine, ci_lo, ci_hi, color=color, alpha=0.08)

        logq_sorted = np.sort(params["logq"])[::-1]
        obs_aep = plotting_positions(logq_sorted, params["n"])
        obs_x = aep_to_normal(obs_aep * 100.0)
        obs_q = 10.0 ** logq_sorted
        ax.semilogy(obs_x, obs_q, marker="o", linestyle="none",
                    color="black", markerfacecolor="white",
                    markersize=5, markeredgewidth=0.8,
                    label=f"{label} — annual peak", zorder=5)

        rows = []
        for rp in rp_list:
            aep_rp = 1.0 / rp
            q_design = lp3_quantile(params, aep_rp)
            var_est, lo, hi = lp3_variance_and_ci(params, aep_rp)
            rows.append({
                "Return Period": f"{rp}-yr",
                "AEP (%)": f"{aep_rp*100:.4g}",
                "EMA Estimate (cfs)": f"{q_design:,.0f}",
                "Variance of Estimate": f"{var_est:.5f}",
                "Lower 2.5% Confidence Limit": f"{lo:,.0f}",
                "Upper 97.5% Confidence Limit": f"{hi:,.0f}",
            })
        all_summary[label] = rows

    x_ticks = aep_to_normal(AEP_TICKS_PCT)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels([str(v) for v in AEP_TICKS_PCT],
                       fontsize=8.5, fontfamily="Verdana")
    ax.set_xlim(aep_to_normal(99.5), aep_to_normal(0.1))
    ax.set_xlabel("Annual Exceedance Probability, in percent",
                  fontsize=11, fontfamily="Verdana")

    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{int(y):,}"))
    ax.yaxis.set_minor_formatter(ticker.NullFormatter())
    ax.set_ylabel("Annual Peak Discharge (cfs)", fontsize=11, fontfamily="Verdana")

    ax2 = ax.twiny()
    rp_top = [1.01, 1.05, 1.11, 1.25, 2, 5, 10, 25, 50, 100, 200, 500, 1000]
    rp_aep_pct = [100.0 / r for r in rp_top]
    rp_top = [r for r, a in zip(rp_top, rp_aep_pct) if 0.1 <= a <= 99.5]
    rp_aep_pct = [100.0 / r for r in rp_top]
    rp_x = aep_to_normal(rp_aep_pct)
    ax2.set_xlim(ax.get_xlim())
    ax2.set_xticks(rp_x)
    ax2.set_xticklabels([str(r) if r >= 1 else f"{r:.2f}" for r in rp_top],
                        fontsize=8, fontfamily="Verdana")
    ax2.set_xlabel("Return Period (years)", fontsize=10, fontfamily="Verdana", labelpad=4)

    ax.grid(True, which="both", linestyle=":", linewidth=0.5, alpha=0.6)

    title_str = (custom_title.strip() if custom_title.strip()
                 else "Log-Pearson Type III Flood Frequency Analysis\n" +
                      " | ".join(d["label"] or f"Station {d['station_id']}"
                                 for d in datasets))
    ax.set_title(title_str, fontsize=13, fontweight="bold",
                 fontfamily="Verdana", pad=28)

    handles, labels_leg = ax.get_legend_handles_labels()
    seen, h2, l2 = set(), [], []
    for h, l in zip(handles, labels_leg):
        if l not in seen:
            seen.add(l)
            h2.append(h)
            l2.append(l)
    leg = ax.legend(h2, l2, fontsize=9.5, framealpha=0.9, loc="upper left")
    for t in leg.get_texts():
        t.set_fontfamily("Verdana")

    meta = "  |  ".join(
        f"n = {lp3_fit(d['peak_va'])['n']} yrs  •  "
        f"skew = {lp3_fit(d['peak_va'])['skew_log']:.3f}"
        for d in datasets
    )
    fig.text(0.5, 0.01, meta, ha="center", va="bottom",
             fontsize=8, fontfamily="Verdana", color="#555555")

    fig.tight_layout(rect=[0, 0.03, 1, 1])
    return fig, all_summary


def lp3_params_table(datasets):
    """DataFrame of fitted LP3 parameters (mean/std/skew/n) per station."""
    rows = []
    for d in datasets:
        p = lp3_fit(d["peak_va"])
        name = d["label"] or f"Station {d['station_id']}"
        rows.append({
            "Station": name,
            "n": p["n"],
            "Mean (log10)": round(p["mean_log"], 4),
            "Std (log10)": round(p["std_log"], 4),
            "Skew (log10)": round(p["skew_log"], 4),
        })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════
#  DESIGN-FLOW TABLE FIGURE (report-style export, matches original SVG output)
# ══════════════════════════════════════════════════════════════════════════

def build_table_figure(summary):
    """
    Render each station's design-flow table as a matplotlib figure, stacked
    vertically, with rows for return periods > 100-yr highlighted as
    extrapolations. Returns the Figure (does not save).
    """
    fig_parts = [(title, pd.DataFrame(rows)) for title, rows in summary.items()]
    n_stations = len(fig_parts)
    n_cols = len(fig_parts[0][1].columns)
    total_rows = sum(len(df) for _, df in fig_parts)
    fig_h = max(3.0, 0.42 * (total_rows + 3 * n_stations + 2))
    fig_w = max(12, 2.2 * n_cols)

    fig, axes = plt.subplots(n_stations, 1, figsize=(fig_w, fig_h), squeeze=False)
    fig.patch.set_facecolor("white")

    for ax_row, (station_title, df_tbl) in zip(axes, fig_parts):
        ax = ax_row[0]
        ax.axis("off")
        n_c = len(df_tbl.columns)

        def _rp_val(s):
            try:
                return float(str(s).replace("-yr", "").replace(",", ""))
            except Exception:
                return 0

        row_colors = [
            ["#fff8e1" if _rp_val(row.get("Return Period", "0")) > 100 else "#ffffff"] * n_c
            for _, row in df_tbl.iterrows()
        ]

        tbl = ax.table(
            cellText=df_tbl.values, colLabels=df_tbl.columns.tolist(),
            cellColours=row_colors, colColours=["#d0e4f7"] * n_c,
            cellLoc="center", loc="center",
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)
        tbl.auto_set_column_width(col=list(range(n_c)))
        for (r, c), cell in tbl.get_celld().items():
            cell.set_edgecolor("#cccccc")
            cell.set_text_props(
                fontweight="bold" if r == 0 else "normal",
                fontfamily="Verdana",
            )
        ax.set_title(station_title, fontsize=11, fontweight="bold",
                     fontfamily="Verdana", pad=6, loc="left")

    fig.text(0.5, 0.005,
             "Rows with RP > 100-yr (yellow) are extrapolations beyond the period of record.",
             ha="center", va="bottom", fontsize=7.5, color="#888888", fontfamily="Verdana")
    fig.tight_layout(rect=[0, 0.025, 1, 1])
    return fig
