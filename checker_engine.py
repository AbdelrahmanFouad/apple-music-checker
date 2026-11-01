"""checker_engine.py - High-speed Apple Music storefront availability checker."""

import re
import time
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional

DEFAULT_STOREFRONTS = ["eg", "us", "sa", "dz", "ae", "fr", "gb"]

def normalize_text(text: Optional[str]) -> str:
    """Normalize Arabic and Latin text for comparison."""
    if not text:
        return ""
    t = str(text).lower()
    # Strip common punctuation and brackets
    t = re.sub(r'[\(\)\[\]\{\}\-_\|\\/\.,!?:;\'"״`~*#]', ' ', t)
    # Normalize Arabic characters
    t = re.sub(r'[إأآا]', 'ا', t)
    t = re.sub(r'[يى]', 'ي', t)
    t = re.sub(r'ة', 'ه', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def compute_similarity(str_a: Optional[str], str_b: Optional[str]) -> float:
    """Compute word overlap and substring similarity between two strings."""
    norm_a = normalize_text(str_a)
    norm_b = normalize_text(str_b)
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b or norm_a in norm_b or norm_b in norm_a:
        return 1.0
    words_a = set(norm_a.split())
    words_b = set(norm_b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a.intersection(words_b)
    return len(intersection) / max(len(words_a), len(words_b))

def check_single_upc(
    upc: str,
    target_artist: str = "",
    target_title: str = "",
    storefronts: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Check if a UPC is live on Apple Music via iTunes Lookup API."""
    clean_upc = re.sub(r'\D', '', str(upc or '')).strip()
    if not clean_upc:
        return {
            "is_live": False,
            "status": "Invalid UPC",
            "upc": upc,
            "error": "Empty or non-numeric UPC"
        }

    countries = storefronts or DEFAULT_STOREFRONTS

    # Step 1: Exact UPC Lookup across storefronts
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

                    # Verify artist and title similarity if target values were provided
                    artist_match = compute_similarity(target_artist, matched_artist) if target_artist else 1.0
                    title_match = max(
                        compute_similarity(target_title, matched_title),
                        compute_similarity(target_title, matched_album)
                    ) if target_title else 1.0

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
                        "method": f"UPC Lookup ({ctry.upper()})",
                        "artist_match_score": round(artist_match, 2),
                        "title_match_score": round(title_match, 2),
                        "confidence": "Exact UPC Match"
                    }
        except Exception:
            pass

    # Step 2: Fallback search by artist + title if provided
    if target_artist and target_title:
        for ctry in ["eg", "us", "sa"]:
            query = f"{target_artist} {target_title}".strip()
            url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&media=music&entity=song&country={ctry}&limit=5"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            try:
                with urllib.request.urlopen(req, timeout=4.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for trk in data.get("results", []):
                        t_name = trk.get("trackName", "")
                        a_name = trk.get("artistName", "")
                        art_url = trk.get("artworkUrl100", "")
                        trk_url = trk.get("trackViewUrl", "")
                        coll_name = trk.get("collectionName", "")
                        r_date = (trk.get("releaseDate") or "")[:10]

                        # Check if artwork path contains the target UPC
                        upc_found_in_art = bool(clean_upc and clean_upc in art_url)
                        a_score = compute_similarity(target_artist, a_name)
                        t_score = compute_similarity(target_title, t_name)

                        if upc_found_in_art or (a_score >= 0.75 and t_score >= 0.75):
                            return {
                                "is_live": True,
                                "status": "Live",
                                "upc": clean_upc,
                                "matched_title": t_name,
                                "matched_artist": a_name,
                                "matched_album": coll_name,
                                "apple_url": trk_url,
                                "copyright": "",
                                "release_date": r_date,
                                "storefront": ctry.upper(),
                                "artwork_url": art_url,
                                "method": f"Title/Artist Search ({ctry.upper()})" + (" [UPC Artwork Confirmed]" if upc_found_in_art else ""),
                                "artist_match_score": round(a_score, 2),
                                "title_match_score": round(t_score, 2),
                                "confidence": "High" if upc_found_in_art else "Medium"
                            }
            except Exception:
                pass

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
        "method": "Lookup Exhausted",
        "confidence": "Not Found"
    }

def batch_check_upcs(
    items: List[Dict[str, Any]],
    max_workers: int = 8,
    progress_callback = None
) -> List[Dict[str, Any]]:
    """Concurrently check multiple UPC items on Apple Music."""
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
                it.get("storefronts")
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
                    "error": str(e)
                }
            # Merge original item context
            merged = {**items[idx], **res}
            results[idx] = merged
            completed += 1
            if progress_callback:
                progress_callback(completed, total, merged)

    return results
