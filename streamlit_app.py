"""streamlit_app.py - High-Speed Apple Music Live Checker (Exact UPC Match Only)."""

import io
import re
import time
from datetime import datetime
from typing import Dict, List, Any

import pandas as pd
import streamlit as st

import checker_engine

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Apple Music Live Checker",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Optional Password Gate (if app_password defined in st.secrets)
if hasattr(st, "secrets") and "app_password" in st.secrets:
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 Apple Music Checker — Access Restricted")
        col_pwd, _ = st.columns([1, 2])
        with col_pwd:
            input_pwd = st.text_input("Enter Access PIN / Password", type="password")
            if st.button("Unlock App", type="primary", width="stretch"):
                if input_pwd == str(st.secrets["app_password"]):
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect password. Please try again.")
        st.stop()

# --- INITIALIZE STATE ---
if "manual_results" not in st.session_state:
    st.session_state["manual_results"] = None
if "pasted_text" not in st.session_state:
    st.session_state["pasted_text"] = ""

# --- APP HEADER ---
st.title("🎵 Apple Music Live Checker")
st.caption(
    "Verify catalog delivery on Apple Music by **exact UPC match only**. Zero false positives, no fuzzy matching."
)

# --- INPUT SECTION ---
with st.container(border=True):
    col_input, col_file = st.columns([1.2, 1], gap="medium")

    with col_input:
        st.markdown("##### Paste UPCs")
        st.caption("Enter UPCs (one per line, comma-separated, or pasted from Excel).")

        col_s1, col_s2, _ = st.columns([1, 1, 1.5])
        with col_s1:
            if st.button("Load Samples", icon=":material/playlist_add:", width="stretch"):
                # 4 sample UPCs: 3 known live, 1 pending
                sample_upcs = "730170424336\n730170440831\n730170441074\n730170424701"
                st.session_state["pasted_text"] = sample_upcs
                st.rerun()
        with col_s2:
            if st.button("Clear Input", icon=":material/clear_all:", width="stretch"):
                st.session_state["pasted_text"] = ""
                st.session_state["manual_results"] = None
                st.rerun()

        input_upcs = st.text_area(
            "UPC Input",
            value=st.session_state.get("pasted_text", ""),
            height=180,
            placeholder="730170424336\n730170440831\n730170441074",
            label_visibility="collapsed"
        )

    with col_file:
        st.markdown("##### Or Upload File")
        st.caption("Upload a CSV or Excel file containing a 'UPC' or 'Barcode' column.")
        uploaded_file = st.file_uploader(
            "Upload CSV or Excel",
            type=["csv", "xlsx", "xls"],
            label_visibility="collapsed"
        )

# Parse UPCs
parsed_items = []

# 1. From Text Input
if input_upcs.strip():
    tokens = re.split(r'[\r\n,\t; ]+', input_upcs.strip())
    seen = set()
    for tok in tokens:
        clean = re.sub(r'\D', '', tok)
        if clean and len(clean) >= 10 and clean not in seen:
            seen.add(clean)
            parsed_items.append({"upc": clean, "source": "Pasted"})

# 2. From Uploaded File
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df_file = pd.read_csv(uploaded_file)
        else:
            df_file = pd.read_excel(uploaded_file)

        # Detect UPC column
        col_candidates = [c for c in df_file.columns if any(k in str(c).lower() for k in ["upc", "barcode", "ean", "catalog"])]
        target_col = col_candidates[0] if col_candidates else df_file.columns[0]

        file_seen = set(it["upc"] for it in parsed_items)
        file_count = 0
        for _, row in df_file.iterrows():
            val = str(row[target_col]).split(".")[0].strip()
            clean = re.sub(r'\D', '', val)
            if clean and len(clean) >= 10 and clean not in file_seen:
                file_seen.add(clean)
                parsed_items.append({
                    "upc": clean,
                    "source": f"File ({uploaded_file.name})"
                })
                file_count += 1
        st.success(f"Loaded **{file_count}** unique UPCs from `{uploaded_file.name}` (Column: `{target_col}`)", icon=":material/check_circle:")
    except Exception as e:
        st.error(f"Error reading file: {e}", icon=":material/error:")

# --- SCAN TRIGGER ---
col_run, col_info = st.columns([1, 2], vertical_alignment="center")

with col_run:
    scan_clicked = st.button(
        f"Check Apple Music ({len(parsed_items)} UPCs)" if parsed_items else "Check Apple Music Availability",
        type="primary",
        disabled=len(parsed_items) == 0,
        icon=":material/search:",
        width="stretch"
    )

with col_info:
    if parsed_items:
        st.caption(f"Ready to check **{len(parsed_items)}** unique UPCs via exact lookup across storefronts.")

if scan_clicked and parsed_items:
    scan_payload = [
        {
            "upc": it["upc"],
            "source": it.get("source", "Manual"),
            "storefronts": checker_engine.DEFAULT_STOREFRONTS
        }
        for it in parsed_items
    ]

    progress_bar = st.progress(0, text="Initiating exact UPC lookups...")

    def on_progress(done, total, item):
        pct = int((done / total) * 100)
        progress_bar.progress(pct, text=f"Checking {done}/{total} ({pct}%) — UPC: {item.get('upc', '')}")

    start_t = time.time()
    results = checker_engine.batch_check_upcs(
        scan_payload,
        max_workers=8,
        progress_callback=on_progress
    )
    elapsed = round(time.time() - start_t, 2)
    progress_bar.empty()

    st.session_state["manual_results"] = {
        "items": results,
        "elapsed": elapsed,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    st.toast(f"Checked {len(results)} UPCs in {elapsed}s!", icon=":material/verified:")

# --- RESULTS SECTION ---
res_state = st.session_state.get("manual_results")

if res_state:
    results_list = res_state["items"]
    elapsed_time = res_state["elapsed"]

    total = len(results_list)
    live_count = sum(1 for r in results_list if r.get("is_live"))
    not_live_count = total - live_count
    live_pct = round((live_count / total * 100), 1) if total > 0 else 0.0
    speed = round(total / elapsed_time, 1) if elapsed_time > 0 else 0.0

    st.divider()
    st.subheader("Verification Results")

    # Metrics Row
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Checked", f"{total}")
    with m2:
        st.metric("Live (Exact Match)", f"{live_count}", delta=f"{live_pct}% Live", delta_color="normal")
    with m3:
        st.metric("Not Live / Unavailable", f"{not_live_count}", delta=f"{round(100 - live_pct, 1)}%", delta_color="inverse")
    with m4:
        st.metric("Scan Speed", f"{speed} UPCs/sec", delta=f"{elapsed_time}s total")

    # Filter Segmented Control
    filter_mode = st.segmented_control(
        "Filter View",
        options=[
            f"All ({total})",
            f"Live Only ({live_count})",
            f"Not Live Only ({not_live_count})"
        ],
        default=f"All ({total})"
    )

    # Filter data
    filtered_rows = []
    for r in results_list:
        is_live = bool(r.get("is_live"))
        if "Live Only" in filter_mode and not is_live:
            continue
        if "Not Live Only" in filter_mode and is_live:
            continue

        filtered_rows.append({
            "Status": "🟢 Live" if is_live else "🔴 Not Live",
            "Artwork": r.get("artwork_url", ""),
            "UPC": str(r.get("upc", "")),
            "Track Title": r.get("matched_title", ""),
            "Artist": r.get("matched_artist", ""),
            "Album": r.get("matched_album", ""),
            "Apple Music Link": r.get("apple_url", ""),
            "Storefront": r.get("storefront", ""),
            "Release Date": r.get("release_date", ""),
            "Copyright": r.get("copyright", "")
        })

    df_display = pd.DataFrame(filtered_rows)

    if not df_display.empty:
        st.dataframe(
            df_display,
            column_config={
                "Artwork": st.column_config.ImageColumn(
                    "Artwork",
                    help="Release cover artwork",
                    width="small"
                ),
                "Status": st.column_config.TextColumn(
                    "Status",
                    width="small"
                ),
                "UPC": st.column_config.TextColumn(
                    "UPC",
                    width="medium"
                ),
                "Track Title": st.column_config.TextColumn(
                    "Track Title",
                    width="medium"
                ),
                "Artist": st.column_config.TextColumn(
                    "Artist",
                    width="medium"
                ),
                "Album": st.column_config.TextColumn(
                    "Album",
                    width="medium"
                ),
                "Apple Music Link": st.column_config.LinkColumn(
                    "Apple Music Link",
                    display_text="Open in Apple Music",
                    width="medium"
                ),
                "Storefront": st.column_config.TextColumn(
                    "Storefront",
                    width="small"
                ),
                "Release Date": st.column_config.TextColumn(
                    "Release Date",
                    width="small"
                )
            },
            hide_index=True,
            width="stretch"
        )

        # --- EXPORT & COPY ACTIONS ---
        st.divider()
        st.markdown("##### Export Results")

        col_dl_csv, col_dl_excel, _ = st.columns([1, 1, 2])

        # CSV Export
        with col_dl_csv:
            csv_buf = io.StringIO()
            pd.DataFrame(results_list).to_csv(csv_buf, index=False, encoding="utf-8-sig")
            st.download_button(
                label="Download CSV",
                data=csv_buf.getvalue(),
                file_name=f"apple_music_exact_matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                icon=":material/download:",
                width="stretch"
            )

        # Excel Export
        with col_dl_excel:
            excel_buf = io.BytesIO()
            with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
                pd.DataFrame(results_list).to_excel(writer, index=False, sheet_name="Results")
            st.download_button(
                label="Download Excel",
                data=excel_buf.getvalue(),
                file_name=f"apple_music_exact_matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/table_view:",
                width="stretch"
            )

        # Quick Copy Expanders
        live_upcs_only = [str(r.get("upc", "")) for r in results_list if r.get("is_live")]
        not_live_upcs_only = [str(r.get("upc", "")) for r in results_list if not r.get("is_live")]

        with st.expander("📋 Copy Live UPCs / Not Live UPCs"):
            c_live, c_not = st.columns(2)
            with c_live:
                st.markdown(f"**Live UPCs ({len(live_upcs_only)})**")
                st.text_area(
                    "Live UPCs",
                    value="\n".join(live_upcs_only),
                    height=120,
                    label_visibility="collapsed"
                )
            with c_not:
                st.markdown(f"**Not Live UPCs ({len(not_live_upcs_only)})**")
                st.text_area(
                    "Not Live UPCs",
                    value="\n".join(not_live_upcs_only),
                    height=120,
                    label_visibility="collapsed"
                )
    else:
        st.info("No items match the selected filter.")
