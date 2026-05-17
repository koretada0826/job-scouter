"""3サイトの取得モジュール集約点。"""
from .lancers_fetcher import fetch_lancers
from .coconala_fetcher import fetch_coconala
from .cw_fetcher import fetch_crowdworks

__all__ = ["fetch_lancers", "fetch_coconala", "fetch_crowdworks"]
