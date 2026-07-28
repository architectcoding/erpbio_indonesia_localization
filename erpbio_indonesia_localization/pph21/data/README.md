# PPh 21 statutory rate data

`pph21_rates.json` holds every statutory table the PPh 21 calculator needs. **No figure in it was
typed by hand.** It was machine-extracted from the regulation, validated, and reconciled against an
independent transcription before being committed.

## Provenance

| Table | Source | Rows |
| --- | --- | --- |
| TER Bulanan A / B / C | DJP **PMK 168/2023**, pp. 10–12 | 44 / 40 / 41 |
| TER Harian | DJP PMK 168/2023, p. 9 | 2 |
| PTKP per status (+ TER category) | DJP PMK 168/2023, pp. 9 · 10–12 · 17 (stated 3×, consistent) | 8 |
| Pasal 17 ayat (1) huruf a | DJP PMK 168/2023, p. 8 | 5 |

Primary source: <https://pajak.go.id/sites/default/files/2024-02/PMK%20168%20Tahun%202023%20Tentang%20PPh%20Pasal%2021%20TER.pdf>
(SHA-256 `1a047860d3fe9d01b737fce2349816fb…`, 3,067,979 bytes). Chosen over the PP 58/2023 scan on
peraturan.bpk.go.id because it is born-digital — real `%`, no OCR damage.

Legal basis: UU HPP No. 7/2021 → PP 58/2023 → PMK 168/2023, with PER-11/PJ/2025 governing the
Coretax-era bukti potong. Effective **2024-01-01**; confirmed unchanged for 2026.

## How it was validated

Every table had to pass, before being written:

- **row count** against the regulation's own structure (44 / 40 / 41 / 2 / 8 / 5);
- **row numbering** — the PDF numbers its bands, so they must run 1..N with no gaps;
- **contiguity** — each band starts one rupiah after the previous ends;
- **monotonicity** — rates never fall as income rises;
- **range** — 0 ≤ rate ≤ 100;
- **PTKP ladder** — 54m + 4.5m per step, exactly;
- **Pasal 17 digits vs words** — the PDF states every amount twice ("Rp60.000.000,00 (enam puluh
  juta rupiah)"), so both forms were parsed independently and had to agree.

The same checks run at runtime via `pph21.tables.validate_tables()`.

## What the checks caught

Worth recording, because it is the argument for not hand-typing tax tables:

1. A widely-published transcription of **TER C band 7** gives **2.0%**; the regulation says **1.5%**.
   The monotonicity check flagged it as impossible (rates ran 1.25 → 2.0 → 1.75) *before* the sources
   were compared, and PMK 168 independently confirmed 1.5%.
2. The extractor initially **dropped the top band** of all three monthly tables — the PDF writes it
   `lebih` ("more than"), not `di atas`. The row-count check caught it.
3. `lebih X` is **exclusive**, so the top band overlapped the one below it. The contiguity check
   caught that.

Aside from item 1, the independent transcription agreed with the regulation on **124 of 125** bands.

## Changing it

Prefer adding rows with a **later `effective_from`** over editing these — the lookups resolve by date,
so history stays intact and a future rate change is data rather than a code change.

`setup_eil` reloads this file on every migrate, but it is **additive only**: it never overwrites a row
an administrator has corrected. It also never ticks `tables_verified` — a human has to look at the
numbers and say so, and until they do, PPh 21 refuses to compute.
