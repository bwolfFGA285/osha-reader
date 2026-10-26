# OSHA General Industry Reader

A free, mobile-friendly reader for OSHA's general industry regulations:

- Full official text of **29 CFR 1910** (General Industry) and **29 CFR 1904** (Recordkeeping)
- Plain-language summaries in **English, Chinese and Spanish** for commonly used sections
- Keyword and full-text search ("forklift", "LOTO", "SDS", "1910.147")
- **What's New**: OSHA rule changes affecting Parts 1910 and 1904, with compliance dates
- **Saved**: bookmark sections (stored on each person's own device)

The regulation text refreshes automatically every week from the official eCFR.

Chinese and Spanish summaries are unofficial translations. The English regulation text is the legal requirement. This site is not affiliated with OSHA or the U.S. Department of Labor.

## Files

| File | What it is |
|---|---|
| `index.html` | The app |
| `data/s/*.json` | Official text, one file per section (generated, don't edit) |
| `data/index.json`, `data/search.json` | Table of contents and search index (generated, don't edit) |
| `data/summaries.json` | Plain-language summaries. Edit to add or change summaries |
| `data/news.json` | What's New entries. Edit to add rule changes |
| `tools/update.py`, `tools/convert.py` | Scripts the weekly job runs |
| `.github/workflows/weekly-update.yml` | The weekly job |

## How updates work

Every Monday morning a GitHub Action:

1. Downloads the latest text of Parts 1910 and 1904 from eCFR and saves any changes. The site updates on its own a minute or two later.
2. Checks the Federal Register for new OSHA notices on Parts 1910 or 1904. If it finds any that aren't in What's New yet, it opens an **Issue** in this repository listing them, so someone can add them to `data/news.json`.

You can also run it any time: **Actions** tab › **Weekly OSHA update** › **Run workflow**.

Sources: [eCFR](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XVII/part-1910) and the [Federal Register](https://www.federalregister.gov/agencies/occupational-safety-and-health-administration). Regulation text is a U.S. government work in the public domain.
