"""Pairwise-masking secure aggregation (the core of Bonawitz et al., minus dropout
recovery). Lets the coordinator learn ONLY the SUM of nodes' count vectors, never any
individual node's vector.

Each ordered pair of nodes (a, b) derives a shared secret via X25519 key agreement and,
from it, a deterministic integer mask vector m_ab(round). Node a adds +m_ab, node b adds
-m_ab (mod 2^32). Summing all nodes' masked vectors cancels every pair's masks, leaving
the true sum; any single masked vector is uniform-looking mod 2^32.

Limitation (POC): requires ALL enrolled nodes to submit a round (no Shamir dropout
recovery). Honest-but-curious, non-colluding coordinator.
"""
import hashlib

import numpy as np
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

MOD = 1 << 32   # counts << MOD, so the unmasked total is recovered exactly


def gen_x25519():
    return X25519PrivateKey.generate()


def x_pub_hex(priv) -> str:
    from cryptography.hazmat.primitives import serialization
    raw = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                          serialization.PublicFormat.Raw)
    return raw.hex()


def load_x_pub(hex_str: str):
    return X25519PublicKey.from_public_bytes(bytes.fromhex(hex_str))


def _mask_vec(secret: bytes, rnd: int, size: int) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(secret + b"|r" + str(rnd).encode()).digest()[:8], "big")
    return np.random.default_rng(seed).integers(0, MOD, size=size, dtype=np.int64)


def mask_counts(my_id: str, my_priv, peers: dict, rnd: int, counts: np.ndarray) -> np.ndarray:
    """peers: {node_id: X25519PublicKey} (may include self; skipped). counts: 1-D int vector."""
    out = counts.astype(np.int64) % MOD
    for pid, ppub in peers.items():
        if pid == my_id:
            continue
        secret = my_priv.exchange(ppub)                 # X25519(my_priv, peer_pub) == X25519(peer, my)
        m = _mask_vec(secret, rnd, counts.size)
        out = (out + m) % MOD if my_id < pid else (out - m) % MOD
    return out % MOD


def secure_sum(masked_vectors) -> np.ndarray:
    """Sum masked vectors mod 2^32 -> the true element-wise sum (masks cancel)."""
    acc = np.zeros_like(masked_vectors[0], dtype=np.int64)
    for v in masked_vectors:
        acc = (acc + np.asarray(v, dtype=np.int64)) % MOD
    return acc % MOD
