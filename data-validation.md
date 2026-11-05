# Data validation: ISBNs in books.csv and books-batch2.csv

This is a diagnosis only. Neither file was changed and nothing was fixed. Both files were checksummed before and after the checks and are byte-for-byte identical.

| File | Rows | What it is |
|---|---|---|
| books.csv | 10,000 | First delivery (Goodbooks-10k, same as Module 2) |
| books-batch2.csv | 31 | Second delivery, one week later, same supplier |

## How "valid" was decided

The rules come from the International ISBN Agency's *ISBN Users' Manual* (7th edition):

- **ISBN-13**: exactly 13 digits, starting with the GS1 prefix **978 or 979**. The last digit is the **check digit**. Multiply the 13 digits alternately by 1 and 3 and add them up. The total must divide evenly by 10. Since 1 January 2007, only 13-digit ISBNs are issued.
- **ISBN-10**: the older format, used before 2007. It has 9 digits plus a check character that is **0–9 or X** (X means 10). Multiply the 10 characters by 10, 9, 8 … 1 and add them up. The total must divide evenly by 11. Every ISBN-10 has an ISBN-13 twin: add `978` in front of the first 9 digits and recompute the check digit.
- **Hyphens and spaces** are only for display. The manual says they carry no meaning, and the stored ISBN is the digits alone.

A value is called **valid** only if it passes these rules **exactly as written in the file**. A value that would pass after a change, such as adding zeros or removing hyphens, is listed as a problem, with a note on whether the change gets the real ISBN back for certain or is only a guess.

Valid means "could be a real ISBN", not "is this book's ISBN". A typo can still produce a value with a correct check digit about 1 time in 10.

---

## books.csv: `isbn` column (ISBN-10)

| Kind | Rows | Example (book_id → value) | What is wrong | Is the real ISBN still there? |
|---|---:|---|---|---|
| ✅ Valid ISBN-10 | 2,690 | 18 → `043965548X` | Nothing | — |
| Leading zeros dropped (1 zero) | 5,563 | 1 → `439023483` (should be `0439023483`) | Only 9 digits | **Yes.** Adding the zero back gives a value that passes the check digit. |
| Leading zeros dropped (2 zeros) | 913 | 4 → `61120081` (should be `0061120081`) | Only 8 digits | **Yes**, same as above |
| Leading zeros dropped (3 zeros) | 111 | 69 → `7442912` (should be `0007442912`) | Only 7 digits | **Yes**, same as above |
| Too short **and** wrong check digit | 14 | 916 → `812971060` (padded `0812971060` still fails) | Missing zeros and the check digit doesn't match | **No.** Padding doesn't fix it; at least one digit is wrong. |
| 10 digits, wrong check digit: actually an ISBN-13 with `978` cut off | 8 | 2778 → `1416913184` (`978` + it = `9781416913184`, a valid ISBN-13) | It's not an ISBN-10 at all. It's the last 10 digits of an ISBN-13. | **Yes**, as the ISBN-13 `978` + value, but it's an inference |
| 10 digits, wrong check digit (no explanation found) | 1 | 4322 → `1400139027` | Check digit doesn't match | **No** |
| Empty | 700 | 106 (*Bossypants*) → `` | No value | — |

**Probable causes**
- **Dropped leading zeros (6,587 rows, 66%).** The column was treated as a number by a spreadsheet or script, and numbers can't start with 0. Evidence: all 814 values ending in **X** kept their leading zeros, because a value containing a letter can't become a number, so it stayed as text.
- **ISBN-13 with 978 cut off.** Someone "converted" ISBN-13 to ISBN-10 by deleting `978`, without recalculating the check digit.
- **Wrong digits.** Data-entry errors at the source.

## books.csv: `isbn13` column (ISBN-13)

**No row contains a valid ISBN-13 as written.**

| Kind | Rows | Example (book_id → value) | What is wrong |
|---|---:|---|---|
| Scientific notation | 9,410 | 1 → `9.78043902348e+12` | The number was rounded to 12 significant digits. The **13th digit (the check digit) is gone**, and the 12th digit was rounded. |
| ↳ of which prefix 978 or 979 | 9,382 | | Would be an ISBN if complete |
| ↳ of which **not an ISBN at all** | 28 | 1165 → `2.94001623192e+12` (prefix 294); 2894 → `6.45573003012e+11` (12 digits) | These are other product barcodes: 22 with prefix 294, 3 UPC codes, 2 with prefix 622, 1 with prefix 123 |
| Decimal number, not 13 digits | 5 | 958 → `76783609419.0` | 3 are UPC barcodes with the leading 0 dropped (`076783609419` passes the UPC check). 1 is a truncated ISBN-13 (1443 → `97893806587.0`, 2 digits missing). 1 is the ISBN-10 copied into this column (8174 → `195170342.0`). |
| Empty | 585 | 106 → `` | No value |

**Is the information still there or lost?** Partly. Rounding to 12 digits loses the check digit. It also rounds the 12th digit **up** whenever the lost check digit was 5–9, which happened in about half the rows.

| Situation | Rows | Can the real ISBN-13 be rebuilt? |
|---|---:|---|
| Row has a valid ISBN-10 (after adding zeros) that matches the rounded value | 9,238 | **Yes, exactly.** Convert the ISBN-10 to ISBN-13. In 4,689 of these, the 12th digit shown is off by one because of rounding, so copying the digits as shown would be wrong. |
| Valid ISBN-10, but the rounded ISBN-13 belongs to something else | 16 | The two columns describe **different products** (e.g. 1106: ISBN-10 `0006280560` but ISBN-13 starts `979000767…`). You can't tell which one is the book. |
| No usable ISBN-10, and only one ISBN-13 fits the rounding | 55 | Yes, mathematically (e.g. 260 → `9780671723651`) |
| No usable ISBN-10, and **two** ISBN-13s fit | 99 | **No. A repair would be a guess.** E.g. 799 `9.7804251888e+12` could be `9780425188804` or `9780425188798`. |
| No usable ISBN-10, and no ISBN-13 fits | 2 | No |

**Rounding makes different books look the same.** 262 rounded values are shared by two or more different books. For example, `9.78006112008e+12` appears on both book 4 (*To Kill a Mockingbird*) and book 265. Matching books on the `isbn13` text as written would merge different books.

**Probable cause:** a spreadsheet or script read the column as a number and wrote it back in scientific notation.

## books.csv: both columns together

| | Rows |
|---|---:|
| Both empty: no ISBN of any kind | 565 |
| `isbn` empty, `isbn13` present (always the rounded value) | 135 |
| `isbn` present, `isbn13` empty | 20 |
| Both present | 9,280 |

---

## books-batch2.csv: `isbn` column (ISBN-10)

| Kind | Rows | book_id → value | What is wrong | Is the real ISBN still there? |
|---|---:|---|---|---|
| ✅ Valid ISBN-10 | 12 | 24 → `0439139600` | Nothing | — |
| Leading zeros dropped | 7 | 1 → `439023483`; 4 → `61120081` | Same as books.csv | **Yes** |
| Lowercase `x` | 1 | 10004 → `031200009x` | The check character must be uppercase `X` | **Yes.** Uppercase gives a valid ISBN that matches its `isbn13` (`9780312000097`). |
| Hyphens | 1 | 10002 → `0-450-19827-8` | Display hyphens stored in the data | **Yes.** Without them it's valid and matches its `isbn13`. |
| Spaces, including before and after | 1 | 10003 → `␣162 001 4750␣` | Spaces inside and around the value | **Yes.** Without them it's valid and matches its `isbn13`. |
| ISBN-13 in the ISBN-10 column | 1 | 10014 → `9781982147600` | Wrong column. It is a **valid ISBN-13**, and `isbn13` is empty. | **Yes**, the value is fine; it's in the wrong column |
| Wrong check digit | 1 | 10007 → `1854433017` | A correct check digit would be `6`, not `7`. `isbn13` is empty. | **No.** Either the last digit or an earlier digit is wrong, and nothing says which. |
| Wrong length (11 digits) | 1 | 10009 → `15287463097` | One digit too many | **No.** Deleting the last digit gives `1528746309`, which is a different book's ISBN (10001, *The Lantern Keeper's Daughter*). |
| Letter in the middle | 1 | 10008 → `04390A3483` | Only the last character may be a letter | **No.** It is one character away from `0439023483` (*The Hunger Games*), so "fixing" it would clash with another book. |
| Empty | 5 | 106, 25, 10005, 10006, 10010 | No value | — (10005 and 10006 have a valid `isbn13`) |

## books-batch2.csv: `isbn13` column (ISBN-13)

| Kind | Rows | book_id → value | Note |
|---|---:|---|---|
| ✅ Valid ISBN-13 | 9 | 24 → `9780439139601` | Batch 2 has proper 13-digit text in some rows, unlike books.csv |
| ↳ valid, prefix **979** | 1 | 10006 → `9798351220413` | Correct. A 979 ISBN has no ISBN-10 twin, so the empty `isbn` is expected, not an error. |
| ↳ valid, but **disagrees with its own ISBN-10** | 1 | 10011: `isbn` `1555550126` → `9781555550127`, but `isbn13` is `9781555550134` | Both pass their check digits on their own, but they can't both be this book's ISBN. Nothing says which is right. |
| Scientific notation | 14 | 132 → `9.78140130858e+12` | Same problem as books.csv. All 14 match a valid ISBN-10 in the same row, so all are exactly rebuildable. In 2, the 12th digit was rounded up. |
| Empty | 8 | 106, 25, 10007, 10008, 10009, 10010, 10013, 10014 | |

---

## Row problems in batch 2 that will matter when loading

These go beyond single ISBN values, but they decide what "the same book" means in Part 3.

1. **Exact duplicate row.** book_id 10001 (*The Lantern Keeper's Daughter*) appears twice, identical.
2. **Two different books share one ISBN.** 10013 *Paper Moons* (Georgia Tran) has ISBN-10 `1416524797`, which is the ISBN of book 9, *Angels & Demons* (Dan Brown), in both files. At least one of them is wrong, most likely the new book.
3. **Book with no identifier and placeholder data.** 10010 has the title "Untitled Manuscript", the author "Unknown", and no ISBN in either column.
4. **Rounded ISBN-13 shared across files.** Batch2 rows 4 and 134 have the same rounded `isbn13` text as different books in books.csv (265 and 153).
5. **16 rows are books already in books.csv, matched by book_id. 15 rows (14 books) are new.** Of the 16 existing books:

| What changed compared with books.csv | book_ids |
|---|---|
| Nothing | 1, 2, 3, 4, 9, 11, 18, 34, 46, 106 |
| Only rating counts went up | 13, 14, 132, 134 |
| ISBNs are now **correct**: zero kept, full 13 digits | 24 (`0439139600`, `9780439139601`) |
| ISBNs are now **missing**: both were present before | 25 (*Harry Potter and the Deathly Hallows*) |

The new books use book_ids 10001–10014, starting after the last Goodbooks id. They look like made-up titles added for this exercise.

---

## Summary of problem kinds

| # | Problem | books.csv | batch 2 | Real ISBN recoverable? |
|---|---|---:|---:|---|
| 1 | Leading zeros dropped from ISBN-10 | 6,587 | 7 | Yes, certain (check digit confirms) |
| 2 | ISBN-13 in scientific notation | 9,410 | 14 | Only if there's a matching ISBN-10. Otherwise sometimes, sometimes a guess. |
| 3 | Non-ISBN barcodes in `isbn13` (UPC, prefix 294/622/123) | 31 | 0 | Not an ISBN |
| 4 | ISBN-13 with `978` cut off, stored as ISBN-10 | 8 | 0 | Yes, but it's an inference |
| 5 | Wrong check digit, cause unknown | 15 | 1 | No |
| 6 | Truncated ISBN-13 | 1 | 0 | No |
| 7 | ISBN-10 copied into `isbn13` | 1 | 0 | Yes (as an ISBN-10, once the zero is restored) |
| 8 | Lowercase `x` | 0 | 1 | Yes, certain |
| 9 | Hyphens or spaces | 0 | 2 | Yes, certain |
| 10 | ISBN-13 in the ISBN-10 column | 0 | 1 | Yes, certain |
| 11 | Wrong length (extra digit) | 0 | 1 | No; the obvious fix collides with another book |
| 12 | Letter in the middle | 0 | 1 | No; the obvious fix collides with another book |
| 13 | ISBN-10 and ISBN-13 refer to different items | 16 | 1 | No; can't tell which is right |
| 14 | No ISBN in either column | 565 | 3 | — |
| 15 | Same ISBN on two different books | 0* | 1 | — |
| 16 | Duplicate row | 0 | 1 | — |

\* None once ISBNs are rebuilt correctly. 262 if the rounded `isbn13` text is compared as written.
