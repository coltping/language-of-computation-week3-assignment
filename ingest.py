"""Load a books CSV file into books.db, following rules.md.

Usage:  python ingest.py <file.csv>

books.db and ingestion-log.json are created next to this script (rules.md, answer 11).
The script uses no internet and no AI: the same file always gives the same result.
"""
import csv
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "books.db")
LOG_PATH = os.path.join(HERE, "ingestion-log.json")
REQUIRED_COLUMNS = ("book_id", "title", "isbn", "isbn13")


# ---------------------------------------------------------------------------
# Section 1: what counts as a valid ISBN
# ---------------------------------------------------------------------------

def isbn10_valid(s):
    if not re.fullmatch(r"\d{9}[\dX]", s):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(s))
    return total % 11 == 0


def isbn13_valid(s):
    if not re.fullmatch(r"97[89]\d{10}", s):
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s))
    return total % 10 == 0


def isbn10_to_13(isbn10):
    core = "978" + isbn10[:9]
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core))
    return core + str((10 - total % 10) % 10)


def strip_hyphens_spaces(raw):
    return re.sub(r"[\s-]", "", raw)


# ---------------------------------------------------------------------------
# Section 2: what happens to each kind of problem
#
# Each column is read into one of these results:
#   ("empty",)                        no value
#   ("isbn10", value, repairs)        valid ISBN-10 (repairs = list of certain fixes made)
#   ("isbn13", value, repairs)        valid ISBN-13
#   ("sci", text)                     978/979 ISBN-13 in scientific notation
#   ("broken", code, reason)          looks like an ISBN but can't be used: a fix would be a guess
#   ("not_isbn", reason)              not an ISBN-13 at all (barcode, decimal, truncated...)
# ---------------------------------------------------------------------------

def read_isbn_column(raw):
    s = strip_hyphens_spaces(raw)
    if s == "":
        return ("empty",)
    repairs = []
    if s != raw:
        repairs.append(("hyphens_spaces", "removed hyphens/spaces"))

    if re.fullmatch(r"\d{13}", s):
        if isbn13_valid(s):
            repairs.append(("isbn13_in_isbn_column", "valid ISBN-13 found in the isbn (ISBN-10) column"))
            return ("isbn13", s, repairs)
        return ("broken", "bad_check_digit", "13-digit value in the isbn column with a wrong ISBN-13 check digit")

    if re.fullmatch(r"\d*x", s):
        s = s[:-1] + "X"
        repairs.append(("lowercase_x", "made the check character uppercase"))

    padded = False
    if re.fullmatch(r"\d{0,8}[\dX]", s):
        zeros = 10 - len(s)
        s = "0" * zeros + s
        padded = True
        repairs.append(("leading_zeros", f"added {zeros} leading zero{'s' if zeros > 1 else ''}"))

    if re.fullmatch(r"\d{9}[\dX]", s):
        if isbn10_valid(s):
            return ("isbn10", s, repairs)
        if padded:
            return ("broken", "too_short_bad_check", "too short, and still fails the ISBN-10 check after adding zeros")
        if s.isdigit() and isbn13_valid("978" + s):
            return ("broken", "978_cut_off", f"looks like an ISBN-13 with 978 cut off (978{s}); not repaired because it is an inference")
        return ("broken", "bad_check_digit", "wrong ISBN-10 check digit")

    if re.fullmatch(r"\d+", s):
        return ("broken", "wrong_length", f"wrong length: {len(s)} digits")
    return ("broken", "invalid_characters", "contains characters that can't be in an ISBN")


def read_isbn13_column(raw):
    s = strip_hyphens_spaces(raw)
    if s == "":
        return ("empty",)
    repairs = [("hyphens_spaces", "removed hyphens/spaces")] if s != raw else []

    if re.fullmatch(r"\d{13}", s):
        if not s.startswith(("978", "979")):
            return ("not_isbn", "13 digits, but the prefix is not 978 or 979")
        if isbn13_valid(s):
            return ("isbn13", s, repairs)
        return ("broken", "bad_check_digit", "wrong ISBN-13 check digit")

    if re.fullmatch(r"\d(\.\d+)?[eE]\+?\d+", s):
        try:
            value = Decimal(s)
        except InvalidOperation:
            return ("not_isbn", "not a number")
        if value == value.to_integral_value() and str(int(value)).startswith(("978", "979")) and len(str(int(value))) == 13:
            return ("sci", s)
        return ("not_isbn", "scientific-notation value that is not a 978/979 ISBN-13 (another kind of barcode)")

    return ("not_isbn", "not a 13-digit ISBN (decimal number, truncated value or other barcode)")


def sci_matches(sci_text, isbn13):
    """True if isbn13, rounded to 12 significant digits, equals the file value (rules.md, answer 12).
    A value showing fewer digits means the missing ones were zeros."""
    return Decimal(f"{int(isbn13):.11e}") == Decimal(sci_text)


def clean_isbns(raw10, raw13):
    """Apply section 2 (and answers 2, 5, 9) to one row. Returns (isbn10, isbn13, warnings)."""
    warnings = []
    c10 = read_isbn_column(raw10)
    c13 = read_isbn13_column(raw13)

    def warn(column, original, outcome, code, reason, new_value=None):
        warnings.append({"column": column, "original": original, "outcome": outcome,
                         "code": code, "reason": reason, "new_value": new_value})

    def load_neither(reason):
        # Repairs don't matter when neither ISBN is kept, so only the disagreement is reported.
        warnings[:] = [w for w in warnings if w["outcome"] != "repaired"]
        warn("isbn + isbn13", f"{raw10} | {raw13}", "ISBN not loaded", "isbn_columns_disagree", reason)
        return None, None, warnings

    # Report what was found in each column.
    for column, raw, c in (("isbn", raw10, c10), ("isbn13", raw13, c13)):
        if c[0] in ("isbn10", "isbn13") and c[2]:
            warn(column, raw, "repaired", "+".join(code for code, _ in c[2]),
                 "; ".join(text for _, text in c[2]), c[1])
        elif c[0] == "broken":
            warn(column, raw, "ISBN not loaded", c[1], c[2])
        elif c[0] == "not_isbn":
            warn(column, raw, "ignored", "not_an_isbn13", c[1])

    # Collect every valid ISBN-13 this row offers.
    isbn10 = c10[1] if c10[0] == "isbn10" else None
    candidates = []
    if isbn10:
        candidates.append(isbn10_to_13(isbn10))
    if c10[0] == "isbn13":
        candidates.append(c10[1])
    if c13[0] == "isbn13":
        candidates.append(c13[1])
    distinct = sorted(set(candidates))

    if len(distinct) > 1:
        return load_neither("the ISBN-10 and ISBN-13 are both valid but are not the same book; loaded with neither")

    isbn13 = distinct[0] if distinct else None

    if c13[0] == "sci":
        if isbn13 is None:
            warn("isbn13", raw13, "ISBN not loaded", "sci_no_isbn10",
                 "scientific notation lost the last digit and there is no valid ISBN-10 to rebuild it from")
        elif sci_matches(c13[1], isbn13):
            warn("isbn13", raw13, "repaired", "rebuilt_from_isbn10",
                 "scientific notation; ISBN-13 rebuilt from the valid ISBN in the same row", isbn13)
        else:
            return load_neither("the scientific-notation ISBN-13 does not match the valid ISBN-10; loaded with neither")

    if c10[0] == "empty" and c13[0] == "empty":
        warn("isbn + isbn13", "", "loaded without ISBN", "no_isbn", "no ISBN in either column")

    return isbn10, isbn13, warnings


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def q(name):
    """Quote a column name for SQL."""
    return '"' + name.replace('"', '""') + '"'


def db_columns(header):
    """All CSV columns; isbn becomes isbn10 (rules.md, answer 1)."""
    return ["isbn10" if h == "isbn" else h for h in header]


def open_database(columns):
    conn = sqlite3.connect(DB_PATH)
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='books'").fetchone()
    if not exists:
        defs = ["book_id INTEGER PRIMARY KEY"] + [f"{q(c)} TEXT" for c in columns if c != "book_id"]
        conn.execute(f"CREATE TABLE books ({', '.join(defs)})")
        conn.execute("CREATE UNIQUE INDEX books_isbn13 ON books(isbn13) WHERE isbn13 IS NOT NULL")
    else:
        have = [r[1] for r in conn.execute("PRAGMA table_info(books)")]
        if have != columns:
            conn.close()
            raise ValueError("the file's columns don't match the columns already in books.db")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------

def ingest(csv_path):
    entry = {
        "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "file": os.path.basename(csv_path),
        "file_path": os.path.abspath(csv_path),
        "database": DB_PATH,
        "counts": {"read": 0, "loaded": 0, "updated": 0, "skipped_already_exist": 0,
                   "rejected": 0, "rows_with_warnings": 0},
        "adds_up": True,
        "error": None,
        "rejected_rows": [],
        "warnings": [],
    }
    counts = entry["counts"]

    try:
        f = open(csv_path, newline="", encoding="utf-8-sig")
    except OSError as e:
        entry["error"] = f"could not open the file: {e.strerror}"
        return entry

    with f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            entry["error"] = "the file is empty"
            return entry
        except (csv.Error, UnicodeDecodeError) as e:
            entry["error"] = f"could not read the header line: {e}"
            return entry
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            entry["error"] = f"the file has no column named {', '.join(missing)}"
            return entry

        columns = db_columns(header)
        try:
            conn = open_database(columns)
        except ValueError as e:
            entry["error"] = str(e)
            return entry

        last_line = reader.line_num
        try:
            for fields in reader:
                line = last_line + 1
                last_line = reader.line_num
                if not fields:
                    continue  # a blank line is not a row
                counts["read"] += 1
                process_row(conn, header, columns, fields, line, entry)
        except (csv.Error, UnicodeDecodeError) as e:
            conn.rollback()
            conn.close()
            entry["error"] = f"could not read the file after line {last_line}: {e}; nothing from this run was saved"
            for k in counts:
                counts[k] = 0
            entry["rejected_rows"], entry["warnings"] = [], []
            return entry
        conn.commit()
        conn.close()

    c = counts
    entry["adds_up"] = c["read"] == c["loaded"] + c["updated"] + c["skipped_already_exist"] + c["rejected"]
    return entry


def process_row(conn, header, columns, fields, line, entry):
    counts = entry["counts"]

    def reject(book_id, title, value, reason, action):
        counts["rejected"] += 1
        entry["rejected_rows"].append({"line": line, "book_id": book_id, "title": title,
                                       "value": value, "reason": reason, "action": action})

    # Section 4: rows that are rejected
    if len(fields) != len(header):
        reject(fields[0] if fields else "", "", f"{len(fields)} fields",
               f"wrong number of fields: {len(fields)} instead of {len(header)}",
               f"Check line {line} of the file; the row is broken (for example a missing or extra comma).")
        return
    rec = dict(zip(header, fields))
    book_id, title = rec["book_id"], rec["title"]
    if not re.fullmatch(r"\d+", book_id):
        reject(book_id, title, book_id, "book_id is missing or not a whole number",
               "Ask the supplier for this book's book_id.")
        return
    if title.strip() == "":
        reject(book_id, title, title, "title is empty", f"Ask the supplier for the title of book_id {book_id}.")
        return

    isbn10, isbn13, warnings = clean_isbns(rec["isbn"], rec["isbn13"])

    # Section 3: same ISBN-13 already used by a different book_id
    if isbn13:
        owner = conn.execute("SELECT book_id, title FROM books WHERE isbn13 = ?", (isbn13,)).fetchone()
        if owner and owner["book_id"] != int(book_id):
            warnings.append({"column": "isbn + isbn13", "original": f"{rec['isbn']} | {rec['isbn13']}",
                             "outcome": "ISBN not loaded", "code": "isbn_belongs_to_other_book",
                             "reason": f"ISBN-13 {isbn13} already belongs to book_id {owner['book_id']} "
                                       f"({owner['title']}); loaded without ISBN", "new_value": None})
            isbn10 = isbn13 = None

    values = {col: rec[h] for col, h in zip(columns, header)}
    values["book_id"] = int(book_id)
    values["isbn10"], values["isbn13"] = isbn10, isbn13

    existing = conn.execute("SELECT * FROM books WHERE book_id = ?", (int(book_id),)).fetchone()

    def record_warnings(ws):
        if ws:
            counts["rows_with_warnings"] += 1
            for w in ws:
                entry["warnings"].append({"line": line, "book_id": int(book_id), "title": title, **w})

    if existing is None:
        cols = list(values)
        conn.execute(f"INSERT INTO books ({', '.join(q(c) for c in cols)}) "
                     f"VALUES ({', '.join('?' for _ in cols)})", [values[c] for c in cols])
        counts["loaded"] += 1
        record_warnings(warnings)
        return

    # Section 3: same book_id, different valid ISBN-13
    if isbn13 and existing["isbn13"] and isbn13 != existing["isbn13"]:
        reject(int(book_id), title, isbn13, f"book_id already belongs to a different ISBN ({existing['isbn13']})",
               f"Ask the supplier which ISBN is correct for book_id {book_id}: "
               f"the database has {existing['isbn13']}, the file has {isbn13}.")
        return

    # Section 4: never downgrade an ISBN
    kept = []
    for col in ("isbn10", "isbn13"):
        if values[col] is None and existing[col] is not None:
            values[col] = existing[col]
            kept.append(f"{col} {existing[col]}")
    downgrade_warning = []
    if kept:
        downgrade_warning = [{"column": "isbn + isbn13", "original": f"{rec['isbn']} | {rec['isbn13']}",
                              "outcome": "kept existing ISBN", "code": "kept_existing_isbn",
                              "reason": "the incoming ISBN is empty or unusable; kept the existing " + " and ".join(kept),
                              "new_value": None}]

    changes = {c: v for c, v in values.items() if existing[c] != v}
    if changes:
        conn.execute(f"UPDATE books SET {', '.join(f'{q(c)} = ?' for c in changes)} WHERE book_id = ?",
                     [*changes.values(), int(book_id)])
        counts["updated"] += 1
        record_warnings(warnings + downgrade_warning)
    else:
        # Answers 3 and 4: skipped rows don't repeat ISBN warnings, except a refused downgrade
        counts["skipped_already_exist"] += 1
        record_warnings(downgrade_warning)


# ---------------------------------------------------------------------------
# Log: append, never overwrite earlier runs
# ---------------------------------------------------------------------------

def read_log():
    """Earlier runs. Raises if the log can't be read, so it is never overwritten."""
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        return []
    runs = json.loads(text)
    if not isinstance(runs, list):
        raise ValueError("ingestion-log.json is not a list of runs")
    return runs


def append_to_log(runs, entry):
    runs = runs + [entry]
    tmp = LOG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2, ensure_ascii=False)
    os.replace(tmp, LOG_PATH)


def main():
    if len(sys.argv) != 2:
        print("Usage: python ingest.py <file.csv>")
        return 2
    # Check the log first, so a run is never made that can't be logged.
    try:
        runs = read_log()
    except (OSError, ValueError) as e:  # json.JSONDecodeError is a ValueError
        print(f"ERROR: could not read {LOG_PATH}: {e}")
        print("Nothing was loaded and the log was left untouched. Fix or move the log, then run again.")
        return 1
    entry = ingest(sys.argv[1])
    append_to_log(runs, entry)

    c = entry["counts"]
    print(f"File:     {entry['file']}")
    if entry["error"]:
        print(f"ERROR:    {entry['error']}")
        return 1
    print(f"Read:     {c['read']}")
    print(f"Loaded:   {c['loaded']}")
    print(f"Updated:  {c['updated']}")
    print(f"Skipped:  {c['skipped_already_exist']} (already exist)")
    print(f"Rejected: {c['rejected']}")
    print(f"Rows with warnings: {c['rows_with_warnings']}")
    print("All rows accounted for." if entry["adds_up"] else "WARNING: the counts do not add up!")
    print(f"Log:      {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
