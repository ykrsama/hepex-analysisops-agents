from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
import numpy as np

from scipy.optimize import curve_fit


def _gauss(x, A, mu, sigma):
    return A * np.exp(-0.5 * ((x - mu) / sigma) ** 2)

def _gauss_plus_const(x, A, mu, sigma, c):
    return _gauss(x, A, mu, sigma) + c

def _gauss_plus_linear(x, A, mu, sigma, c0, c1):
    return _gauss(x, A, mu, sigma) + (c0 + c1 * x)


_MODEL_FUNCS = {
    "gauss": (_gauss, 3),
    "gauss_plus_const": (_gauss_plus_const, 4),
    "gauss_plus_linear": (_gauss_plus_linear, 5),
}


def fit_peak_tool(
    values: List[float],
    window: List[float],
    bins: int = 120,
    model: str = "gauss_plus_const",
    min_count: int = 200,
) -> Dict[str, Any]:
    """
    Tool: fit a 1D peak in a specified window using a simple parametric model.

    Inputs
    ------
    values: list of floats
        Raw samples (e.g., invariant masses).
    window: (low, high)
        Fit window applied to values.
    bins: int
        Histogram bins used for fitting.
    model: str
        One of: "gauss", "gauss_plus_const", "gauss_plus_linear"
    min_count: int
        Minimum number of points in the window to attempt a fit.

    Returns
    -------
    dict:
      {
        "status": "ok" | "error",
        "model": str,
        "window": [low, high],
        "n_in_window": int,
        "fit": {"mu": float, "sigma": float, "A": float, ...},
        "errors": {"mu": float|None, "sigma": float|None, ...},
        "notes": str
      }
    """
    if model not in _MODEL_FUNCS:
        return {"status": "error", "notes": f"Unknown model '{model}'. Options: {list(_MODEL_FUNCS.keys())}"}

    low, high = float(window[0]), float(window[1])
    if not (low < high):
        return {"status": "error", "notes": f"Invalid window {window}. Expected low < high."}

    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    xw = x[(x >= low) & (x <= high)]

    n = int(xw.shape[0])
    if n < min_count:
        return {
            "status": "error",
            "model": model,
            "window": [low, high],
            "n_in_window": n,
            "notes": f"Not enough data in window (n={n} < min_count={min_count})."
        }

    # Histogram for stable fitting
    counts, edges = np.histogram(xw, bins=bins, range=(low, high))
    centers = 0.5 * (edges[:-1] + edges[1:])

    # Only fit bins with counts > 0 to avoid zero-weight weirdness
    mask = counts > 0
    xc = centers[mask]
    yc = counts[mask]

    if xc.size < 6:
        return {
            "status": "error",
            "model": model,
            "window": [low, high],
            "n_in_window": n,
            "notes": "Too few non-empty histogram bins to fit."
        }

    func, npar = _MODEL_FUNCS[model]

    # Initial guesses: peak near max bin
    i_max = int(np.argmax(yc))
    mu0 = float(xc[i_max])
    A0 = float(yc[i_max])
    # Rough sigma guess: window/10 but not too small
    sigma0 = max((high - low) / 10.0, 0.5)

    # Background guesses
    if model == "gauss":
        p0 = [A0, mu0, sigma0]
        bounds = ([0.0, low, 1e-3], [np.inf, high, (high - low)])
    elif model == "gauss_plus_const":
        c0 = float(np.median(yc))
        p0 = [A0, mu0, sigma0, c0]
        bounds = ([0.0, low, 1e-3, 0.0], [np.inf, high, (high - low), np.inf])
    else:  # gauss_plus_linear
        c00 = float(np.median(yc))
        c10 = 0.0
        p0 = [A0, mu0, sigma0, c00, c10]
        bounds = ([0.0, low, 1e-3, 0.0, -np.inf], [np.inf, high, (high - low), np.inf, np.inf])

    # Poisson-like uncertainties for histogram counts
    sigma_y = np.sqrt(yc)
    sigma_y[sigma_y == 0] = 1.0

    try:
        popt, pcov = curve_fit(
            func, xc, yc,
            p0=p0,
            sigma=sigma_y,
            absolute_sigma=True,
            bounds=bounds,
            maxfev=20000,
        )
    except Exception as e:
        return {
            "status": "error",
            "model": model,
            "window": [low, high],
            "n_in_window": n,
            "notes": f"Fit failed: {type(e).__name__}: {e}"
        }

    # Parameter names
    if model == "gauss":
        names = ["A", "mu", "sigma"]
    elif model == "gauss_plus_const":
        names = ["A", "mu", "sigma", "c"]
    else:
        names = ["A", "mu", "sigma", "c0", "c1"]

    fit = {k: float(v) for k, v in zip(names, popt)}

    # Errors if covariance is sensible
    errors: Dict[str, Optional[float]] = {k: None for k in names}
    if pcov is not None and np.all(np.isfinite(pcov)) and pcov.shape[0] == pcov.shape[1]:
        perr = np.sqrt(np.diag(pcov))
        for k, v in zip(names, perr):
            errors[k] = float(v)

    # Sanity: sigma positive
    if fit["sigma"] <= 0:
        return {
            "status": "error",
            "model": model,
            "window": [low, high],
            "n_in_window": n,
            "notes": f"Unphysical sigma={fit['sigma']}.",
            "fit": fit,
            "errors": errors,
        }

    return {
        "status": "ok",
        "model": model,
        "window": [low, high],
        "n_in_window": n,
        "fit": fit,
        "errors": errors,
        "notes": "Histogram-based fit in the given window.",
    }
