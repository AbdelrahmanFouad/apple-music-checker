# Apple Music Live Checker (Manual UPC Mode)

A streamlined, high-speed Streamlit application designed to verify music catalog availability on Apple Music by UPC across global storefronts (Egypt, Saudi Arabia, Algeria, UAE, US, France, UK, Morocco).

---

## Features

- **Multi-Format UPC Input**: Paste UPCs one per line, comma-separated, or copy-pasted directly from Excel/Sheets.
- **File Upload**: Upload any CSV or Excel file (`.xlsx`, `.xls`) with automatic UPC column detection.
- **Concurrent High-Speed Lookup**: Multi-threaded Apple Music storefront queries (up to 16 parallel workers) checking catalog availability, track title, artist, album, storefront, release date, artwork, and sound recording copyright.
- **Interactive Results**: Real-time progress, live metrics, filtering (`All` / `Live Only` / `Not Live Only`), and rich data table with artwork thumbnails and direct Apple Music links.
- **Instant Export**: 1-click Download as CSV, Download as Excel, or copy live/unlive UPC lists directly to clipboard.
- **Zero Cloud Dependencies**: Requires no Google credentials, service accounts, or tokens.

---

## Local Development

```powershell
cd "C:\SCRIPTS\apple_music_checker"
$env:PYTHONIOENCODING="utf-8"
streamlit run streamlit_app.py --server.port 8502
```

---

## Deployment (Streamlit Community Cloud)

1. Push this folder to a GitHub repository (e.g. `AbdelrahmanFouad/apple-music-checker`).
2. Deploy on [Streamlit Community Cloud](https://share.streamlit.io):
   - **Main file path**: `streamlit_app.py`
3. Optional: Set a PIN/password in **App Settings -> Secrets**:
   ```toml
   app_password = "YOUR_PIN_OR_PASSWORD"
   ```
