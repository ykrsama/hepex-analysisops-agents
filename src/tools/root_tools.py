import uproot
import awkward as ak

def inspect_root_schema_tool(
    file_path: str,
    max_branches_per_tree: int = 200,
) -> dict:
    """
    Tool to inspect the schema of a ROOT file.

    Returns:
    {
      "tree_name": {
          "n_branches": int,
          "branches": [str, ...],
          "truncated": bool
      },
      ...
    }
    """
    schema = {}

    with uproot.open(file_path) as f:
        for key, classname in f.classnames().items():
            # uproot TTree classname usually contains "TTree"
            if "TTree" not in classname:
                continue

            try:
                tree = f[key]
                branches = list(tree.keys())
                schema[key] = {
                    "n_branches": len(branches),
                    "branches": branches[:max_branches_per_tree],
                    "truncated": len(branches) > max_branches_per_tree,
                }
            except Exception as e:
                schema[key] = {
                    "error": str(e)
                }

    return schema

def load_kinematics_tool(
    file_path: str,
    tree_name: str,
    branches: dict,            # {"pt": "...", "eta": "...", "phi": "...", "e": "...", "charge": "...?"}
    entry_start: int = 0,
    entry_stop: int = 200000,
    require_exactly_two: bool = True,
    require_opposite_charge: bool = False,
) -> dict:
    """
    Load lepton kinematics from ROOT file.

    Returns:
    {
      "n_events": int,
      "pt":  [[pt1, pt2], ...],
      "eta": [[eta1, eta2], ...],
      "phi": [[phi1, phi2], ...],
      "e":   [[e1, e2], ...],
      "selection": {...}
    }
    """
    needed = ["pt", "eta", "phi", "e"]
    for k in needed:
        if k not in branches:
            raise ValueError(f"Missing required branch mapping: {k}")

    branch_names = [branches[k] for k in needed]
    if "charge" in branches:
        branch_names.append(branches["charge"])

    with uproot.open(file_path) as f:
        tree = f[tree_name]
        arrs = tree.arrays(
            branch_names,
            entry_start=entry_start,
            entry_stop=entry_stop,
            library="ak",
        )

    pt = arrs[branches["pt"]]
    eta = arrs[branches["eta"]]
    phi = arrs[branches["phi"]]
    e = arrs[branches["e"]]

    mask = ak.ones_like(pt, dtype=bool)

    if require_exactly_two:
        mask = mask & (ak.num(pt) == 2)

    if require_opposite_charge and "charge" in branches:
        q = arrs[branches["charge"]]
        mask = mask & (ak.num(q) == 2) & (q[:, 0] * q[:, 1] < 0)

    pt = pt[mask]
    eta = eta[mask]
    phi = phi[mask]
    e = e[mask]

    return {
        "n_events": int(len(pt)),
        "pt": ak.to_list(pt),
        "eta": ak.to_list(eta),
        "phi": ak.to_list(phi),
        "e": ak.to_list(e),
        "selection": {
            "require_exactly_two": require_exactly_two,
            "require_opposite_charge": require_opposite_charge,
            "entry_range": [entry_start, entry_stop],
        },
    }
