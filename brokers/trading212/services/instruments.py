from pathlib import Path

from utils.json_file_cache import JsonFileCache


class InstrumentsService:
    CACHE_PATH = Path("data/instruments_cache.json")

    def __init__(self, client):
        self.client = client
        self._cache = None
        self._storage = JsonFileCache(self.CACHE_PATH)

    def _fetch_from_api(self):
        print("Fetching instruments from API...")
        data = self.client.get("/equity/metadata/instruments")
        self._storage.save(data)
        return data

    def get_all(self):
        if self._cache is not None:
            return self._cache

        file_data = self._storage.load()

        if file_data is not None:
            self._cache = file_data
            return self._cache

        self._cache = self._fetch_from_api()
        return self._cache

    def find_by_ticker(self, ticker: str):
        instruments = self.get_all()

        for inst in instruments:
            if inst.get("ticker") == ticker:
                return inst

        instruments = self._fetch_from_api()

        for inst in instruments:
            if inst.get("ticker") == ticker:
                return inst

        return None

    def find_by_short_name(self, short_name: str, partial: bool = False):
        short_name = short_name.lower()
        instruments = self.get_all()

        for inst in instruments:
            name = (inst.get("shortName") or "").lower()

            if partial and short_name in name:
                return inst
            if not partial and short_name == name:
                return inst

        instruments = self._fetch_from_api()

        for inst in instruments:
            name = (inst.get("shortName") or "").lower()

            if partial and short_name in name:
                return inst
            if not partial and short_name == name:
                return inst

        return None
