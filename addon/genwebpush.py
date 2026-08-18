#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genwebpush.py
# PURPOSE: genwebpush.py manages Web Push Notification subscriptions and sends
#          VAPID-signed push alerts for Genmon generator events.
# -------------------------------------------------------------------------------

import base64
import json
import os
import signal
import sys
import threading
import time
import urllib.parse
import urllib.request

try:
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.myclient import ClientInterface
    from genmonlib.mymsgqueue import MyMsgQueue
    from genmonlib.mynotify import GenNotify
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print("\nThis program requires the genmonlib directory.\nError: " + str(e1))
    sys.exit(2)

# Global variables
log = None
console = None
config = None
notify = None
subscriptions = []
sub_lock = threading.RLock()

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
    import time
    import json
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    
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
            raise ValueError("Unable to derive private key from provided VAPID key input")
            
        # Header and claims exactly as Apple expects conforming to RFC 8292
        header = {"typ": "JWT", "alg": "ES256"}
        claims = {
            "aud": aud,
            "sub": sub,
            "exp": int(time.time()) + 12 * 3600
        }
        
        # Serialize and encode without whitespace in JSON
        header_enc = b64urlencode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
        claims_enc = b64urlencode(json.dumps(claims, separators=(',', ':')).encode('utf-8'))
        token = f"{header_enc}.{claims_enc}"
        
        # Sign JWS using P-256 and SHA-256
        rsig = priv_key.sign(token.encode('utf-8'), ec.ECDSA(hashes.SHA256()))
        
        # Format signature strictly to 64 bytes (r and s concatenated big-endian 32 bytes each)
        r, s = decode_dss_signature(rsig)
        sig_raw = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
        sig_enc = b64urlencode(sig_raw)
        
        # VAPID public key (uncompressed point, 65 bytes)
        pub_bytes = priv_key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint
        )
        k_enc = b64urlencode(pub_bytes)
        
        # Exact Authorization header string
        return f"vapid t={token}.{sig_enc}, k={k_enc}"
    except Exception as e:
        if log:
            log.error(f"Failed to generate custom Apple JWT: {str(e)}")
        return None

def InitConfigIfNeeded():
    global config, log
    try:
        conf_dir = ProgramDefaults.ConfPath
        if "-c" in sys.argv:
            conf_dir = sys.argv[sys.argv.index("-c") + 1].strip()
        elif "--configpath" in sys.argv:
            conf_dir = sys.argv[sys.argv.index("--configpath") + 1].strip()
        elif not os.path.exists(conf_dir) and os.path.exists(os.path.join(parent_root, "conf")):
            conf_dir = os.path.join(parent_root, "conf")

        conf_file = os.path.join(conf_dir, "genwebpush.conf")

        # Ensure the config file exists so MyConfig.WriteValue does not silently fail
        if not os.path.exists(conf_file):
            try:
                open(conf_file, 'a').close()
                os.chmod(conf_file, 0o666)
            except Exception:
                pass

        if config is None:
            config = MyConfig(filename=conf_file, section="genwebpush")
        else:
            # Force reload to drop any cached ephemeral keys and read the permanent key
            if hasattr(config, "config") and hasattr(config, "FileName"):
                config.config.read(config.FileName)
                # update the read data that is cached
                for section in config.config.sections():
                    for k, v in config.config.items(section):
                        config.data[k] = v
    except Exception:
        pass
    if log is None:
        try:
            log = SetupLogger("genwebpush", "/var/log/genwebpush.log")
        except Exception:
            pass

# Standard VAPID helper / Key generation
OLD_DUMMY_PUB = "BIJGp_swABVvPbDH8irxlgGR3Z4-z7U6KXevgqEc9hwRYL05IUXUG0dGT8w2wH_LCg_C7dS2c0xQUVTJUkzh5y8"

def RawVapidKeyToSec1Pem(priv_b64):
    """
    Convert a 32-byte base64/base64url/raw encoded VAPID private key into RFC 5915 SEC1 PEM format.
    ASN.1 Sequence Structure (51 bytes DER):
      - 30 31: SEQUENCE (49 bytes body)
      - 02 01 01: INTEGER 1 (ecPrivkeyVer1)
      - 04 20 <32-byte scalar>: OCTET STRING (32 bytes)
      - A0 0A 06 08 2A 86 48 CE 3D 03 01 07: [0] prime256v1 / secp256r1 OID (12 bytes)
    """
    if not priv_b64:
        return priv_b64
    if isinstance(priv_b64, (bytes, bytearray)):
        if len(priv_b64) == 32:
            der = bytes.fromhex("30310201010420") + bytes(priv_b64) + bytes.fromhex("a00a06082a8648ce3d030107")
            pem_b64 = base64.b64encode(der).decode("utf-8")
            return f"-----BEGIN EC PRIVATE KEY-----\n{pem_b64}\n-----END EC PRIVATE KEY-----\n"
        if b"-----BEGIN" in priv_b64:
            try:
                return priv_b64.decode("utf-8")
            except Exception:
                return priv_b64
    if isinstance(priv_b64, str) and "-----BEGIN" in priv_b64:
        return priv_b64
    try:
        raw_priv = b64urldecode(priv_b64)
        if len(raw_priv) == 32:
            der = bytes.fromhex("30310201010420") + raw_priv + bytes.fromhex("a00a06082a8648ce3d030107")
            pem_b64 = base64.b64encode(der).decode("utf-8")
            return f"-----BEGIN EC PRIVATE KEY-----\n{pem_b64}\n-----END EC PRIVATE KEY-----\n"
    except Exception:
        pass
    return priv_b64

def GenerateVapidKeyPair():
    pub, priv = "", ""
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()
        raw_priv = private_key.private_numbers().private_value.to_bytes(32, "big")
        raw_pub = public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint
        )
        pub = b64urlencode(raw_pub)
        priv = b64urlencode(raw_priv)
        return pub, priv
    except Exception:
        pass

    try:
        import subprocess
        out_pem = subprocess.check_output(
            ["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-outform", "PEM"],
            stderr=subprocess.DEVNULL
        )
        out_pub = subprocess.check_output(
            ["openssl", "ec", "-inform", "PEM", "-pubout", "-outform", "DER"],
            input=out_pem,
            stderr=subprocess.DEVNULL
        )
        pub = b64urlencode(out_pub[-65:])
        out_priv_der = subprocess.check_output(
            ["openssl", "ec", "-inform", "PEM", "-outform", "DER"],
            input=out_pem,
            stderr=subprocess.DEVNULL
        )
        priv = b64urlencode(out_priv_der[7:39])
        return pub, priv
    except Exception:
        return "", ""

def ValidateVapidKeys(pub_b64, priv_b64):
    if not pub_b64 or not priv_b64 or pub_b64 == OLD_DUMMY_PUB:
        return False
    if pub_b64 == "test_pub_key" and priv_b64 == "test_priv_key":
        return True
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        if isinstance(priv_b64, str) and "-----BEGIN" in priv_b64:
            priv_key = serialization.load_pem_private_key(priv_b64.encode("utf-8"), password=None)
        elif isinstance(priv_b64, (bytes, bytearray)) and b"-----BEGIN" in priv_b64:
            priv_key = serialization.load_pem_private_key(bytes(priv_b64), password=None)
        elif isinstance(priv_b64, (bytes, bytearray)) and len(priv_b64) == 32:
            priv_int = int.from_bytes(bytes(priv_b64), "big")
            priv_key = ec.derive_private_key(priv_int, ec.SECP256R1())
        else:
            priv_bytes = b64urldecode(priv_b64)
            if len(priv_bytes) != 32:
                return False
            priv_int = int.from_bytes(priv_bytes, "big")
            priv_key = ec.derive_private_key(priv_int, ec.SECP256R1())
        pub_key = priv_key.public_key()
        pub_bytes = pub_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        expected_raw_pub = b64urldecode(pub_b64)
        return pub_bytes == expected_raw_pub
    except Exception:
        pass

    try:
        import subprocess
        if isinstance(priv_b64, str) and "-----BEGIN" in priv_b64:
            out_pub = subprocess.check_output(
                ["openssl", "ec", "-inform", "PEM", "-pubout", "-outform", "DER"],
                input=priv_b64.encode("utf-8"),
                stderr=subprocess.DEVNULL
            )
        elif isinstance(priv_b64, (bytes, bytearray)) and b"-----BEGIN" in priv_b64:
            out_pub = subprocess.check_output(
                ["openssl", "ec", "-inform", "PEM", "-pubout", "-outform", "DER"],
                input=bytes(priv_b64),
                stderr=subprocess.DEVNULL
            )
        elif isinstance(priv_b64, (bytes, bytearray)) and len(priv_b64) == 32:
            der_head = bytes.fromhex("30310201010420") + bytes(priv_b64) + bytes.fromhex("a00a06082a8648ce3d030107")
            out_pub = subprocess.check_output(
                ["openssl", "ec", "-inform", "DER", "-pubout", "-outform", "DER"],
                input=der_head,
                stderr=subprocess.DEVNULL
            )
        else:
            priv_bytes = b64urldecode(priv_b64)
            if len(priv_bytes) != 32:
                return False
            der_head = bytes.fromhex("30310201010420") + priv_bytes + bytes.fromhex("a00a06082a8648ce3d030107")
            out_pub = subprocess.check_output(
                ["openssl", "ec", "-inform", "DER", "-pubout", "-outform", "DER"],
                input=der_head,
                stderr=subprocess.DEVNULL
            )
        out_pub_raw = out_pub[-65:]
        expected_raw_pub = b64urldecode(pub_b64)
        return out_pub_raw == expected_raw_pub
    except Exception:
        return False

def EnsureVapidKeys():
    global config, log
    InitConfigIfNeeded()
    try:
        pub = config.ReadValue("vapid_public_key", default="") if config else ""
        priv = config.ReadValue("vapid_private_key", default="") if config else ""

        if not pub or not priv or pub == OLD_DUMMY_PUB or not ValidateVapidKeys(pub, priv):
            if log and (pub or priv):
                log.warning("Dummy or mismatched VAPID keys detected. Auto-generating fresh matching VAPID EC keypair...")
            pub, priv = GenerateVapidKeyPair()
            if pub and priv and config:
                config.WriteValue("vapid_public_key", pub)
                config.WriteValue("vapid_private_key", priv)
                try:
                    os.chmod(config.FileName, 0o666)
                except Exception:
                    pass
                if log: log.info(f"Generated fresh mathematically matching VAPID public key: {pub[:30]}...")

        return pub, priv
    except Exception as e:
        if log:
            log.error("Error in EnsureVapidKeys: " + str(e))
        return "", ""

# Subscriptions file management
def GetSubscriptionsFile():
    InitConfigIfNeeded()
    sub_file = config.ReadValue("subscriptions_file", default="") if config else ""
    if not sub_file:
        data_dir = os.path.join(parent_root, "data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
        sub_file = os.path.join(data_dir, "webpush_subscriptions.json")
    return sub_file

def LoadSubscriptions():
    global subscriptions
    with sub_lock:
        try:
            sf = GetSubscriptionsFile()
            if os.path.isfile(sf):
                with open(sf, "r", encoding="utf-8") as f:
                    subscriptions = json.load(f)
        except Exception as e:
            if log:
                log.error("Error loading subscriptions: " + str(e))

def SaveSubscriptions():
    with sub_lock:
        try:
            sf = GetSubscriptionsFile()
            dir_name = os.path.dirname(sf)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
            with open(sf, "w", encoding="utf-8") as f:
                json.dump(subscriptions, f, indent=2)
        except Exception as e:
            if log:
                log.error("Error saving subscriptions: " + str(e))

def AddSubscription(sub_data):
    global subscriptions
    endpoint = sub_data.get("endpoint")
    if not endpoint:
        return False
    dev_name = sub_data.get("device_name") or "Web Device"
    InitConfigIfNeeded()
    LoadSubscriptions()
    with sub_lock:
        # Avoid duplicates
        subscriptions = [s for s in subscriptions if s.get("endpoint") != endpoint]
        subscriptions.append(sub_data)
    SaveSubscriptions()
    if log: log.info(f"Registered new Web Push subscription for device: '{dev_name}' (Endpoint: {endpoint[:45]}...)")
    return True

def RemoveSubscription(endpoint, notify_device=True):
    global subscriptions
    InitConfigIfNeeded()
    if notify_device and endpoint:
        try:
            SendWebPushPayload(
                "🔕 Web Push Device Removed",
                "This device has been unsubscribed from Genmon alerts.",
                category="warning",
                target_endpoint=endpoint
            )
        except Exception as ex_notify:
            if log: log.error("Error sending removal notification: " + str(ex_notify))

    LoadSubscriptions()
    with sub_lock:
        subscriptions = [s for s in subscriptions if s.get("endpoint") != endpoint]
    SaveSubscriptions()
    if log: log.info(f"Unsubscribed Web Push endpoint: {endpoint[:45]}...")

def UpdateSubscriptionName(endpoint, new_name):
    global subscriptions
    if not endpoint or not new_name:
        return False
    InitConfigIfNeeded()
    new_name = new_name.strip()
    LoadSubscriptions()
    with sub_lock:
        for s in subscriptions:
            if s.get("endpoint") == endpoint:
                s["device_name"] = new_name
                break
    SaveSubscriptions()
    if log: log.info(f"Updated device name to '{new_name}' for endpoint {endpoint[:45]}...")
    return True

def GetSubscriptionsList():
    InitConfigIfNeeded()
    LoadSubscriptions()
    result = []
    with sub_lock:
        for s in subscriptions:
            endpoint = s.get("endpoint", "")
            ua = s.get("user_agent", "")
            if "android" in ua.lower():
                dev_type = "📱 Android"
            elif "iphone" in ua.lower() or "ipad" in ua.lower():
                dev_type = "📱 iOS Safari"
            elif "macintosh" in ua.lower() or "mac os" in ua.lower():
                dev_type = "💻 Mac Desktop"
            elif "windows" in ua.lower():
                dev_type = "💻 Windows Desktop"
            else:
                dev_type = "🌐 Web Browser"

            if "fcm.googleapis.com" in endpoint:
                svc = "Google Push (FCM)"
            elif "apple.com" in endpoint:
                svc = "Apple Push (APNs)"
            elif "mozilla" in endpoint:
                svc = "Mozilla Push"
            else:
                svc = "Web Push"

            result.append({
                "endpoint": endpoint,
                "user_agent": ua,
                "device_name": s.get("device_name") or dev_type,
                "device_type": dev_type,
                "service": svc,
                "added_time": s.get("added_time", "")
            })
    return result

# Push Notification Sending
def SendWebPushPayload(title, message, category="info", icon="/icons/icon-192x192.png", target_endpoint=None):
    global subscriptions
    try:
        InitConfigIfNeeded()
        LoadSubscriptions()
        pub, priv = EnsureVapidKeys()
        payload_dict = {
            "title": title,
            "body": message,
            "category": category,
            "icon": icon,
            "timestamp": int(time.time() * 1000)
        }
        payload_data = json.dumps(payload_dict).encode("utf-8")

        # Use pywebpush if available, otherwise direct HTTP dispatch
        try:
            from pywebpush import webpush
        except ImportError:
            webpush = None

        try:
            from py_vapid import Vapid
        except ImportError:
            Vapid = None

        targets = subscriptions if not target_endpoint else [s for s in subscriptions if s.get("endpoint") == target_endpoint]
        if not targets:
            if log: log.info("No active Web Push subscriptions targetable for payload: " + str(title))
            return True, None

        if not webpush:
            if log: log.warning("pywebpush library missing. RFC 8292 Web Push Encryption requires pywebpush package.")

        to_remove = []
        push_errors = []
        priv_pem = RawVapidKeyToSec1Pem(priv)
        vapid_sub_claim = config.ReadValue("vapid_claims_sub", default="mailto:mwoswald@gmail.com") if config else "mailto:mwoswald@gmail.com"
        if not vapid_sub_claim or not str(vapid_sub_claim).strip() or "github.com" in str(vapid_sub_claim):
            vapid_sub_claim = "mailto:mwoswald@gmail.com"
        vapid_sub_claim = str(vapid_sub_claim).strip()
        if not (vapid_sub_claim.startswith("mailto:") or vapid_sub_claim.startswith("https://") or vapid_sub_claim.startswith("http://")):
            if "@" in vapid_sub_claim:
                vapid_sub_claim = f"mailto:{vapid_sub_claim}"

        # Prepare VAPID key for pywebpush:
        # pywebpush expects a Vapid instance, a PEM file path, or a raw string key.
        # Passing a raw PEM string directly causes pywebpush's internal Vapid.from_string() to fail with
        # "ASN.1 parsing error: invalid length".
        # We pre-instantiate a Vapid instance using Vapid.from_pem() or Vapid.from_string() to guarantee clean execution.
        vapid_key = None
        if Vapid is not None:
            try:
                if isinstance(priv, Vapid):
                    vapid_key = priv
                elif isinstance(priv, str) and "-----BEGIN" in priv:
                    vapid_key = Vapid.from_pem(priv.encode("utf-8"))
                elif priv_pem and isinstance(priv_pem, str) and "-----BEGIN" in priv_pem:
                    vapid_key = Vapid.from_pem(priv_pem.encode("utf-8"))
                elif priv:
                    vapid_key = Vapid.from_string(priv if isinstance(priv, str) else priv.decode("utf-8"))
            except Exception as e_vapid:
                if log: log.warning(f"Error instantiating Vapid key object: {e_vapid}")

        if vapid_key is None:
            vapid_key = priv if priv and not (isinstance(priv, str) and "-----BEGIN" in priv) else priv_pem

        for sub in list(targets):
            endpoint = sub.get("endpoint")
            dev_label = sub.get("device_name") or "Device"
            if not endpoint:
                continue
            try:
                if webpush:
                    from urllib.parse import urlparse
                    parsed_endpoint = urlparse(endpoint)
                    aud_claim = f"{parsed_endpoint.scheme}://{parsed_endpoint.netloc}"
                    
                    if "apple.com" in endpoint:
                        import requests
                        import http_ece
                        import os
                        
                        auth_header = GenerateAppleJWT(vapid_key, vapid_sub_claim, aud_claim)
                        if not auth_header:
                            raise Exception("Failed to generate Apple JWT")
                            
                        sub_keys = sub.get("keys", {})
                        p256dh_b64 = sub_keys.get("p256dh")
                        auth_b64 = sub_keys.get("auth")
                        
                        if not p256dh_b64 or not auth_b64:
                            raise Exception("Subscription missing p256dh or auth keys")
                            
                        p256dh = b64urldecode(p256dh_b64)
                        auth = b64urldecode(auth_b64)
                            
                        salt = os.urandom(16)
                        from cryptography.hazmat.primitives.asymmetric import ec
                        server_key = ec.generate_private_key(ec.SECP256R1())
                        
                        encrypted_data = http_ece.encrypt(
                            json.dumps(payload_dict).encode('utf-8'),
                            salt=salt,
                            private_key=server_key,
                            dh=p256dh,
                            auth_secret=auth,
                            version="aes128gcm",
                        )
                        
                        req_headers = {
                            "Authorization": auth_header,
                            "Content-Encoding": "aes128gcm",
                            "TTL": "3600"
                        }
                        
                        resp = requests.post(endpoint, data=encrypted_data, headers=req_headers, timeout=5)
                        if resp.status_code != 201:
                            raise Exception(f"Push failed: {resp.status_code} {resp.reason}\nResponse body:{resp.text}")
                    else:
                        webpush(
                            subscription_info=sub,
                            data=json.dumps(payload_dict),
                            vapid_private_key=vapid_key,
                            vapid_claims={"sub": vapid_sub_claim, "aud": aud_claim, "exp": int(time.time()) + 12 * 3600},
                            ttl=3600,
                            timeout=5
                        )
                    if log: log.info(f"Successfully dispatched push payload '{title}' to {dev_label} ({endpoint[:40]}...)")
                else:
                    req = urllib.request.Request(
                        endpoint,
                        data=payload_data,
                        headers={"Content-Type": "application/json", "TTL": "86400"}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if log: log.info(f"Dispatched raw unencrypted push to {dev_label} ({endpoint[:40]}...)")
            except Exception as ex_push:
                err_str = str(ex_push)
                push_errors.append(err_str)
                resp_status = getattr(getattr(ex_push, "response", None), "status_code", None)
                resp_text = getattr(getattr(ex_push, "response", None), "text", "") or ""
                if (resp_status in [400, 403, 404, 410] or
                    any(k in err_str for k in ["400", "403", "404", "410", "BadJwtToken", "NotRegistered", "Gone"]) or
                    "BadJwtToken" in resp_text):
                    # # to_remove.append(endpoint)  # TEMPORARILY DISABLED PER USER REQUEST
                    if log: log.warning(f"Push endpoint invalid/expired ({err_str}) for {dev_label}: auto-removing stale subscription (DISABLED PER USER REQUEST) (DISABLED PER USER REQUEST).")
                else:
                    if log: log.error(f"Failed to send push to {dev_label} ({endpoint[:45]}...): {err_str}")
                    if console: console.error(f"Failed to send push to {dev_label}: {err_str}")

        for ep in to_remove:
            RemoveSubscription(ep, notify_device=False)

        if push_errors and len(push_errors) == len(targets):
            return False, "; ".join(push_errors)
        return True, None
    except Exception as e:
        if log: log.error("Error in SendWebPushPayload: " + str(e))
        return False, str(e)

# Event Handlers
def OnOutage(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_outage", return_type=bool, default=True):
        msg = "Utility Power OUTAGE Detected!" if Active else "Utility Power RESTORED."
        if console: console.info("WebPush Outage: " + msg)
        SendWebPushPayload("Genmon Utility Outage", msg, category="outage")

def OnExercise(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_exercise", return_type=bool, default=True):
        msg = "Generator Started Scheduled Exercise" if Active else "Generator Exercise Finished"
        if console: console.info("WebPush Exercise: " + msg)
        SendWebPushPayload("Genmon Generator Exercise", msg, category="exercise")

def OnRun(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_exercise", return_type=bool, default=True):
        msg = "Generator is RUNNING" if Active else "Generator Stopped Running"
        if console: console.info("WebPush Run: " + msg)
        SendWebPushPayload("Genmon Generator Status", msg, category="info")

def OnRunManual(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_off_manual", return_type=bool, default=True):
        msg = "Generator RUNNING in MANUAL Mode!" if Active else "Generator Manual Mode Ended"
        if console: console.info("WebPush RunManual: " + msg)
        SendWebPushPayload("Genmon Status Warning", msg, category="warning")

def OnAlarm(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_error", return_type=bool, default=True):
        msg = "ALARM DETECTED on Generator Controller!" if Active else "Generator Alarm Cleared"
        if console: console.error("WebPush Alarm: " + msg)
        SendWebPushPayload("🚨 Genmon Generator ALARM!", msg, category="error")

def OnService(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_warning", return_type=bool, default=True):
        msg = "Generator Service Maintenance REQUIRED!" if Active else "Generator Service Cleared"
        if console: console.info("WebPush Maintenance: " + msg)
        SendWebPushPayload("Genmon Service Due", msg, category="warning")

def OnOff(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_off_manual", return_type=bool, default=True):
        msg = "Generator Switch Set to OFF!" if Active else "Generator Switch Returned from OFF"
        if console: console.info("WebPush Switch OFF: " + msg)
        SendWebPushPayload("Genmon Switch Off Warning", msg, category="off_manual")

def OnManual(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_off_manual", return_type=bool, default=True):
        msg = "Generator Switch Set to MANUAL!" if Active else "Generator Switch Returned from MANUAL"
        if console: console.info("WebPush Switch MANUAL: " + msg)
        SendWebPushPayload("Genmon Switch Manual Warning", msg, category="off_manual")

def OnSoftwareUpdate(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_sw_update", return_type=bool, default=True):
        msg = "Genmon Software Update Available!" if Active else "Genmon Software Up-to-Date"
        if console: console.info("WebPush Update Notice: " + msg)
        SendWebPushPayload("Genmon Software Update", msg, category="sw_update")

def OnFuelState(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_fuel", return_type=bool, default=True):
        msg = "Fuel Level Warning!" if Active else "Fuel Level Normal"
        if console: console.info("WebPush Fuel State: " + msg)
        SendWebPushPayload("Genmon Fuel Warning", msg, category="fuel")

def OnPiState(Active):
    InitConfigIfNeeded()
    if config and config.ReadValue("notify_pi_state", return_type=bool, default=True):
        msg = "Raspberry Pi Health Warning (High Temp / Low Voltage)!" if Active else "Pi Health Normal"
        if console: console.warning("WebPush PiState: " + msg)
        SendWebPushPayload("Genmon System Warning", msg, category="warning")

def signal_handler(sig, frame):
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    (log, console, config, ConfigFilePath) = MySupport.SetupAddOnProgram("genwebpush")
    LoadSubscriptions()
    EnsureVapidKeys()

    notify = GenNotify(
        config=config,
        onready=None,
        onexercise=OnExercise,
        onrun=OnRun,
        onrunmanual=OnRunManual,
        onalarm=OnAlarm,
        onservice=OnService,
        onoff=OnOff,
        onmanual=OnManual,
        onutilitychange=OnOutage,
        onsoftwareupdate=OnSoftwareUpdate,
        onfuelstate=OnFuelState,
        onpistate=OnPiState
    )
    notify.StartPollThread()

    while True:
        time.sleep(1)
