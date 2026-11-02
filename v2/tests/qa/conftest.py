"""QA fixtures: a throwaway uvicorn server on a random port with an empty data dir (no new dependencies:
plain urllib, no httpx/TestClient)."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

V2 = Path(__file__).resolve().parents[2]


class Client:
    def __init__(self, base):
        self.base = base

    def req(self, method, path, form=None, body=None, raw=False):
        data = None
        headers = {}
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
        if body is not None:
            data, headers = json.dumps(body).encode(), {"Content-Type": "application/json"}

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        op = urllib.request.build_opener(NoRedirect)
        r = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            resp = op.open(r, timeout=60)
        except urllib.error.HTTPError as e:
            resp = e
        content = resp.read()
        status = resp.status if hasattr(resp, "status") else resp.code
        return status, (content if raw else content.decode("utf-8", "replace")), {k.title(): v for k, v in resp.headers.items()}

    def get(self, path, **k):
        return self.req("GET", path, **k)

    def post(self, path, form=None, **k):
        return self.req("POST", path, form=form or {}, **k)

    def new_factory(self, name="QA"):
        st, _, h = self.post("/api/factories", {"name": name})
        assert st == 303, st
        return int(h["Location"].rsplit("/", 1)[1])

    def export(self, fid):
        st, body, _ = self.get(f"/api/factory/{fid}/export.json")
        assert st == 200
        return json.loads(body)


def _start(d):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    env = dict(os.environ, SFP_DATA_DIR=str(d))
    env.pop("SFP_1X_DB", None)
    log = open(d / "server.log", "w")
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=V2, env=env,
                         stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/health", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        p.kill()
        raise RuntimeError("server did not start")
    return p, Client(base)


def _stop(p, d):
    p.terminate()
    p.wait(10)
    txt = (d / "server.log").read_text()
    assert "Traceback" not in txt.replace("HTTPException", ""), txt[-3000:]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    d = tmp_path_factory.mktemp("qa-data")
    p, c = _start(d)
    yield c
    _stop(p, d)


@pytest.fixture()
def fresh_server(tmp_path):
    """A brand-new empty data directory (no world, no factories)."""
    p, c = _start(tmp_path)
    yield c
    _stop(p, tmp_path)
