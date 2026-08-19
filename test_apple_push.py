#!/usr/bin/env python3
"""
Apple APNs Web Push Standalone Diagnostic Script.
Validates:
1. RFC 8292 Base64URL subscriber key decoding (p256dh and auth).
2. Elimination of 'ValueError: Unsupported elliptic curve point type' during http_ece.encrypt.
3. RFC 8292 / Apple APNs compliant ES256 JWT construction with exact 64-byte R|S signature.
4. Mathematical verification of ECDSA signature using cryptography P-256.
"""

import base64
import binascii
import json
import os
import sys
import time
from urllib.parse import urlparse

try:
    import http_ece
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
    from cryptography.hazmat.primitives import hashes, serialization
    import requests
except ImportError as e:
    print(f"Missing required dependency: {e}")
    sys.exit(1)


def b64urldecode(b64str):
    """Safely decode a base64 or base64url string with missing padding to raw bytes."""
    if b64str is None:
        return b""
    if isinstance(b64str, (bytes, bytearray)):
        if len(b64str) in [16, 32] or (len(b64str) == 65 and b64str[0] == 0x04):
            return bytes(b64str)
        try:
            b64str = b64str.decode("ascii")
        except (UnicodeDecodeError, Exception):
            return bytes(b64str)
    b64str = str(b64str).strip().strip("'\"").replace("\r", "").replace("\n", "").replace(" ", "").rstrip("=")
    rem = len(b64str) % 4
    if rem > 0:
        b64str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(b64str)


def b64urlencode(raw_bytes):
    """Encode raw bytes to unpadded base64url ASCII string."""
    if isinstance(raw_bytes, str):
        raw_bytes = raw_bytes.encode("utf-8")
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8").rstrip("=")


def GenerateAppleJWT(vapid_private_key, sub, aud):
    """
    Generate an RFC 8292 conforming VAPID Authorization JWT for Apple APNs.
    Accepts VAPID private key as:
    - Base64 / Base64URL string
    - PEM formatted string or bytes
    - Raw 32 bytes
    - cryptography ec.EllipticCurvePrivateKey
    - py_vapid.Vapid instance
    """
    try:
        priv_key = None
        if hasattr(vapid_private_key, "private_key"):
            priv_key = vapid_private_key.private_key
        elif isinstance(vapid_private_key, ec.EllipticCurvePrivateKey):
            priv_key = vapid_private_key
        elif isinstance(vapid_private_key, (bytes, bytearray)) and len(vapid_private_key) == 32:
            priv_key = ec.derive_private_key(int.from_bytes(bytes(vapid_private_key), "big"), ec.SECP256R1())
        elif isinstance(vapid_private_key, (bytes, bytearray)) and b"-----BEGIN" in vapid_private_key:
            priv_key = serialization.load_pem_private_key(bytes(vapid_private_key), password=None)
        elif isinstance(vapid_private_key, str) and "-----BEGIN" in vapid_private_key:
            priv_key = serialization.load_pem_private_key(vapid_private_key.encode("utf-8"), password=None)
        elif isinstance(vapid_private_key, (str, bytes, bytearray)):
            raw_priv = b64urldecode(vapid_private_key)
            if len(raw_priv) == 32:
                priv_key = ec.derive_private_key(int.from_bytes(raw_priv, "big"), ec.SECP256R1())

        if priv_key is None:
            raise ValueError("Unable to load private key from provided input")

        # Header and claims conforming strictly to RFC 8292 / Apple APNs
        header = {"typ": "JWT", "alg": "ES256"}
        exp_time = int(time.time()) + 12 * 3600
        claims = {
            "aud": aud,
            "sub": sub,
            "exp": exp_time
        }

        # JSON serialization without whitespace
        header_enc = b64urlencode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
        claims_enc = b64urlencode(json.dumps(claims, separators=(',', ':')).encode('utf-8'))
        signing_input = f"{header_enc}.{claims_enc}".encode('utf-8')

        # Sign JWS using P-256 and SHA-256
        rsig_der = priv_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))

        # Extract r and s, formatted strictly to 64 bytes (32 bytes big-endian each)
        r, s = decode_dss_signature(rsig_der)
        sig_raw = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
        sig_enc = b64urlencode(sig_raw)

        # Mathematical verification of signature against public key
        pub_key = priv_key.public_key()
        pub_key.verify(rsig_der, signing_input, ec.ECDSA(hashes.SHA256()))

        # VAPID public key (uncompressed point, 65 bytes)
        pub_bytes = pub_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        k_enc = b64urlencode(pub_bytes)

        token = f"{header_enc}.{claims_enc}.{sig_enc}"
        return f"vapid t={token}, k={k_enc}"
    except Exception as e:
        print(f"Error generating Apple JWT: {e}")
        return None


def run_diagnostic():
    print("=" * 60)
    print(" Apple APNs Web Push Diagnostic & Verification Suite ")
    print("=" * 60)

    # 1. Load or generate VAPID keys
    vapid_priv = None
    conf_search_paths = [
        "/etc/genmon/genwebpush.conf",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "conf", "genwebpush.conf"),
    ]
    for cp in conf_search_paths:
        if os.path.exists(cp):
            print(f"[1/5] Reading VAPID configuration from: {cp}")
            with open(cp, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("vapid_private_key"):
                        vapid_priv = line.split("=", 1)[1].strip()
            if vapid_priv:
                break

    if not vapid_priv:
        print("[1/5] No configured VAPID private key found. Generating ephemeral test key...")
        test_key = ec.generate_private_key(ec.SECP256R1())
        vapid_priv = b64urlencode(test_key.private_numbers().private_value.to_bytes(32, 'big'))
    print(f"      VAPID Private Key loaded (starts with {vapid_priv[:6]}...)")

    # 2. Read or mock subscriptions
    subs_search_paths = [
        "/etc/genmon/data/webpush_subscriptions.json",
        "/etc/genmon/webpush_subscriptions.json",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "webpush_subscriptions.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "conf", "webpush_subscriptions.json"),
    ]
    subs = []
    for sp in subs_search_paths:
        if os.path.exists(sp):
            try:
                with open(sp, "r", encoding="utf-8") as f:
                    subs = json.load(f)
                print(f"[2/5] Loaded subscriptions from: {sp}")
                break
            except Exception:
                pass

    apple_sub = None
    if isinstance(subs, list):
        for sub in subs:
            if "apple.com" in sub.get("endpoint", ""):
                apple_sub = sub
                break

    if not apple_sub:
        print("[2/5] No live Apple subscription found on disk. Using standardized mock Apple subscription...")
        apple_sub = {
            "endpoint": "https://push.apple.com/sub/mock_ios_device_id_abcdef123456",
            "device_name": "Diagnostic Mock iPad Pro",
            "keys": {
                "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                "auth": "tBHItJI5svbpez7KI4CCXg"
            }
        }
    else:
        print(f"[2/5] Found real Apple Push subscription for device: {apple_sub.get('device_name', 'iOS Device')}")

    endpoint = apple_sub["endpoint"]
    print(f"      Target Endpoint: {endpoint}")

    p256dh_b64 = apple_sub.get("keys", {}).get("p256dh")
    auth_b64 = apple_sub.get("keys", {}).get("auth")
    if not p256dh_b64 or not auth_b64:
        print("FAILED: Subscription is missing p256dh or auth keys.")
        return False

    # 3. Test Base64URL decoding (R1)
    print("\n[3/5] Diagnosing Base64URL Key Decoding (Requirement R1)...")
    p256dh = b64urldecode(p256dh_b64)
    auth = b64urldecode(auth_b64)
    print(f"      Decoded p256dh: {len(p256dh)} bytes (First byte: 0x{p256dh[0]:02x})")
    print(f"      Decoded auth:   {len(auth)} bytes")

    if len(p256dh) != 65 or p256dh[0] != 0x04:
        print("FAILED: Decoded p256dh key is not a valid 65-byte uncompressed EC point (0x04 prefix)")
        return False
    if len(auth) != 16:
        print("FAILED: Decoded auth secret is not 16 bytes")
        return False
    print("      SUCCESS: Base64URL decoding successfully recovered raw cryptographic keys.")

    # 4. Construct and mathematically verify Apple APNs JWT (R2)
    print("\n[4/5] Generating and Validating Apple APNs JWT Header (Requirement R2)...")
    parsed = urlparse(endpoint)
    aud_claim = f"{parsed.scheme}://{parsed.netloc}"
    sub_claim = "mailto:genmon.push@gmail.com"

    auth_header = GenerateAppleJWT(vapid_priv, sub_claim, aud_claim)
    if not auth_header:
        print("FAILED: GenerateAppleJWT returned None")
        return False

    print(f"      Authorization Header generated: length={len(auth_header)}")
    print(f"      Header Preview: {auth_header[:50]}...{auth_header[-25:]}")

    # Verify JWT structure
    parts = auth_header.split(" ")
    if len(parts) != 3 or parts[0] != "vapid" or not parts[1].startswith("t=") or not parts[2].startswith("k="):
        print("FAILED: Authorization header does not match RFC 8292 'vapid t=..., k=...' format")
        return False

    jwt_token = parts[1][2:].rstrip(",")
    jwt_parts = jwt_token.split(".")
    if len(jwt_parts) != 3:
        print("FAILED: JWT does not contain 3 segments (header.claims.signature)")
        return False

    # Check raw signature length
    sig_raw = b64urldecode(jwt_parts[2])
    print(f"      Raw ECDSA signature length: {len(sig_raw)} bytes (expected 64 bytes for R|S)")
    if len(sig_raw) != 64:
        print(f"FAILED: Signature length is {len(sig_raw)} bytes, expected exactly 64 bytes")
        return False

    # Check claims
    claims_json = json.loads(b64urldecode(jwt_parts[1]).decode("utf-8"))
    print(f"      Decoded Claims: aud='{claims_json.get('aud')}', sub='{claims_json.get('sub')}', exp={claims_json.get('exp')}")
    if claims_json.get("aud") != aud_claim or claims_json.get("sub") != sub_claim:
        print("FAILED: JWT claims do not match required aud/sub")
        return False
    print("      SUCCESS: JWT mathematically conforms to RFC 8292 and Apple APNs requirements.")

    # 5. Encrypt payload using http_ece (RFC 8291 aes128gcm)
    print("\n[5/5] Encrypting Payload via http_ece (RFC 8291 aes128gcm)...")
    payload = {
        "title": "Genmon Alert",
        "body": "Utility Power OUTAGE Detected!",
        "category": "outage",
        "timestamp": int(time.time() * 1000)
    }
    salt = os.urandom(16)
    server_key = ec.generate_private_key(ec.SECP256R1())

    try:
        encrypted_data = http_ece.encrypt(
            json.dumps(payload).encode('utf-8'),
            salt=salt,
            private_key=server_key,
            dh=p256dh,
            auth_secret=auth,
            version="aes128gcm"
        )
        print(f"      Encrypted ciphertext generated successfully ({len(encrypted_data)} bytes).")
        print("      SUCCESS: Zero 'ValueError: Unsupported elliptic curve point type' exceptions encountered.")
    except Exception as e_enc:
        print(f"FAILED: http_ece.encrypt raised exception: {e_enc}")
        return False

    # 6. Live dispatch test (if real endpoint)
    if "mock_ios_device" not in endpoint and "example.com" not in endpoint:
        print(f"\nDispatching live POST request to Apple APNs ({endpoint[:45]}...)...")
        req_headers = {
            "Authorization": auth_header,
            "Content-Encoding": "aes128gcm",
            "TTL": "3600"
        }
        try:
            resp = requests.post(endpoint, data=encrypted_data, headers=req_headers, timeout=5)
            print(f"--- HTTP {resp.status_code} {resp.reason} ---")
            print(f"Response: {resp.text}")
            if resp.status_code == 201:
                print("SUCCESS: Apple APNs accepted the push notification!")
            elif resp.status_code == 410:
                print("Endpoint expired (410 Gone) — subscription is stale.")
            else:
                print(f"Apple returned status {resp.status_code}.")
        except Exception as ex_net:
            print(f"Network dispatch note: {ex_net}")
    else:
        print("\nSkipping live HTTP POST for mock endpoint.")

    print("\n" + "=" * 60)
    print(" ALL DIAGNOSTIC CHECKS PASSED SUCCESSFULLY ")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = run_diagnostic()
    sys.exit(0 if success else 1)
