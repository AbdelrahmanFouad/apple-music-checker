"""sheets_sync.py - Google Sheets integration for CD Tracker Apple Music sync."""

import json
import os
import sys
from typing import Dict, List, Any, Optional

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build

DEFAULT_SHEET_ID = "1w7kB0FFBLND3tUc64cGIYSss2OJuCC4kmec5JLfw42Q"
DEFAULT_LOCAL_TOKEN = r"C:\Scripts\contentid_api_migration\google_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly"
]

def get_sheets_service(custom_credentials=None, local_token_path: str = DEFAULT_LOCAL_TOKEN):
    """Authenticate and build Google Sheets service.
    
    Checks in order:
    1. custom_credentials passed directly
    2. Streamlit secrets (st.secrets["gcp_service_account"] or st.secrets["google_token"])
    3. Local google_token.json file
    """
    if custom_credentials:
        return build("sheets", "v4", credentials=custom_credentials)

    # Check Streamlit secrets if running inside Streamlit
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            if "gcp_service_account" in st.secrets:
                sa_info = st.secrets["gcp_service_account"]
                if isinstance(sa_info, str):
                    sa_info = json.loads(sa_info)
                else:
                    sa_info = dict(sa_info)
                creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
                return build("sheets", "v4", credentials=creds)

            if "google_token" in st.secrets:
                t_info = st.secrets["google_token"]
                if isinstance(t_info, str):
                    t_info = json.loads(t_info)
                else:
                    t_info = dict(t_info)
                creds = Credentials.from_authorized_user_info(t_info)
                return build("sheets", "v4", credentials=creds)
    except Exception:
        pass

    # Fallback to local token
    if os.path.exists(local_token_path):
        with open(local_token_path, "r", encoding="utf-8") as f:
            token_data = json.load(f)
        creds = Credentials.from_authorized_user_info(token_data)
        return build("sheets", "v4", credentials=creds)

    raise FileNotFoundError(
        f"No valid Google credentials found. Checked Streamlit secrets and {local_token_path}"
    )

def fetch_pending_from_sheet(sheet_id: str = DEFAULT_SHEET_ID) -> List[Dict[str, Any]]:
    """Fetch all rows with 'Pending' status in Apple Music column from both tabs."""
    service = get_sheets_service()
    pending_items = []

    tabs_config = [
        {"tab": "2026_Tickets", "status_header": "apple music"},
        {"tab": "New Releases 2026", "status_header": "apple music aprroved"}
    ]

    for cfg in tabs_config:
        tab_name = cfg["tab"]
        target_hdr = cfg["status_header"]

        # Fetch entire active range A1:AO6000
        resp = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{tab_name}'!A1:AO6000"
        ).execute()

        rows = resp.get("values", [])
        if len(rows) < 2:
            continue

        header = rows[0]
        col_idx = {str(h).strip().lower(): i for i, h in enumerate(header) if h}

        # Identify key column indices
        upc_col = col_idx.get("upc", 14)
        isrc_col = col_idx.get("isrc", 15)
        ticket_col = col_idx.get("ticket number", 35)
        artist_en_col = col_idx.get("artist name en", 3)
        song_en_col = col_idx.get("song name en", 4)
        artist_ar_col = col_idx.get("artist name ar", 5)
        song_ar_col = col_idx.get("song name ar", 6)
        label_col = col_idx.get("asset label", col_idx.get("record label", 13))

        # Status column
        status_col = None
        for h, idx in col_idx.items():
            if "apple" in h and ("music" in h or "status" in h or "aprroved" in h):
                status_col = idx
                break
        if status_col is None:
            status_col = 30  # Default column AE

        # Apple Music Name / URL column
        name_col = col_idx.get("apple music name", 31)

        for row_num, r in enumerate(rows[1:], start=2):
            if not any(str(c or "").strip() for c in r):
                continue

            current_status = str(r[status_col]).strip() if len(r) > status_col and r[status_col] else ""
            if current_status.lower() != "pending":
                continue

            upc = str(r[upc_col]).strip() if len(r) > upc_col and r[upc_col] else ""
            isrc = str(r[isrc_col]).strip() if len(r) > isrc_col and r[isrc_col] else ""
            ticket = str(r[ticket_col]).strip() if len(r) > ticket_col and r[ticket_col] else f"Row {row_num}"
            artist = (str(r[artist_ar_col]).strip() if len(r) > artist_ar_col and r[artist_ar_col] else "") or \
                     (str(r[artist_en_col]).strip() if len(r) > artist_en_col and r[artist_en_col] else "")
            song = (str(r[song_ar_col]).strip() if len(r) > song_ar_col and r[song_ar_col] else "") or \
                   (str(r[song_en_col]).strip() if len(r) > song_en_col and r[song_en_col] else "")
            label = str(r[label_col]).strip() if len(r) > label_col and r[label_col] else ""
            existing_name = str(r[name_col]).strip() if len(r) > name_col and r[name_col] else ""

            pending_items.append({
                "tab": tab_name,
                "row": row_num,
                "ticket": ticket,
                "upc": upc,
                "isrc": isrc,
                "artist": artist,
                "title": song,
                "label": label,
                "current_status": current_status,
                "existing_apple_name": existing_name
            })

    return pending_items

def batch_update_sheet_status(
    sheet_id: str,
    items_to_update: List[Dict[str, Any]],
    target_status: str = "Uploaded",
    update_apple_name: bool = True
) -> Dict[str, Any]:
    """Execute batch cell updates in the CD Tracker Google Sheet.
    
    Sets Column AE to target_status ('Uploaded').
    Optionally sets Column AF to the verified Apple Music track name or link.
    """
    if not items_to_update:
        return {"updated_count": 0, "message": "No items to update"}

    service = get_sheets_service()
    data_payload = []

    for it in items_to_update:
        tab = it["tab"]
        row = it["row"]

        # Status cell in Column AE (col 31)
        data_payload.append({
            "range": f"'{tab}'!AE{row}",
            "values": [[target_status]]
        })

        # Name / Link cell in Column AF (col 32)
        if update_apple_name:
            apple_url = it.get("apple_url", "")
            matched_title = it.get("matched_title", "")
            # Prefer link or matched title
            val_af = apple_url if apple_url else matched_title
            if val_af:
                data_payload.append({
                    "range": f"'{tab}'!AF{row}",
                    "values": [[val_af]]
                })

    body = {
        "valueInputOption": "USER_ENTERED",
        "data": data_payload
    }

    resp = service.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body=body
    ).execute()

    return {
        "updated_count": len(items_to_update),
        "total_cells_updated": resp.get("totalUpdatedCells", 0),
        "responses": resp
    }
