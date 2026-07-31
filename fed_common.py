"""Shared federated primitives: Ed25519 signing, a SIGNATURE-VERIFIED hash-chained
audit log, and a pickle-free forest exchange format.

  * Model updates are a constrained JSON tree schema (no pickle -> no RCE), bounds-checked.
  * Default privacy is CENTRAL differential privacy (see dp.py): a node ships INTEGER leaf
    histograms of data-INDEPENDENT random trees (validate_count_forest); the COORDINATOR adds
    the Laplace noise and meters epsilon, so epsilon is enforced, not self-declared. The
    resulting probability forest is consumed by JsonForest below. (serialize_forest /
    validate_forest support a non-private probability-forest path used only for baselines.)
  * Audit.verify() checks BOTH the SHA-256 hash chain AND each entry's Ed25519 signature
    against the coordinator's pinned public key.
"""
import base64
import hashlib
import json

import numpy as np
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_score,
    roc_auc_score,
    roc_curve,
)

TREE_LEAF = -1


# ---------- Ed25519 signing ----------
def gen_key():
    return ed25519.Ed25519PrivateKey.generate()


def priv_pem(k) -> bytes:
    return k.private_bytes(serialization.Encoding.PEM,
                           serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption())


def load_priv(pem: bytes):
    return serialization.load_pem_private_key(pem, password=None)


def pub_pem(k) -> bytes:
    return k.public_key().public_bytes(serialization.Encoding.PEM,
                                       serialization.PublicFormat.SubjectPublicKeyInfo)


def load_pub(pem: bytes):
    return serialization.load_pem_public_key(pem)


def verify_sig(pub, signature: bytes, message: bytes) -> bool:
    try:
        pub.verify(signature, message)
        return True
    except Exception:
        return False


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def cohort_fingerprint(participants) -> str:
    """Fingerprint of the exact (node_id, x_pub) set a round's masks were built against.

    Pairwise masks cancel only for one specific peer set, so a submission built against a
    different set would silently corrupt the pooled sum rather than fail. Both sides compute
    this from the same canonical form and the coordinator refuses to mix fingerprints.
    """
    pairs = sorted([str(node_id), str(x_pub)] for node_id, x_pub in participants)
    return sha256_hex(_canon(pairs))


# ---------- pickle-free forest exchange ----------
def serialize_forest(clf) -> dict:
    """Fitted ExtraTrees -> JSON-safe dict. Leaves carry normalised class
    proportions only (no counts, no n_node_samples)."""
    trees = []
    for est in clf.estimators_:
        tr = est.tree_
        val = tr.value.reshape(tr.value.shape[0], -1).astype(float)  # (n_nodes, C)
        s = val.sum(axis=1, keepdims=True)
        s[s == 0] = 1.0
        proba = val / s
        trees.append({
            "cl": tr.children_left.astype(int).tolist(),
            "cr": tr.children_right.astype(int).tolist(),
            "f": tr.feature.astype(int).tolist(),
            "t": np.round(tr.threshold, 6).tolist(),
            "v": np.round(proba, 5).tolist(),
        })
    return {"classes": [str(c) for c in clf.classes_], "trees": trees}


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def validate_forest(d, global_classes, n_features, max_trees=2000, max_nodes=400000) -> str:
    """Return '' if a STRUCTURALLY valid + bounds-safe forest payload, else a rejection
    reason. Never raises (any malformed input -> reason string). Guarantees the payload
    carries only tree arrays — no raw feature/label data — AND that every index is in
    range, so the pure-numpy predictor cannot crash on accepted input."""
    try:
        if not isinstance(d, dict) or set(d.keys()) != {"classes", "trees"}:
            return "schema: unexpected keys"
        classes = d["classes"]
        if not isinstance(classes, list) or not classes or not all(isinstance(c, str) for c in classes):
            return "schema: bad classes"
        if any(c not in global_classes for c in classes):
            return "schema: unknown class label"
        C = len(classes)
        trees = d["trees"]
        if not isinstance(trees, list) or not (0 < len(trees) <= max_trees):
            return "schema: tree count"
        total = 0
        for t in trees:
            if not isinstance(t, dict) or set(t.keys()) != {"cl", "cr", "f", "t", "v"}:
                return "schema: tree keys"
            cl, cr, f, th, v = t["cl"], t["cr"], t["f"], t["t"], t["v"]
            if not all(isinstance(a, list) for a in (cl, cr, f, th, v)):
                return "schema: tree arrays"
            n = len(cl)
            if n == 0:
                return "schema: empty tree"
            total += n
            if total > max_nodes:
                return "schema: too many nodes"
            if not (len(cr) == len(f) == len(th) == len(v) == n):
                return "schema: array length mismatch"
            if not all(_is_int(x) for x in cl) or not all(_is_int(x) for x in cr) or not all(_is_int(x) for x in f):
                return "schema: non-int index"
            if any(x < -1 or x >= n for x in cl) or any(x < -1 or x >= n for x in cr):
                return "schema: child index out of range"
            if any(x < -2 or x >= n_features for x in f):   # -2 = sklearn leaf marker
                return "schema: feature index out of range"
            if not all(_is_num(x) for x in th):
                return "schema: non-numeric threshold"
            for row in v:
                if not isinstance(row, list) or len(row) != C or not all(_is_num(x) for x in row):
                    return "schema: bad leaf vector"
        return ""
    except Exception as e:  # never throw — always a graceful rejection reason
        return f"schema: malformed ({type(e).__name__})"


def validate_count_forest(d, global_classes, n_features, max_trees=2000, max_nodes=400000) -> str:
    """Validate a NODE 'count forest' {classes, trees:[{cl,cr,f,t,n}]}: n are NON-NEGATIVE
    INTEGER leaf histograms (curator adds the DP noise). Never raises; bounds-checks indices."""
    try:
        if not isinstance(d, dict) or set(d.keys()) != {"classes", "trees"}:
            return "schema: unexpected keys"
        classes = d["classes"]
        if not isinstance(classes, list) or not classes or not all(isinstance(c, str) for c in classes):
            return "schema: bad classes"
        if any(c not in global_classes for c in classes):
            return "schema: unknown class label"
        C = len(classes)
        trees = d["trees"]
        if not isinstance(trees, list) or not (0 < len(trees) <= max_trees):
            return "schema: tree count"
        total = 0
        for t in trees:
            if not isinstance(t, dict) or set(t.keys()) != {"cl", "cr", "f", "t", "n"}:
                return "schema: tree keys"
            cl, cr, f, th, n = t["cl"], t["cr"], t["f"], t["t"], t["n"]
            if not all(isinstance(a, list) for a in (cl, cr, f, th, n)):
                return "schema: tree arrays"
            m = len(cl)
            if m == 0:
                return "schema: empty tree"
            total += m
            if total > max_nodes:
                return "schema: too many nodes"
            if not (len(cr) == len(f) == len(th) == len(n) == m):
                return "schema: array length mismatch"
            if not all(_is_int(x) for x in cl) or not all(_is_int(x) for x in cr) or not all(_is_int(x) for x in f):
                return "schema: non-int index"
            if any(x < -1 or x >= m for x in cl) or any(x < -1 or x >= m for x in cr):
                return "schema: child index out of range"
            if any(x < -2 or x >= n_features for x in f):
                return "schema: feature index out of range"
            if not all(_is_num(x) for x in th):
                return "schema: non-numeric threshold"
            for row in n:
                if not isinstance(row, list) or len(row) != C or not all(_is_int(x) and x >= 0 for x in row):
                    return "schema: bad count vector"
        return ""
    except Exception as e:
        return f"schema: malformed ({type(e).__name__})"


class JsonForest:
    """Pure-numpy predictor rebuilt from the JSON schema (no sklearn, no pickle)."""

    def __init__(self, d):
        self.classes = list(d["classes"])
        self.trees = [(np.asarray(t["cl"], int), np.asarray(t["cr"], int),
                       np.asarray(t["f"], int), np.asarray(t["t"], float),
                       np.asarray(t["v"], float)) for t in d["trees"]]

    @property
    def n_trees(self):
        return len(self.trees)

    def to_dict(self):
        """Rebuild the JSON schema {classes, trees:[{cl,cr,f,t,v}]} from the arrays."""
        return {"classes": list(self.classes),
                "trees": [{"cl": cl.astype(int).tolist(), "cr": cr.astype(int).tolist(),
                           "f": f.astype(int).tolist(),
                           "t": np.round(th, 6).tolist(),
                           "v": np.round(v, 5).tolist()}
                          for cl, cr, f, th, v in self.trees]}

    def predict_proba(self, X):
        X = np.asarray(X, float)
        n, C = X.shape[0], len(self.classes)
        agg = np.zeros((n, C))
        rows = np.arange(n)
        for cl, cr, f, th, v in self.trees:
            node = np.zeros(n, dtype=int)
            for _ in range(256):  # depth bound
                leaf = cl[node] == TREE_LEAF
                if leaf.all():
                    break
                fi = np.where(f[node] < 0, 0, f[node])
                go_left = X[rows, fi] <= th[node]
                nxt = np.where(go_left, cl[node], cr[node])
                node = np.where(leaf, node, nxt)
            agg += v[node]
        return agg / max(self.n_trees, 1)


# ---------- signed, hash-chained, signature-VERIFIED audit log ----------
class Audit:
    _FIELDS = ("seq", "ts", "event", "node", "detail", "payload_sha256", "prev_hash")

    def __init__(self, signer_key):
        self.entries = []
        self._signer = signer_key

    def append(self, event, node, detail, payload_sha256="", ts=0.0):
        prev = self.entries[-1]["hash"] if self.entries else "0" * 64
        body = {"seq": len(self.entries), "ts": ts, "event": event, "node": node,
                "detail": detail, "payload_sha256": payload_sha256, "prev_hash": prev}
        h = sha256_hex(_canon(body))
        sig = base64.b64encode(self._signer.sign(h.encode())).decode()
        entry = {**body, "hash": h, "sig": sig}
        self.entries.append(entry)
        return entry

    def verify(self, coord_pub, expected_len=None) -> bool:
        """Hash chain + per-entry Ed25519 signature against the PINNED coordinator
        public key + (optional) committed length (truncation check)."""
        if expected_len is not None and len(self.entries) != expected_len:
            return False
        prev = "0" * 64
        for i, e in enumerate(self.entries):
            if e["seq"] != i or e["prev_hash"] != prev:
                return False
            body = {k: e[k] for k in self._FIELDS}
            if sha256_hex(_canon(body)) != e["hash"]:
                return False
            if not verify_sig(coord_pub, base64.b64decode(e["sig"]), e["hash"].encode()):
                return False
            prev = e["hash"]
        return True


# ---------- global federated model (weighted ensemble of JsonForests) ----------
class GlobalModel:
    def __init__(self, classes):
        self.classes = [str(c) for c in classes]
        self._idx = {c: i for i, c in enumerate(self.classes)}
        self.parts = []  # (weight, JsonForest, node_id, round)

    def add(self, jf: JsonForest, weight: float, node_id: str, rnd: int):
        self.parts.append((float(weight), jf, node_id, rnd))

    def serialize(self) -> dict:
        """The whole aggregated global model as pickle-free JSON — a weighted ensemble of the
        per-round secure-aggregated DP forests. Consumers rebuild it with from_serialized()."""
        return {"classes": list(self.classes),
                "parts": [{"weight": w, "node_id": nid, "round": rnd, "forest": jf.to_dict()}
                          for w, jf, nid, rnd in self.parts]}

    @classmethod
    def from_serialized(cls, d: dict) -> "GlobalModel":
        m = cls(d["classes"])
        for p in d.get("parts", []):
            m.add(JsonForest(p["forest"]), float(p.get("weight", 1.0)),
                  p.get("node_id", "?"), int(p.get("round", 0)))
        return m

    def n_trees(self):
        return sum(jf.n_trees for _, jf, _, _ in self.parts)

    def n_updates(self):
        return len(self.parts)

    def predict_proba(self, X):
        if not self.parts:
            return None
        C = len(self.classes)
        agg = np.zeros((X.shape[0], C))
        wsum = 0.0
        for w, jf, _, _ in self.parts:
            p = jf.predict_proba(X)
            p2 = np.zeros((X.shape[0], C))
            for ci, cl in enumerate(jf.classes):
                if cl in self._idx:
                    p2[:, self._idx[cl]] = p[:, ci]
            agg += p2 * w
            wsum += w
        return agg / max(wsum, 1e-9)

    def evaluate(self, X, y) -> dict:
        proba = self.predict_proba(X)
        if proba is None:
            return {}
        y = np.asarray(y).astype(str)
        pred = np.array([self.classes[i] for i in proba.argmax(1)])
        result = {"acc": float(accuracy_score(y, pred)),
                  "bacc": float(balanced_accuracy_score(y, pred)),
                  "n_trees": self.n_trees(), "n_updates": self.n_updates()}
        try:
            if len(self.classes) == 2:
                # ASD is the clinically meaningful positive class when it is present.  The
                # explicit label also prevents a dashboard from silently calling TD recall
                # "sensitivity" merely because of alphabetic class ordering.
                positive = next((c for c in self.classes if c.upper() == "ASD"), self.classes[1])
                negative = next(c for c in self.classes if c != positive)
                positive_i = self._idx[positive]
                y_binary = (y == positive).astype(int)
                pred_binary = (pred == positive).astype(int)
                auc = float(roc_auc_score(y_binary, proba[:, positive_i]))
                tn, fp, fn, tp = confusion_matrix(
                    y, pred, labels=[negative, positive]).ravel().astype(int).tolist()
                sensitivity = tp / max(tp + fn, 1)
                specificity = tn / max(tn + fp, 1)
                fpr, tpr, _ = roc_curve(y_binary, proba[:, positive_i])
                # Status is polled every second, so keep the diagnostic curve compact.
                if len(fpr) > 32:
                    keep = np.unique(np.linspace(0, len(fpr) - 1, 32).round().astype(int))
                    fpr, tpr = fpr[keep], tpr[keep]
                confidence = proba[:, positive_i]
                ece = 0.0
                for lo, hi in zip(np.linspace(0.0, 1.0, 11)[:-1],
                                  np.linspace(0.0, 1.0, 11)[1:]):
                    in_bin = (confidence >= lo) & (confidence < hi)
                    if hi == 1.0:
                        in_bin |= confidence == 1.0
                    if in_bin.any():
                        ece += float(in_bin.mean()) * abs(
                            float(y_binary[in_bin].mean()) - float(confidence[in_bin].mean()))
                result.update({
                    "positive_class": positive,
                    "negative_class": negative,
                    "sensitivity": float(sensitivity),
                    "specificity": float(specificity),
                    "precision": float(precision_score(
                        y_binary, pred_binary, zero_division=0)),
                    "f1": float(f1_score(y_binary, pred_binary, zero_division=0)),
                    "mcc": float(matthews_corrcoef(y_binary, pred_binary)),
                    "brier": float(brier_score_loss(y_binary, confidence)),
                    "ece": float(ece),
                    "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
                    "roc": {"fpr": np.round(fpr, 5).tolist(),
                            "tpr": np.round(tpr, 5).tolist()},
                })
            else:
                auc = float(roc_auc_score(y, proba, multi_class="ovr",
                                          average="macro", labels=self.classes))
            if not np.isfinite(auc):
                auc = None
        except Exception:
            auc = None                       # None is JSON-safe; NaN is not
        result["auc"] = auc
        return result
