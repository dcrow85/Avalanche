"""Execute Python code on a RunPod pod via the Jupyter kernel websocket.

Credentials are intentionally read from the environment so this helper can stay
tracked without leaking a live pod ID or password into Git history.

Required env vars:
    RPOD_EXEC_POD_ID
    RPOD_EXEC_PASSWORD
"""
import json
import os
import sys
import time
import uuid

import requests
import websocket


POD_ID = os.environ.get("RPOD_EXEC_POD_ID", "")
PASSWORD = os.environ.get("RPOD_EXEC_PASSWORD", "")
BASE = f"https://{POD_ID}-8888.proxy.runpod.net" if POD_ID else ""


def _require_config():
    if POD_ID and PASSWORD:
        return
    raise SystemExit(
        "Missing RunPod credentials. Set RPOD_EXEC_POD_ID and "
        "RPOD_EXEC_PASSWORD before running rpod_exec.py."
    )

def execute(code, timeout=600):
    _require_config()
    s = requests.Session()
    s.get(f"{BASE}/login")
    xsrf = s.cookies.get("_xsrf", "")
    s.post(f"{BASE}/login", data={"password": PASSWORD, "_xsrf": xsrf},
           headers={"X-XSRFToken": xsrf}, allow_redirects=False)
    cookies = "; ".join([f"{c.name}={c.value}" for c in s.cookies])

    # Get or create kernel
    r = s.get(f"{BASE}/api/kernels")
    kernels = r.json()
    if kernels:
        kid = kernels[0]["id"]
    else:
        r = s.post(f"{BASE}/api/kernels", json={"name": "python3"},
                   headers={"X-XSRFToken": xsrf})
        kid = r.json()["id"]

    ws = websocket.create_connection(
        f"wss://{POD_ID}-8888.proxy.runpod.net/api/kernels/{kid}/channels",
        cookie=cookies, timeout=15
    )

    msg = {
        "header": {"msg_id": str(uuid.uuid4()), "msg_type": "execute_request",
                   "username": "", "session": str(uuid.uuid4()), "version": "5.3"},
        "parent_header": {}, "metadata": {},
        "content": {"code": code, "silent": False, "store_history": False,
                    "user_expressions": {}, "allow_stdin": False}
    }
    ws.send(json.dumps(msg))

    output = []
    start = time.time()
    while time.time() - start < timeout:
        try:
            ws.settimeout(10)
            resp = json.loads(ws.recv())
            if resp.get("msg_type") == "stream":
                text = resp["content"]["text"]
                output.append(text)
                print(text, end="", flush=True)
            elif resp.get("msg_type") == "execute_reply":
                break
            elif resp.get("msg_type") == "error":
                tb = "\n".join(resp["content"]["traceback"])
                output.append(tb)
                print(tb)
                break
        except websocket.WebSocketTimeoutException:
            continue
        except Exception as e:
            print(f"Error: {e}")
            break

    ws.close()
    return "".join(output)

def shell(cmd, timeout=600):
    """Execute a shell command via Python subprocess."""
    code = f'''import subprocess
r = subprocess.run({repr(cmd)}, shell=True, capture_output=True, text=True, timeout={timeout})
if r.stdout: print(r.stdout, end="")
if r.stderr: print("STDERR:", r.stderr, end="")
print("EXIT:", r.returncode)
'''
    return execute(code, timeout)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        shell(cmd)
    else:
        print("Usage: rpod_exec.py <shell command>")
