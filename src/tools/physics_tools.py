from __future__ import annotations

from typing import Any, Dict, List, Sequence, Union
import numpy as np
import vector


Number = Union[int, float]


def _to_2d_float_array(x: Any, name: str) -> np.ndarray:
    """
    Convert x to a 2D numpy float array.
    Expected: list[list[number]] shape (n_events, n_objects)
    """
    arr = np.asarray(x, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be 2D array-like with shape (n_events, n_objects). Got ndim={arr.ndim}, shape={arr.shape}")
    if arr.shape[0] == 0:
        raise ValueError(f"{name} has zero events. shape={arr.shape}")
    if arr.shape[1] == 0:
        raise ValueError(f"{name} has zero objects per event. shape={arr.shape}")
    return arr


def _validate_shapes(pt: np.ndarray, eta: np.ndarray, phi: np.ndarray, e: np.ndarray) -> None:
    if pt.shape != eta.shape or pt.shape != phi.shape or pt.shape != e.shape:
        raise ValueError(
            f"Shape mismatch: pt{pt.shape}, eta{eta.shape}, phi{phi.shape}, e{e.shape}"
        )


def calc_dilepton_mass_tool(
    pt: Sequence[Sequence[Number]],
    eta: Sequence[Sequence[Number]],
    phi: Sequence[Sequence[Number]],
    e: Sequence[Sequence[Number]],
) -> Dict[str, Any]:
    """
    Tool: dilepton invariant mass per event.

    Inputs must have shape (n_events, 2).
    Returns:
      {
        "mass": [float, ...],  # length n_events
        "n_events": int,
        "n_objects": 2,
        "definition": "m((p4[0]+p4[1]).M)"
      }
    """
    pt_arr = _to_2d_float_array(pt, "pt")
    eta_arr = _to_2d_float_array(eta, "eta")
    phi_arr = _to_2d_float_array(phi, "phi")
    e_arr = _to_2d_float_array(e, "e")
    _validate_shapes(pt_arr, eta_arr, phi_arr, e_arr)

    if pt_arr.shape[1] != 2:
        raise ValueError(f"dilepton tool requires exactly 2 objects per event. Got shape {pt_arr.shape}")

    p4 = vector.array({"pt": pt_arr, "eta": eta_arr, "phi": phi_arr, "e": e_arr})
    mass = (p4[:, 0] + p4[:, 1]).M

    return {
        "mass": mass.astype(float).tolist(),
        "n_events": int(mass.shape[0]),
        "n_objects": 2,
        "definition": "m((p4[0]+p4[1]).M)",
    }


def calc_system_invariant_mass_tool(
    pt: Sequence[Sequence[Number]],
    eta: Sequence[Sequence[Number]],
    phi: Sequence[Sequence[Number]],
    e: Sequence[Sequence[Number]],
) -> Dict[str, Any]:
    """
    Tool: invariant mass of the sum of all objects per event.

    Inputs: shape (n_events, n_objects) with n_objects >= 1.
    Returns:
      {
        "mass": [float, ...],  # length n_events
        "n_events": int,
        "n_objects": int,
        "definition": "m(sum_i p4[i])"
      }
    """
    pt_arr = _to_2d_float_array(pt, "pt")
    eta_arr = _to_2d_float_array(eta, "eta")
    phi_arr = _to_2d_float_array(phi, "phi")
    e_arr = _to_2d_float_array(e, "e")
    _validate_shapes(pt_arr, eta_arr, phi_arr, e_arr)

    p4 = vector.array({"pt": pt_arr, "eta": eta_arr, "phi": phi_arr, "e": e_arr})
    p4_sum = p4.sum(axis=1)
    mass = p4_sum.M

    return {
        "mass": mass.astype(float).tolist(),
        "n_events": int(mass.shape[0]),
        "n_objects": int(pt_arr.shape[1]),
        "definition": "m(sum_i p4[i])",
    }
