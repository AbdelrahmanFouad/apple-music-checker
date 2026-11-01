"""streamlit_app.py - Apple Music Live Checker & CD Tracker Sync App."""

import io
import re
import time
from datetime import datetime
from typing import Dict, List, Any

import pandas as pd
import streamlit as st

import checker_engine
import sheets_sync

# Page configuration
st.set_page_config(
    page_title="Apple Music Live Checker",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Session State
if "scan_results" not in st.session_state:
    st.session_state["scan_results"] = None
if "pending_items" not in st.session_state:
    st.session_state["pending_items"] = None
if "last_updated_count" not in st.session_state:
    st.session_state["last_updated_count"] = None
if "selected_rows_state" not in st.session_state:
    st.session_state["selected_rows_state"] = {}

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.title("Configuration")
    
    st.markdown("### Google Sheets")
    sheet_id_input = st.text_input(
        "Tracker Sheet ID",
        value=sheets_sync.DEFAULT_SHEET_ID,
        help="Google Sheet ID for CD Tracker"
    )
    
    target_status = st.selectbox(
        "Status Value for Live Items",
        options=["Uploaded", "Delivered"],
        index=0,
        help="Value written to Column AE for verified live releases (default: Uploaded)"
    )
    
    update_apple_name_col = st.checkbox(
        "Update Apple Music Name (Column AF)",
        value=True,
        help="Write verified Apple Music link/title into Column AF"
    )

    st.divider()
    st.markdown("### Storefronts & Engine")
    all_storefronts = {
        "EG": "Egypt",
        "SA": "Saudi Arabia",
        "DZ": "Algeria",
        "AE": "United Arab Emirates",
        "US": "United States",
        "FR": "France",
        "GB": "United Kingdom"
    }
    selected_storefronts = st.multiselect(
        "Storefronts to Scan",
        options=list(all_storefronts.keys()),
        default=["EG", "US", "SA", "DZ", "AE"],
        format_func=lambda code: f"{code} - {all_storefronts[code]}"
    )
    
    max_concurrency = st.slider(
        "Concurrent Workers",
        min_value=2,
        max_value=16,
        value=8,
        help="Higher values scan faster but may trigger storefront rate limits"
    )

    st.divider()
    # Check credentials status
    try:
        service_test = sheets_sync.get_sheets_service()
        st.success("Google API Connected", icon=":material/check_circle:")
    except Exception as e:
        st.warning("Google API Not Connected", icon=":material/warning:")
        st.caption(f"Error: {e}")

# --- APP HEADER ---
st.title("🎵 Apple Music Live Checker")
st.caption(
    "Verify whether distributed releases are live on Apple Music by UPC and synchronize their status to 'Uploaded' in the CD Tracker Google Sheet."
)

# --- WORKFLOW TABS ---
input_mode = st.segmented_control(
    "Select Workflow",
    options=["CD Tracker Pending", "Paste UPCs / Manual Input"],
    default="CD Tracker Pending"
)

# -------------------------------------------------------------
# MODE 1: CD TRACKER PENDING
# -------------------------------------------------------------
if input_mode == "CD Tracker Pending":
    st.markdown("#### Scan Pending Releases from CD Tracker")
    st.caption("Fetches all rows currently marked as 'Pending' in '2026_Tickets' and 'New Releases 2026'.")
    
    col_fetch, col_scan = st.columns([1, 1], vertical_alignment="bottom")
    with col_fetch:
        if st.button("Fetch Pending from Sheet", icon=":material/sync:", width="stretch"):
            with st.spinner("Connecting to Google Sheets..."):
                try:
                    pending = sheets_sync.fetch_pending_from_sheet(sheet_id=sheet_id_input)
                    st.session_state["pending_items"] = pending
                    st.session_state["scan_results"] = None
                    st.toast(f"Fetched {len(pending)} pending releases from Google Sheets!", icon=":material/check:")
                except Exception as e:
                    st.error(f"Failed to fetch pending items from Google Sheets: {e}")
                    
    pending_items = st.session_state.get("pending_items")
    if pending_items:
        tickets_count = sum(1 for it in pending_items if it.get("tab") == "2026_Tickets")
        releases_count = sum(1 for it in pending_items if it.get("tab") == "New Releases 2026")
        st.info(
            f"Found **{len(pending_items)}** total pending items: **{tickets_count}** in '2026_Tickets' and **{releases_count}** in 'New Releases 2026'.",
            icon=":material/info:"
        )

        with col_scan:
            if st.button("Start Apple Music Scan", icon=":material/search:", type="primary", width="stretch"):
                progress_bar = st.progress(0, text="Starting scan...")
                status_placeholder = st.empty()

                def on_progress(done, total, item):
                    pct = int((done / total) * 100)
                    progress_bar.progress(pct, text=f"Scanning {done}/{total} ({pct}%) - Checking {item.get('ticket', '')} ({item.get('upc', '')})")

                items_to_scan = [
                    {
                        **it,
                        "storefronts": [s.lower() for s in selected_storefronts]
                    }
                    for it in pending_items
                ]

                start_time = time.time()
                results = checker_engine.batch_check_upcs(
                    items_to_scan,
                    max_workers=max_concurrency,
                    progress_callback=on_progress
                )
                duration = round(time.time() - start_time, 2)
                
                progress_bar.empty()
                status_placeholder.empty()
                st.session_state["scan_results"] = results
                st.success(f"Scan complete in {duration} seconds!", icon=":material/verified:")

# -------------------------------------------------------------
# MODE 2: PASTE UPCS / MANUAL INPUT
# -------------------------------------------------------------
else:
    st.markdown("#### Paste UPCs or Upload File")
    raw_text = st.text_area(
        "Paste UPCs (one per line, or comma-separated)",
        height=150,
        placeholder="730170424336\n730170424701\n730170425326"
    )

    uploaded_file = st.file_uploader("Or upload CSV / Excel with a 'UPC' column", type=["csv", "xlsx"])
    
    col_manual_run, _ = st.columns([1, 2], vertical_alignment="bottom")
    with col_manual_run:
        if st.button("Scan Pasted UPCs", icon=":material/search:", type="primary", width="stretch"):
            upc_list = []
            if raw_text.strip():
                # Extract all numeric strings between 10 and 15 digits
                tokens = re.split(r'[\r\n,\t; ]+', raw_text.strip())
                for tok in tokens:
                    clean = re.sub(r'\D', '', tok)
                    if clean and len(clean) >= 10:
                        upc_list.append({"upc": clean, "ticket": "Manual Input", "artist": "", "title": ""})
            
            if uploaded_file is not None:
                try:
                    if uploaded_file.name.endswith(".csv"):
                        df_upload = pd.read_csv(uploaded_file)
                    else:
                        df_upload = pd.read_excel(uploaded_file)
                    
                    # Look for UPC column
                    col_found = next((c for c in df_upload.columns if "upc" in str(c).lower()), None)
                    if col_found:
                        for _, row in df_upload.iterrows():
                            val = str(row[col_found]).split(".")[0].strip()
                            clean = re.sub(r'\D', '', val)
                            if clean and len(clean) >= 10:
                                upc_list.append({
                                    "upc": clean,
                                    "ticket": str(row.get("Ticket Number", "File Upload")),
                                    "artist": str(row.get("Artist", "")),
                                    "title": str(row.get("Title", ""))
                                })
                    else:
                        st.error("Uploaded file must have a column containing 'UPC'")
                except Exception as e:
                    st.error(f"Error reading file: {e}")

            if not upc_list:
                st.warning("Please paste at least one valid UPC or upload a file.")
            else:
                progress_bar = st.progress(0, text="Starting scan...")
                def on_progress(done, total, item):
                    pct = int((done / total) * 100)
                    progress_bar.progress(pct, text=f"Scanning {done}/{total} ({pct}%) - UPC: {item.get('upc', '')}")

                items_to_scan = [
                    {
                        **it,
                        "storefronts": [s.lower() for s in selected_storefronts]
                    }
                    for it in upc_list
                ]

                start_time = time.time()
                results = checker_engine.batch_check_upcs(
                    items_to_scan,
                    max_workers=max_concurrency,
                    progress_callback=on_progress
                )
                duration = round(time.time() - start_time, 2)
                progress_bar.empty()
                st.session_state["scan_results"] = results
                st.success(f"Scanned {len(results)} UPCs in {duration} seconds!", icon=":material/verified:")

# -------------------------------------------------------------
# RESULTS SECTION
# -------------------------------------------------------------
results = st.session_state.get("scan_results")

if results:
    st.divider()
    st.subheader("Scan Results")

    total_scanned = len(results)
    live_count = sum(1 for r in results if r.get("is_live"))
    not_live_count = total_scanned - live_count
    live_pct = round((live_count / total_scanned * 100), 1) if total_scanned > 0 else 0.0

    # Summary Metrics
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Scanned", f"{total_scanned}")
    with m2:
        st.metric("Live on Apple Music", f"{live_count}", delta=f"{live_pct}% Live", delta_color="normal")
    with m3:
        st.metric("Not Live / Pending", f"{not_live_count}", delta=f"{round(100 - live_pct, 1)}%", delta_color="inverse")
    with m4:
        can_update_sheet = any(r.get("tab") and r.get("row") for r in results if r.get("is_live"))
        st.metric("Sheet Update Ready", f"{live_count if can_update_sheet else 0} Rows")

    # Table Filter
    filter_choice = st.segmented_control(
        "Filter View",
        options=["All Items", "Live Only", "Not Live Only"],
        default="All Items"
    )

    # Prepare DataFrame
    table_data = []
    for idx, r in enumerate(results):
        is_live = bool(r.get("is_live"))
        
        # Filter check
        if filter_choice == "Live Only" and not is_live:
            continue
        if filter_choice == "Not Live Only" and is_live:
            continue

        table_data.append({
            "_idx": idx,
            "Update Sheet": is_live and bool(r.get("tab") and r.get("row")),
            "Status": "🟢 Live" if is_live else "🔴 Not Live",
            "UPC": str(r.get("upc", "")),
            "Ticket": str(r.get("ticket", "")),
            "Original Title": str(r.get("title", "")),
            "Original Artist": str(r.get("artist", "")),
            "Matched Title": str(r.get("matched_title", "")),
            "Matched Artist": str(r.get("matched_artist", "")),
            "Matched Album": str(r.get("matched_album", "")),
            "Apple Music Link": str(r.get("apple_url", "")),
            "Storefront": str(r.get("storefront", "")),
            "Confidence": str(r.get("confidence", "")),
            "Tab": str(r.get("tab", "")),
            "Row": r.get("row", "")
        })

    df_view = pd.DataFrame(table_data)

    if not df_view.empty:
        # Selection and Edit controls
        st.caption("Review results below. Check or uncheck releases before updating the tracker sheet.")
        
        edited_df = st.data_editor(
            df_view,
            column_config={
                "Update Sheet": st.column_config.CheckboxColumn(
                    "Update Sheet",
                    help="Check to include this row in the sheet update to 'Uploaded'",
                    default=True
                ),
                "Apple Music Link": st.column_config.LinkColumn(
                    "Apple Music Link",
                    display_text="View Track"
                ),
                "Status": st.column_config.TextColumn(
                    "Status",
                    width="small"
                ),
                "UPC": st.column_config.TextColumn(
                    "UPC",
                    width="medium"
                )
            },
            disabled=[c for c in df_view.columns if c != "Update Sheet"],
            hide_index=True,
            width="stretch",
            key="results_data_editor"
        )

        # -------------------------------------------------------------
        # DRY RUN & SHEET UPDATE ACTION BAR
        # -------------------------------------------------------------
        st.divider()
        st.subheader("Update CD Tracker Sheet")

        # Determine which items are selected for update
        selected_for_update = []
        if edited_df is not None and not edited_df.empty:
            for _, row in edited_df.iterrows():
                if row.get("Update Sheet") and row.get("Tab") and row.get("Row"):
                    orig_idx = row.get("_idx")
                    selected_for_update.append(results[orig_idx])

        if selected_for_update:
            st.info(
                f"**Dry Run Preview**: **{len(selected_for_update)}** release(s) selected for synchronization.\n\n"
                f"- **Target Sheet ID**: `{sheet_id_input}`\n"
                f"- **Status Target**: Column AE will be updated to **`{target_status}`**\n"
                f"- **Apple Music Name / Link**: Column AF will be updated: **{'Yes' if update_apple_name_col else 'No'}**",
                icon=":material/visibility:"
            )

            # Confirmation and Action
            col_confirm, col_action = st.columns([1, 1], vertical_alignment="bottom")
            with col_confirm:
                confirm_check = st.checkbox(
                    "I confirm these releases are live and approve updating the live CD Tracker Google Sheet.",
                    value=False
                )

            with col_action:
                update_btn = st.button(
                    f"Update {len(selected_for_update)} Releases in CD Tracker",
                    type="primary",
                    disabled=not confirm_check,
                    icon=":material/cloud_upload:",
                    width="stretch"
                )

            if update_btn and confirm_check:
                with st.spinner("Executing atomic batch update to Google Sheet..."):
                    try:
                        update_res = sheets_sync.batch_update_sheet_status(
                            sheet_id=sheet_id_input,
                            items_to_update=selected_for_update,
                            target_status=target_status,
                            update_apple_name=update_apple_name_col
                        )
                        st.session_state["last_updated_count"] = update_res.get("updated_count", 0)
                        st.success(
                            f"Successfully updated **{update_res.get('updated_count')}** rows in CD Tracker! "
                            f"(Total cells updated: {update_res.get('total_cells_updated')})",
                            icon=":material/task_alt:"
                        )
                        st.balloons()
                    except Exception as e:
                        st.error(f"Failed to update Google Sheet: {e}", icon=":material/error:")
        else:
            st.info("No live releases with sheet tab/row locations are currently selected for update.")

        # -------------------------------------------------------------
        # EXPORT CSV
        # -------------------------------------------------------------
        st.divider()
        csv_buffer = io.StringIO()
        export_df = pd.DataFrame(results)
        export_df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
        
        st.download_button(
            label="Download Scan Results (CSV)",
            data=csv_buffer.getvalue(),
            file_name=f"apple_music_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            icon=":material/download:"
        )
    else:
        st.info("No items match the selected filter.")
