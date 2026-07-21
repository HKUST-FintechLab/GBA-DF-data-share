"""Offline verifier for exported GBA-DF audit evidence packages."""
import argparse
import base64
import json

import fed_common as fc


def verify_bundle(bundle: dict) -> dict:
    """Verify package signature, audit chain, node receipts, and optional model hash."""
    errors = []
    if bundle.get("format") != "gba-df-audit-bundle" or bundle.get("version") != 1:
        errors.append("unsupported bundle format/version")

    signed = {k: v for k, v in bundle.items()
              if k not in {"bundle_sha256", "bundle_signature"}}
    digest = fc.sha256_hex(fc._canon(signed))
    if digest != bundle.get("bundle_sha256"):
        errors.append("bundle SHA-256 mismatch")

    try:
        coord_pub = fc.load_pub(bundle["coordinator_public_key_pem"].encode())
        signature = base64.b64decode(bundle["bundle_signature"], validate=True)
        if not fc.verify_sig(coord_pub, signature, digest.encode()):
            errors.append("bundle signature invalid")
    except Exception:
        coord_pub = None
        errors.append("coordinator public key or bundle signature malformed")

    entries = bundle.get("audit_entries", [])
    if bundle.get("audit_count") != len(entries):
        errors.append("audit count mismatch")
    expected_tip = entries[-1].get("hash") if entries else "0" * 64
    if bundle.get("audit_tip") != expected_tip:
        errors.append("audit tip mismatch")
    if coord_pub is not None:
        audit = fc.Audit(fc.gen_key())
        audit.entries = entries
        if not audit.verify(coord_pub, expected_len=bundle.get("audit_count")):
            errors.append("audit hash chain or entry signature invalid")

    participants = bundle.get("participants", {})
    submit_entries = {(e.get("node"), e.get("detail", {}).get("round"),
                       e.get("payload_sha256"), e.get("detail", {}).get("n_samples"))
                      for e in entries if e.get("event") == "submit"}
    verified_receipts = 0
    for receipt in bundle.get("submission_receipts", []):
        try:
            node_id = receipt["node_id"]
            rnd = int(receipt["round"])
            n_samples = int(receipt["n_samples"])
            payload_hash = receipt["payload_sha256"]
            node_pub = fc.load_pub(participants[node_id]["pubkey_pem"].encode())
            message = f"{node_id}|{rnd}|{n_samples}|{payload_hash}".encode()
            if not fc.verify_sig(node_pub, bytes.fromhex(receipt["sig_hex"]), message):
                errors.append(f"node receipt signature invalid: {node_id} round {rnd}")
                continue
            if (node_id, rnd, payload_hash, n_samples) not in submit_entries:
                errors.append(f"node receipt missing matching audit entry: {node_id} round {rnd}")
                continue
            verified_receipts += 1
        except Exception:
            errors.append("malformed node submission receipt")

    model = bundle.get("model")
    if model is None:
        if bundle.get("model_sha256") is not None:
            errors.append("model hash present without a model")
    elif fc.sha256_hex(fc._canon(model)) != bundle.get("model_sha256"):
        errors.append("model SHA-256 mismatch")

    return {
        "ok": not errors,
        "errors": errors,
        "audit_entries": len(entries),
        "verified_submission_receipts": verified_receipts,
        "audit_tip": expected_tip,
        "model_included": model is not None,
    }


def main():
    parser = argparse.ArgumentParser(description="Verify a GBA-DF exported audit bundle")
    parser.add_argument("bundle", help="path to the exported audit JSON package")
    args = parser.parse_args()
    try:
        with open(args.bundle, encoding="utf-8") as f:
            bundle = json.load(f)
        result = verify_bundle(bundle)
    except Exception as e:
        print(f"INVALID: could not read bundle: {e}")
        raise SystemExit(1)
    if not result["ok"]:
        print("INVALID audit bundle")
        for error in result["errors"]:
            print(f"- {error}")
        raise SystemExit(1)
    print(f"VALID audit bundle · {result['audit_entries']} audit entries · "
          f"{result['verified_submission_receipts']} node receipts · "
          f"model {'included' if result['model_included'] else 'not yet available'}")
    print(f"audit tip: {result['audit_tip']}")


if __name__ == "__main__":
    main()
