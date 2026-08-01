"""The federated node loop, factored out so the CLI (node.py) and the desktop client
(client_app.py) share ONE implementation. Nothing here transmits raw data: it extracts
features locally, then per round uploads only a PAIRWISE-MASKED integer count vector.
"""
import json
import os
import secrets
import time

import httpx
import numpy as np

import client_config as ccfg
import dp as dpmod
import fed_common as fc
import invitations as invites
import modalities as mods
import secure_agg as sa

HERE = os.path.dirname(os.path.abspath(__file__))

RECONNECT_ATTEMPTS = 3        # re-enrol + rebuild masks this many times before giving up
ROUND_POLL_ATTEMPTS = 3600    # ≈18 min; outlives the coordinator's own round timeout, which
                              # is the authority on when a partial round is discarded


def load_client_config(path: str) -> dict:
    """Read an administrator-issued connection config into node settings.

    Version 2 files also carry the coordinator-signed institution invitation, which is
    forwarded verbatim at registration — this node never inspects or alters it; the
    coordinator is the only party that verifies the signature.
    """
    with open(os.path.expanduser(path), encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config, dict):
        raise ValueError("connection config must be a JSON object")
    if config.get("format") != ccfg.CLIENT_CONFIG_FORMAT:
        raise ValueError("not a GBA-DF connection configuration")
    if config.get("version") not in ccfg.SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported connection config version: {config.get('version')}")
    coord = ccfg.clean_coordinator_url(config.get("coordinator_url"))
    invitation = config.get("invitation")
    if invitation is not None and not isinstance(invitation, dict):
        raise ValueError("invitation must be a JSON object")
    return {"coord": coord, "password": config.get("password") or None,
            "node_id": config.get("node_id") or None,
            "name": config.get("display_name") or None,
            "modality": config.get("modality") or None, "invitation": invitation}


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


def coordinator_identity_result(advertised_pem: str, invitation: dict, coord: str) -> dict:
    """Compare a coordinator's advertised public key with the one named in our invitation.

    The invitation records the coordinator key it was issued against, so a node holding one
    can pin the coordinator with no separate fingerprint exchange. TLS still authenticates
    the transport and protects the payloads; this check is what makes a redirected or
    impersonating endpoint visible even when the transport was trusted for the wrong reason.

    Returns {"pinned", "expected", "actual", "transport_encrypted", "warning"}. Raises
    RuntimeError when the coordinator presents a different key.
    """
    expected = str((invitation or {}).get("coordinator_key_sha256") or "")
    result = {"pinned": False, "expected": expected, "actual": "",
              "transport_encrypted": str(coord).lower().startswith("https://"), "warning": ""}
    if not expected:
        result["warning"] = ("this configuration carries no coordinator key fingerprint — "
                             "the coordinator's identity cannot be pinned")
        return result
    try:
        result["actual"] = invites.coordinator_key_id(fc.load_pub(advertised_pem.encode()))
    except Exception as e:
        raise RuntimeError(f"coordinator did not return a usable public key: {e}")
    if not secrets.compare_digest(result["actual"], expected):
        raise RuntimeError(
            "coordinator identity mismatch: the server at this address does not hold the key "
            "that signed your invitation. Do not continue — confirm the address with the "
            "federation administrator.")
    result["pinned"] = True
    if not result["transport_encrypted"]:
        result["warning"] = ("the coordinator address is plain http:// — identity is pinned, but "
                             "the connection is not encrypted; a pilot deployment must use https")
    return result


def check_coordinator_identity(coord: str, invitation: dict, key: str = None) -> dict:
    """Fetch the coordinator's advertised public key and pin it against the invitation."""
    if not (invitation or {}).get("coordinator_key_sha256"):
        return coordinator_identity_result("", invitation, coord)
    with httpx.Client(base_url=coord, timeout=30.0, headers=_auth_headers(key)) as c:
        r = c.get("/pubkey")
        r.raise_for_status()
        advertised = r.text
    return coordinator_identity_result(advertised, invitation, coord)


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
             key=None, session=None, invitation=None):
    """Register (Ed25519 + ephemeral X25519), wait for the cohort, then each round build the
    SHARED data-independent trees, count LOCAL data, upload a count vector, and poll for the
    global metric. With a cohort of three or more the vector is pairwise-masked; cohort-1 is
    explicitly central-DP-only and has no masking peer. Returns a summary dict.

    key         shared access token (X-Fed-Key) if the federation is password-protected.
    session     private session id (X-Fed-Session); auto-generated so a solo/isolated
                federation gives this run its own room. Pass one to resume a specific room.
    invitation  the coordinator-signed institution invitation, when the federation enforces
                them. Sent verbatim at registration and bound there to this node's key."""
    classes = sch["classes"]
    session = session or secrets.token_hex(8)
    bounds = np.asarray(sch["feature_bounds"], dtype=float)
    dpc = sch["dp"]
    secure_mode = bool(sch.get("secure_aggregation", int(sch.get("cohort", 1)) >= 3))
    count_label = "pairwise-masked vector" if secure_mode else "unmasked count vector"
    struct_seed, n_trees, depth = dpc["structure_seed"], dpc["trees_per_round"], dpc["depth"]
    n_samples = int(X.shape[0])
    key_dir = key_dir or os.path.join(HERE, "nodes", node_id)

    ed_key = load_or_make_key(key_dir)
    x_key = sa.gen_x25519()                              # ephemeral masking key for this run
    cli = httpx.Client(base_url=coord, timeout=120.0, headers=_auth_headers(key, session))
    summary = {"node_id": node_id, "n_samples": n_samples, "rounds_done": 0,
               "raw_bytes_sent": 0, "global_eps": 0.0, "fed_primary": None,
               "primary_metric": sch.get("primary_metric", "acc"), "ok": True, "error": None,
               "current_round": None, "application_bytes_sent": 0,
               "application_bytes_received": 0, "masked_payload_bytes_sent": 0,
               "protocol_metadata_bytes_sent": 0,
               # live progress: without these the caller only learns anything once a whole
               # round has completed, so every counter reads zero while work is in flight
               "phase": "starting", "rounds_total": int(rounds), "cohort_size": int(sch["cohort"]),
               "cohort_seen": 0}

    def publish(phase=None):
        if phase:
            summary["phase"] = phase
        if on_round:
            on_round(dict(summary))

    def post_json(path, payload, masked_bytes=0):
        """Send and count the exact UTF-8 JSON application body (not HTTP/TLS overhead)."""
        body = fc._canon(payload)
        summary["application_bytes_sent"] += len(body)
        summary["masked_payload_bytes_sent"] += masked_bytes
        summary["protocol_metadata_bytes_sent"] += len(body) - masked_bytes
        response = cli.post(path, content=body, headers={"Content-Type": "application/json"})
        summary["application_bytes_received"] += len(response.content)
        return response.json()

    def get_json(path):
        response = cli.get(path)
        summary["application_bytes_received"] += len(response.content)
        return response.json()

    try:
        if invitation:
            # Pin the coordinator BEFORE anything is sent: a mismatch means this address is
            # not the federation we were invited to, so no counts should leave the machine.
            identity = check_coordinator_identity(coord, invitation, key=key)
            if identity["pinned"]:
                on_log(f"coordinator identity pinned to the key that signed your invitation "
                       f"({identity['actual'][:16]}…).")
            if identity["warning"]:
                on_log(f"warning: {identity['warning']}")
        enrol = {"node_id": node_id, "name": name,
                 "pubkey_pem": fc.pub_pem(ed_key).decode(),
                 "x_pub": sa.x_pub_hex(x_key), "samples": n_samples}
        if invitation:
            enrol["invitation"] = invitation
        elif sch.get("invitation_required"):
            on_log("this federation requires a signed institution invitation — "
                   "import the connection configuration your administrator issued.")
        r = post_json("/register", enrol)
        if not r.get("ok"):
            summary.update(ok=False, error=f"register rejected: {r.get('error')}")
            on_log(f"register rejected: {r.get('error')}"); return summary
        on_log(f"{name}: {n_samples} local samples registered — waiting for cohort ({sch['cohort']})…")
        publish("registered")

        def await_cohort():
            """Block until the enrolled cohort is complete, then return the peer masking keys
            and the fingerprint of the exact set those keys belong to.

            There is no deadline: institutions join a demo or a pilot minutes apart, and a
            timeout here silently drops the node from a cohort the others are still forming.
            The caller stays interruptible through should_stop() (the desktop client's Stop
            button, Ctrl+C for the CLI).
            """
            while True:
                if should_stop():
                    return None, ""
                p = get_json("/participants")
                if p["ready"]:
                    return ({q["node_id"]: sa.load_x_pub(q["x_pub"]) for q in p["participants"]},
                            p.get("cohort_sha256", ""))
                seen = len(p.get("participants") or [])
                if seen != summary["cohort_seen"]:
                    summary["cohort_seen"] = seen
                    on_log(f"waiting for the cohort — {seen}/{summary['cohort_size']} "
                           f"institutions connected…")
                publish("waiting_for_cohort")
                time.sleep(0.5)

        peers, cohort_sha = await_cohort()
        if peers is None:
            summary.update(ok=False, error="cohort never completed")
            on_log("cohort never completed — aborting."); return summary
        if secure_mode:
            on_log(f"cohort ready ({len(peers)} nodes); pairwise secure aggregation active.")
        else:
            on_log("single-node cohort ready; central DP active, secure aggregation inactive.")
        summary["cohort_seen"] = len(peers)
        publish("cohort_ready")

        def rejoin():
            """Re-enrol after the coordinator lost our registration or the cohort changed.

            The masking key is ephemeral, so the coordinator adopts the new one and drops any
            round built against the old peer set; we then rebuild this round's masks.
            """
            nonlocal peers, cohort_sha
            post_json("/register", dict(enrol))
            peers, cohort_sha = await_cohort()
            return peers is not None

        start_round = int(sch.get("next_round", 1))
        aborted = False
        for completed, rd in enumerate(range(start_round, start_round + rounds), start=1):
            if should_stop():
                summary.update(error="stopped"); break
            summary["current_round"] = rd
            publish("counting")
            trees = dpmod.build_shared_structure(struct_seed + rd, X.shape[1], bounds, depth, n_trees)
            counts = dpmod.count_on_shared(trees, X, y, classes, assign_seed=seed * 100 + rd)
            flat = dpmod.flatten_counts(counts)

            resp = None
            for attempt in range(RECONNECT_ATTEMPTS):
                masked = [int(v) for v in sa.mask_counts(node_id, x_key, peers, rd, flat)]
                masked_body = fc._canon(masked)
                phash = fc.sha256_hex(masked_body)
                sig = ed_key.sign(f"{node_id}|{rd}|{n_samples}|{phash}".encode())
                resp = post_json("/submit", {"node_id": node_id, "round": rd,
                                 "n_samples": n_samples, "masked": masked,
                                 "sig_hex": sig.hex(), "cohort_sha256": cohort_sha},
                                 masked_bytes=len(masked_body))
                if resp.get("ok") or resp.get("code") not in {"cohort_changed", "unregistered"}:
                    break
                if attempt == RECONNECT_ATTEMPTS - 1:
                    break
                on_log(f"round {rd}: {resp.get('error')} — re-enrolling and rebuilding masks…")
                if not rejoin():
                    break
            if not resp or not resp.get("ok"):
                summary.update(ok=False, error=f"round {rd}: {(resp or {}).get('error')}")
                on_log(f"round {rd} REJECTED: {(resp or {}).get('error')}"); break

            res = resp
            publish("submitted")            # the payload counters are only real from here on
            for _ in range(ROUND_POLL_ATTEMPTS):
                if should_stop():
                    break
                rr = get_json(f"/round/{rd}")
                if rr.get("ready"):
                    res = rr; break
                if rr.get("aborted"):
                    res = rr; break
                time.sleep(0.3)
            if not res.get("ready") and res.get("aborted"):
                missing = ", ".join(res.get("waiting_for") or []) or "another institution"
                summary.update(ok=False, error=f"round {rd} was discarded (waiting for {missing})")
                on_log(f"round {rd} was discarded by the coordinator — it never received every "
                       f"institution's submission (missing: {missing}). No epsilon was spent; "
                       f"re-run once the cohort is back.")
                aborted = True; break
            if not res.get("ready"):
                summary.update(ok=False, error=f"round {rd} did not complete in time")
                on_log(f"round {rd} is still waiting for "
                       f"{', '.join(res.get('waiting_for') or ['the rest of the cohort'])} — "
                       f"stopping rather than starting another round.")
                aborted = True; break
            val = res.get("fed_primary")
            global_eps = float(res.get("global_eps", resp.get("global_eps")) or 0.0)
            epsilon_budget = res.get("epsilon_budget", resp.get("epsilon_budget"))
            summary.update(rounds_done=completed, current_round=rd,
                           global_eps=global_eps, fed_primary=val,
                           metrics=res.get("metrics"))
            val_s = f"{val:.3f}" if isinstance(val, (int, float)) else "n/a"
            total_kb = summary["application_bytes_sent"] / 1024
            masked_kb = summary["masked_payload_bytes_sent"] / 1024
            on_log(f"round {rd}: raw sent = 0 bytes · JSON payload sent {total_kb:.1f} KB "
                   f"({count_label} {masked_kb:.1f} KB) · "
                   f"global ε {global_eps:.2f}/{epsilon_budget} · "
                   f"global {summary['primary_metric']} = {val_s}")
            publish("aggregated")
        if aborted and on_round:
            on_round(dict(summary))
    except Exception as e:                               # network/other — surface, don't crash UI
        summary.update(ok=False, error=f"{type(e).__name__}: {e}")
        on_log(f"error: {e}")
    finally:
        cli.close()
    sent = "pairwise-masked counts" if secure_mode else "integer leaf counts to the central-DP curator"
    on_log(f"done — no raw data left this machine; only {sent} and protocol metadata were sent.")
    return summary
