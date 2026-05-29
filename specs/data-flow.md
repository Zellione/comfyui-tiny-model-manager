# Data Flow

```
User clicks Download
       │
       ▼
POST /api/download
       │
       ▼
downloader.enqueue()  ──►  asyncio.Queue
                                  │
                                  ▼
                         _run_download()
                           streams file
                                  │
                         file write complete
                                  │
                                  ▼
                    metadata_fetcher.fetch_and_store()
                    ├── civitai/hf API call
                    ├── image download → data/media/
                    └── upsert into SQLite
```
