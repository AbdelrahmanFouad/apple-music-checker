# Apple Music Live Checker & CD Tracker Sync

A streamlined, high-speed Streamlit application designed to verify catalog delivery on Apple Music by UPC across global storefronts (Egypt, Saudi Arabia, Algeria, UAE, US, France, UK) and atomically synchronize verified live releases to the CD Tracker Google Sheet (`Column AE -> 'Uploaded'`).

---

## Features

- **Direct Sheet Integration**: 1-click fetch of all pending releases directly from Google Sheets (`2026_Tickets` and `New Releases 2026`).
- **Arbitrary Input Mode**: Paste raw UPCs (one per line or comma-separated) or upload CSV/Excel files.
- **Concurrent High-Speed Lookup**: Multi-threaded Apple Music storefront queries (up to 16 parallel workers) checking catalog availability, track title, artist, album, storefront, and sound recording copyright.
- **Safety First & Dry-Run Preview**: Displays the exact releases, tab names, and row numbers before any update. Interactive checkboxes let you review and toggle updates per release.
- **Atomic Batch Sync**: Updates Column AE to `Uploaded` (and optionally Column AF to the verified Apple Music URL/Title) via atomic `spreadsheets.values.batchUpdate`.
- **CSV Export**: Export all verified and unverified releases with links and metadata.

---

## Local Development

```bash
cd "C:\SCRIPTS\apple_music_checker"
streamlit run streamlit_app.py --server.port 8502
```

---

## Streamlit Community Cloud Deployment

1. Push this folder to a private GitHub repository.
2. Link the repository to [Streamlit Community Cloud](https://share.streamlit.io).
3. Set Main file path: `streamlit_app.py`.
4. In **App Settings -> Secrets**, paste your Google OAuth token or GCP Service Account JSON as shown in `.streamlit/secrets.toml.example`.
5. Deploy!
