import sys, json, os, time, base64
from urllib.parse import urlparse
import requests
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
import http_ece

def b64urlencode(raw_bytes):
    if isinstance(raw_bytes, str): raw_bytes = raw_bytes.encode("utf-8")
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8").rstrip("=")

def b64urldecode(b64_str):
    if isinstance(b64_str, str): b64_str = b64_str.encode('utf-8')
    b64_str += b'=' * (-len(b64_str) % 4)
    return base64.urlsafe_b64decode(b64_str)

def main():
    print("=== Apple APNs Brute Force Diagnostic ===")
    conf_path = "/etc/genmon/genwebpush.conf"
    if not os.path.exists(conf_path):
        print(f"ERROR: {conf_path} not found.")
        return

    with open(conf_path, "r") as f:
        conf = f.read()
    
    pub_key_b64, priv_key_b64 = "", ""
    for line in conf.split("\n"):
        if "vapid_public_key" in line: pub_key_b64 = line.split("=")[1].strip()
        if "vapid_private_key" in line: priv_key_b64 = line.split("=")[1].strip()

    if not priv_key_b64:
        print("ERROR: No private key found.")
        return

    sub_path = "/etc/genmon/data/webpush_subscriptions.json"
    if not os.path.exists(sub_path):
        print(f"ERROR: {sub_path} not found.")
        return

    with open(sub_path, "r") as f:
        subs = json.load(f)

    apple_sub = None
    for sub in subs:
        if "apple.com" in sub.get("endpoint", ""):
            apple_sub = sub
            break

    if not apple_sub:
        print("ERROR: No live Apple subscription found. Please toggle 'Enable Web Push' on your iPad first.")
        return

    print(f"Found Apple subscription: {apple_sub['endpoint'][:50]}...")
    endpoint = apple_sub['endpoint']
    parsed_endpoint = urlparse(endpoint)
    aud = f"{parsed_endpoint.scheme}://{parsed_endpoint.netloc}"
    sub_claim = "mailto:mwoswald@gmail.com"

    # Derive private key
    raw_priv = b64urldecode(priv_key_b64)
    priv_key = ec.derive_private_key(int.from_bytes(raw_priv, "big"), ec.SECP256R1())

    # Build JWT
    header = {"typ": "JWT", "alg": "ES256"}
    claims = {"aud": aud, "sub": sub_claim, "exp": int(time.time()) + 12 * 3600}
    
    header_enc = b64urlencode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    claims_enc = b64urlencode(json.dumps(claims, separators=(',', ':')).encode('utf-8'))
    token = f"{header_enc}.{claims_enc}"
    
    rsig = priv_key.sign(token.encode('utf-8'), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(rsig)
    sig_raw = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
    sig_enc = b64urlencode(sig_raw)
    
    pub_bytes = priv_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    k_enc = b64urlencode(pub_bytes)

    # Build Payload
    sub_keys = apple_sub.get("keys", {})
    p256dh = b64urldecode(sub_keys.get("p256dh"))
    auth = b64urldecode(sub_keys.get("auth"))
    
    salt = os.urandom(16)
    server_key = ec.generate_private_key(ec.SECP256R1())
    payload_dict = {"title": "Diagnostic", "message": "Brute force test"}
    
    encrypted_data = http_ece.encrypt(
        json.dumps(payload_dict).encode('utf-8'),
        salt=salt,
        private_key=server_key,
        dh=p256dh,
        auth_secret=auth,
        version="aes128gcm",
    )

    formats = [
        {
            "name": "Standard VAPID (with space)",
            "headers": {
                "Authorization": f"vapid t={token}.{sig_enc}, k={k_enc}",
                "Content-Encoding": "aes128gcm",
                "TTL": "3600"
            }
        },
        {
            "name": "Standard VAPID (no space)",
            "headers": {
                "Authorization": f"vapid t={token}.{sig_enc},k={k_enc}",
                "Content-Encoding": "aes128gcm",
                "TTL": "3600"
            }
        },
        {
            "name": "Legacy WebPush",
            "headers": {
                "Authorization": f"WebPush {token}.{sig_enc}",
                "Crypto-Key": f"p256ecdsa={k_enc}",
                "Content-Encoding": "aes128gcm",
                "TTL": "3600"
            }
        },
        {
            "name": "Bearer Token",
            "headers": {
                "Authorization": f"bearer {token}.{sig_enc}",
                "Content-Encoding": "aes128gcm",
                "TTL": "3600"
            }
        }
    ]

    for fmt in formats:
        print(f"\n--- Testing Format: {fmt['name']} ---")
        try:
            resp = requests.post(endpoint, data=encrypted_data, headers=fmt['headers'], timeout=5)
            print(f"Status Code: {resp.status_code}")
            print(f"Response: {resp.text}")
            if resp.status_code == 201:
                print(">>> SUCCESS! THIS FORMAT WORKS! <<<")
                break
        except Exception as e:
            print(f"Request failed: {e}")

if __name__ == "__main__":
    main()
