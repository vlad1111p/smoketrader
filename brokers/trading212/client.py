import os

import httpx
from dotenv import load_dotenv, find_dotenv


class Trading212Client:

    def __init__(self):
        load_dotenv(find_dotenv())

        self.base_url = (os.getenv("T212_BASE_URL") or "").strip()
        self.api_key = (os.getenv("T212_API_KEY") or "").strip()
        self.api_secret = (os.getenv("T212_API_SECRET") or "").strip()

        if not self.base_url:
            raise RuntimeError("Missing T212_BASE_URL in .env")

        self._client = httpx.Client(
            base_url=self.base_url,
            auth=(self.api_key, self.api_secret),
            timeout=15.0,
            headers={"Accept": "application/json"},
        )

    def get(self, path: str, **kwargs):
        r = self._client.get(path, **kwargs)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, **kwargs):
        r = self._client.post(path, **kwargs)
        r.raise_for_status()
        return r.json()

    def delete(self, path: str, **kwargs):
        r = self._client.delete(path, **kwargs)
        r.raise_for_status()
        return r.json()

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
