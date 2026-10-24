"""GET JSON de solo lectura (DefiLlama y Blockscout) con reintentos y límite de ritmo."""

import json
import random
import threading
import time
import urllib.error
import urllib.request


class WebError(Exception):
    pass


def http_get(url, timeout):
    req = urllib.request.Request(url, headers={"accept": "application/json",
                                               "user-agent": "nqc-census-dinero/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise WebError(f"HTTP {e.code} en {url}") from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        raise WebError(f"transporte: {e} en {url}") from None


class WebClient:
    def __init__(self, *, rps=4, timeout=30, retries=4, getter=None, sleep=time.sleep):
        self.interval = 1.0 / rps if rps else 0.0
        self.next_at = 0.0
        self.lock = threading.Lock()
        self.timeout = timeout
        self.retries = retries
        self.getter = getter or http_get
        self.sleep = sleep
        self.calls = 0
        self.errors = 0

    def get(self, url):
        last = None
        for attempt in range(self.retries):
            with self.lock:
                now = time.monotonic()
                at = max(now, self.next_at)
                self.next_at = at + self.interval
                self.calls += 1
            if at > now:
                self.sleep(at - now)
            try:
                return self.getter(url, self.timeout)
            except WebError as e:
                last = e
                with self.lock:
                    self.errors += 1
                if "HTTP 404" in str(e):
                    break
                self.sleep(min(15.0, 1.0 * 2 ** attempt) + random.random())
        raise last or WebError(url)
