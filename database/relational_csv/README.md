# `database/relational_csv/`

Hand-maintained mapping tables for identity / clubs / venues.

| File | Purpose |
|------|---------|
| `club_mapping.csv` | Alias → **canonical Club** (durable). Edited via Diagnose `/diagnose/validierung/clubs` or by hand. |
| `venue_mapping.csv` | Alias → **canonical bowling center** (durable). Applied during league extract/merge on `Location`. |
| `rangliste_club_crosswalk.csv` | Optional Rangliste club label → league Club |

Registry builds (`clubs_registry`, publish) **fold** `club_mapping.csv` in; they do not replace this file.

Operator flow: [`../../docs/DATA_PIPELINE.md`](../../docs/DATA_PIPELINE.md).
