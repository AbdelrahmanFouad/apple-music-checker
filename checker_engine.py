"""checker_engine.py - High-speed Apple Music storefront exact UPC availability checker."""

import re
import time
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional

DEFAULT_STOREFRONTS = ["eg", "us", "sa", "dz", "ae", "fr", "gb"]

def check_single_upc(
    upc: str,
    target_artist: str = "",
    target_title: str = "",
    storefronts: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Check if a UPC is live on Apple Music via exact iTunes UPC Lookup API ONLY.
    
    Strictly performs exact UPC lookups. No fuzzy title/artist searches,
    no medium or low confidence matches.
    """
    clean_upc = re.sub(r'\D', '', str(upc or '')).strip()
    if not clean_upc:
        return {
            "is_live": False,
            "status": "Invalid UPC",
            "upc": upc,
            "error": "Empty or non-numeric UPC",
            "confidence": "Invalid"
        }

    countries = storefronts or DEFAULT_STOREFRONTS

    # Exact UPC Lookup across storefronts ONLY
    for ctry in countries:
        url = f"https://itunes.apple.com/lookup?upc={clean_upc}&entity=song&country={ctry}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        try:
            with urllib.request.urlopen(req, timeout=4.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("resultCount", 0) > 0:
                    results = data.get("results", [])
                    collection = next((r for r in results if r.get("wrapperType") == "collection"), results[0])
                    tracks = [r for r in results if r.get("wrapperType") == "track"]

                    matched_artist = collection.get("artistName", "")
                    matched_album = collection.get("collectionName", "")
                    matched_title = tracks[0].get("trackName", matched_album) if tracks else matched_album
                    apple_url = collection.get("collectionViewUrl") or (tracks[0].get("trackViewUrl") if tracks else "")
                    copyright_text = collection.get("copyright", "")
                    release_date = (collection.get("releaseDate") or "")[:10]
                    artwork = collection.get("artworkUrl100", "")

                    return {
                        "is_live": True,
                        "status": "Live",
                        "upc": clean_upc,
                        "matched_title": matched_title,
                        "matched_artist": matched_artist,
                        "matched_album": matched_album,
                        "apple_url": apple_url,
                        "copyright": copyright_text,
                        "release_date": release_date,
                        "storefront": ctry.upper(),
                        "artwork_url": artwork,
                        "method": f"Exact UPC Lookup ({ctry.upper()})",
                        "confidence": "Exact UPC Match"
                    }
        except Exception:
            pass

    # No exact match found across any storefront
    return {
        "is_live": False,
        "status": "Not Live",
        "upc": clean_upc,
        "matched_title": "",
        "matched_artist": "",
        "matched_album": "",
        "apple_url": "",
        "copyright": "",
        "release_date": "",
        "storefront": "",
        "artwork_url": "",
        "method": "Exact Lookup Exhausted",
        "confidence": "Not Found"
    }

def batch_check_upcs(
    items: List[Dict[str, Any]],
    max_workers: int = 8,
    progress_callback = None
) -> List[Dict[str, Any]]:
    """Concurrently check multiple UPC items on Apple Music via exact UPC match."""
    results = [None] * len(items)
    total = len(items)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                check_single_upc,
                it.get("upc", ""),
                it.get("artist", ""),
                it.get("title", ""),
                it.get("storefronts", DEFAULT_STOREFRONTS)
            ): idx
            for idx, it in enumerate(items)
        }

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                res = future.result()
            except Exception as e:
                res = {
                    "is_live": False,
                    "status": "Error",
                    "upc": items[idx].get("upc", ""),
                    "error": str(e),
                    "confidence": "Error"
                }
            merged = {**items[idx], **res}
            results[idx] = merged
            completed += 1
            if progress_callback:
                progress_callback(completed, total, merged)

    return results
