"""The federated node loop, factored out so the CLI (node.py) and the desktop client
(client_app.py) share ONE implementation. Nothing here transmits raw data: it extracts
features locally, then per round uploads only a PAIRWISE-MASKED integer count vector.
"""
import os
import secrets
import time

import httpx
import numpy as np

import dp as dpmod
import fed_common as fc
import modalities as mods
import secure_agg as sa

HERE = os.path.dirname(os.path.abspath(__file__))


def load_or_make_key(node_dir: str):
    """Ed25519 signing key, persisted 0600, stays local."""
    p = os.path.join(node_dir, "node_key.pem")
    if os.path.exists(p):
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        return fc.load_priv(open(p, "rb").read())
    k = fc.gen_key()
    os.makedirs(node_dir, exist_ok=True)
    try:
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(fc.priv_pem(k))
    except OSError:                      # e.g. read-only dir — key just isn't persisted
        pass
    return k


def _auth_headers(key: str = None, session: str = None) -> dict:
    """Headers a node attaches to every coordinator call: the shared access token and
    (for solo/isolated federations) this run's private session id."""
    h = {}
    if key:
        h["X-Fed-Key"] = key
    if session:
        h["X-Fed-Session"] = session
    return h


def fetch_schema(coord: str, key: str = None) -> dict:
    with httpx.Client(base_url=coord, timeout=30.0, headers=_auth_headers(key)) as c:
        r = c.get("/schema")
        if r.status_code == 401:
            raise RuntimeError("unauthorized — check the federation password")
        r.raise_for_status()
        return r.json()


def load_local(sch: dict, data=None, folder=None, modality=None, on_log=print):
    """Produce (X, y, key_dir) from a baked .npz OR a raw recordings folder, validating
    against the federation schema. Raises ValueError with a human message on any mismatch."""
    classes = sch["classes"]
    if folder:
        folder = folder if os.path.isabs(folder) else os.path.join(HERE, folder)
        mod_key = modality or sch.get("modality")
        if not mod_key:
            raise ValueError("federation published no modality; choose one explicitly")
        m = mods.get(mod_key)
        on_log(f"extracting '{mod_key}' features locally from {folder} …")
        X, y, _ = m.extract_folder(folder)
        y = np.asarray(y).astype(str)
        key_dir = folder
    else:
        data_path = data if os.path.isabs(data) else os.path.join(HERE, data)
        d = np.load(data_path)
        X, y = d["X"], np.asarray(d["y"]).astype(str)
        key_dir = os.path.dirname(data_path)

    if X.shape[0] == 0:
        raise ValueError("no usable recordings found in that folder")
    if X.shape[1] != sch["n_features"]:
        raise ValueError(f"feature mismatch: local {X.shape[1]} vs federation "
                         f"{sch['n_features']} — align the modality/pipeline")
    unknown = sorted(set(y.tolist()) - set(classes))
    if unknown:
        raise ValueError(f"labels {unknown} not in federation classes {classes}; put "
                         f"recordings under class subfolders (e.g. asd/ td/)")
    return X, y, key_dir


def run_node(coord, node_id, name, X, y, sch, rounds=5, seed=0,
             key_dir=None, on_log=print, on_round=None, should_stop=lambda: False,
             key=None, session=None):
    """Register (Ed25519 + ephemeral X25519), wait for the cohort, then each round build the
    SHARED data-independent trees, count LOCAL data, upload a MASKED count vector, and poll
    for the securely-aggregated global metric. Returns a summary dict.

    key      shared access token (X-Fed-Key) if the federation is password-protected.
    session  private session id (X-Fed-Session); auto-generated so a solo/isolated
             federation gives this run its own room. Pass one to resume a specific room."""
    classes = sch["classes"]
    session = session or secrets.token_hex(8)
    bounds = np.asarray(sch["feature_bounds"], dtype=float)
    dpc = sch["dp"]
    struct_seed, n_trees, depth = dpc["structure_seed"], dpc["trees_per_round"], dpc["depth"]
    n_samples = int(X.shape[0])
    key_dir = key_dir or os.path.join(HERE, "nodes", node_id)

    ed_key = load_or_make_key(key_dir)
    x_key = sa.gen_x25519()                              # ephemeral masking key for this run
    cli = httpx.Client(base_url=coord, timeout=120.0, headers=_auth_headers(key, session))
    summary = {"node_id": node_id, "n_samples": n_samples, "rounds_done": 0,
               "raw_bytes_sent": 0, "global_eps": 0.0, "fed_primary": None,
               "primary_metric": sch.get("primary_metric", "acc"), "ok": True, "error": None}
    try:
        r = cli.post("/register", json={
            "node_id": node_id, "name": name, "pubkey_pem": fc.pub_pem(ed_key).decode(),
            "x_pub": sa.x_pub_hex(x_key), "samples": n_samples}).json()
        if not r.get("ok"):
            summary.update(ok=False, error=f"register rejected: {r.get('error')}")
            on_log(f"register rejected: {r.get('error')}"); return summary
        on_log(f"{name}: {n_samples} local samples registered — waiting for cohort ({sch['cohort']})…")

        peers = None
        for _ in range(480):
            if should_stop():
                summary.update(ok=False, error="stopped"); return summary
            p = cli.get("/participants").json()
            if p["ready"]:
                peers = {q["node_id"]: sa.load_x_pub(q["x_pub"]) for q in p["participants"]}
                break
            time.sleep(0.5)
        if peers is None:
            summary.update(ok=False, error="cohort never completed")
            on_log("cohort never completed — aborting."); return summary
        on_log(f"cohort ready ({len(peers)} nodes); secure aggregation active.")

        for rd in range(1, rounds + 1):
            if should_stop():
                summary.update(error="stopped"); break
            trees = dpmod.build_shared_structure(struct_seed + rd, X.shape[1], bounds, depth, n_trees)
            counts = dpmod.count_on_shared(trees, X, y, classes, assign_seed=seed * 100 + rd)
            flat = dpmod.flatten_counts(counts)
            masked = [int(v) for v in sa.mask_counts(node_id, x_key, peers, rd, flat)]
            phash = fc.sha256_hex(fc._canon(masked))
            sig = ed_key.sign(f"{node_id}|{rd}|{n_samples}|{phash}".encode())
            resp = cli.post("/submit", json={"node_id": node_id, "round": rd,
                            "n_samples": n_samples, "masked": masked, "sig_hex": sig.hex()}).json()
            if not resp.get("ok"):
                summary.update(ok=False, error=f"round {rd}: {resp.get('error')}")
                on_log(f"round {rd} REJECTED: {resp.get('error')}"); break
            res = resp
            for _ in range(480):
                if should_stop():
                    break
                rr = cli.get(f"/round/{rd}").json()
                if rr.get("ready"):
                    res = rr; break
                time.sleep(0.3)
            val = res.get("fed_primary")
            summary.update(rounds_done=rd, global_eps=resp.get("global_eps"),
                           fed_primary=val)
            val_s = f"{val:.3f}" if isinstance(val, (int, float)) else "n/a"
            kb = len(fc._canon(masked)) / 1024
            on_log(f"round {rd}: raw sent = 0 bytes · masked counts uploaded ({kb:.0f} KB) · "
                   f"global ε {resp.get('global_eps'):.2f}/{resp.get('epsilon_budget')} · "
                   f"global {summary['primary_metric']} = {val_s}")
            if on_round:
                on_round(dict(summary))
    except Exception as e:                               # network/other — surface, don't crash UI
        summary.update(ok=False, error=f"{type(e).__name__}: {e}")
        on_log(f"error: {e}")
    finally:
        cli.close()
    on_log("done — only masked aggregates ever left this machine.")
    return summary
