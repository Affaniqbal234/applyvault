import math
import time


class AuthRateLimiter:
    """Bound authentication work in one process using a fixed time window."""

    def __init__(self, per_client=20, total=100, window=60, clock=time.monotonic):
        self.per_client = per_client
        self.total = total
        self.window = window
        self.clock = clock
        self.reset()

    def reset(self):
        self.started = self.clock()
        self.clients = {}
        self.count = 0

    def retry_after(self, client):
        # Called on the event loop without an await: check and increment together.
        now = self.clock()
        if now - self.started >= self.window:
            self.reset()
        if self.count >= self.total or self.clients.get(client, 0) >= self.per_client:
            return max(1, math.ceil(self.window - (now - self.started)))
        self.clients[client] = self.clients.get(client, 0) + 1
        self.count += 1
        return 0
