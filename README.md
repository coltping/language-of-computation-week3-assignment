# language-of-computation-week3-assignment

This is my Module 3 assignment for MSAI-5523.

## How to run the ingestion (Windows)

`ingest.py` loads a books CSV file into `books.db`, following the rules in `rules.md`. Each run adds an entry to `ingestion-log.json`. Both files are created in this folder, next to `ingest.py`.

### 1. Open a terminal in this folder

1. Press the **Windows key**, type `PowerShell`, and press **Enter**.
2. Go to the assignment folder:

   ```powershell
   cd $HOME\workspace\language-of-computation\week3-assignment
   ```

3. Check that Python works. It should print `Python 3.13` or newer:

   ```powershell
   python --version
   ```

   If it says Python was not found, close PowerShell and open it again. A terminal that was open before Python was installed doesn't know about it yet.

### 2. Run the ingestion

Run these three commands one at a time, in this order:

```powershell
python ingest.py books.csv
```

```powershell
python ingest.py books.csv
```

```powershell
python ingest.py books-batch2.csv
```

After each run, the terminal prints how many rows were read, loaded, updated, skipped (already exist), rejected, and loaded with warnings, and whether every row is accounted for. The first command takes a few seconds, because books.csv has 10,000 rows.

### 3. Open the report

1. Open the report in your browser. Either double-click `report.html` in File Explorer, or run:

   ```powershell
   start report.html
   ```

2. Click **Open ingestion-log.json** and choose `ingestion-log.json` from this folder.
3. The runs are shown newest first. Each run shows its counts, a verdict, every rejected row with what to do about it, and every warning. Click a warning kind to filter the list, or search by book_id, title or value.

The report works without a server or internet connection.

### Start over

To rebuild from scratch, delete the database and the log, then repeat step 2:

```powershell
Remove-Item books.db, ingestion-log.json
```
