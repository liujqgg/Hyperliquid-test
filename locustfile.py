"""
Locust load test for Hyperliquid Testnet API.
Usage: locust -f locustfile.py --host=https://api.hyperliquid-testnet.xyz
Optional: set HYPERLIQUID_WALLET_ADDRESS and HYPERLIQUID_PRIVATE_KEY for signed tasks.
"""
import os
from locust import HttpUser, task, between

# Host is set via --host; paths are /info and /exchange


class HyperliquidInfoUser(HttpUser):
    """Read-only info endpoint load."""
    wait_time = between(0.5, 1.5)

    @task(3)
    def all_mids(self):
        self.client.post("/info", json={"type": "allMids"}, name="info/allMids")

    @task(2)
    def meta(self):
        self.client.post("/info", json={"type": "metaAndAssetCtxs"}, name="info/meta")

    @task(1)
    def clearinghouse_state(self):
        # Requires valid user; may get empty or error if no user in payload
        addr = os.environ.get("HYPERLIQUID_WALLET_ADDRESS", "0xa4022bdfa1e6d546f26905111fc62b0b8887d482")
        self.client.post(
            "/info",
            json={"type": "clearinghouseState", "user": addr},
            name="info/clearinghouseState",
        )


class HyperliquidMixedUser(HttpUser):
    """Mix of info (no auth) and optional exchange (would need signing in real run)."""
    wait_time = between(1, 3)

    @task(5)
    def info_all_mids(self):
        self.client.post("/info", json={"type": "allMids"}, name="info/allMids")

    @task(2)
    def info_meta(self):
        self.client.post("/info", json={"type": "metaAndAssetCtxs"}, name="info/meta")
