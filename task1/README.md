# Task 1 — pharmacy identity and revenue explorer

## Problem and sources

This solution creates one master record per row in `pharmacy_registry.csv`, then maps supplier account names and ERP invoice headers to that master where evidence is sufficient. The sources are the registry, four-area reference, 83 supplier branches, 14,953 supplier accounts, and APP, ERP, and LEGACY invoice headers/details.

The generated site reads `output/analytics.json`; it does not contain dashboard constants.

## Data model and identity policy

`pharmacy_id` is the registry ID. Supplier identities retain account name, supplier branch, supplier customer code, match status, method, score, and evidence. Exact normalized names are preferred; fuzzy matching is accepted only with a strong score and a clear brand-token/branch disambiguation. Location text is not treated as definitive identity evidence. Unresolved or competing candidates remain `UNMATCHED` or `AMBIGUOUS`.

There are 38 supplier companies, 83 branches, 14,953 supplier accounts, and 1,826 master pharmacies. The current generated run maps 1,720 accounts, leaves 2,702 accounts ambiguous and 10,531 strictly unmatched. These are disjoint statuses and sum to 14,953. ERP matching is reported separately because invoice headers may use names absent from the supplier naming book.

## Area recovery

Registry area is used as the final area when present, but invoice evidence is retained for comparison. A registry/invoice disagreement is marked `registry_conflict` with `conflict` confidence rather than being presented as uncontested high confidence. For missing areas, only ERP header area, ERP account address, and ERP delivery address are used; pharmacy-name suffixes are intentionally not used as proof. Evidence is weighted by reliability (header 3, account address 2, delivery address 1). A close vote is ambiguous. Area values are constrained to `areas_reference.csv`.

## Revenue definition

The ledger has one row per invoice header that survives the source-specific rules. Revenue uses summed detail-line amounts when detail exists, otherwise the header total. APP includes only `paid` and `shipped`; canceled and pending-hold orders are excluded. ERP includes matched pharmacy invoices with a valid date and positive reconciled amount; both `CLSD` and blank `record_state` are treated as source-valid because the data provides no contrary completion semantics. LEGACY includes parseable `P:<pharmacy_id>` documents; `CR` rows remain negative and therefore reduce revenue. The window is inclusive: 2024-09-01 through 2026-08-26.

No invoice header is duplicated in the input. Detail rows are line items, so repeated invoice IDs are expected and are aggregated, not deduplicated. The pipeline records every exclusion and its row/money impact in `output/revenue_stats.json`. Unmatched ERP invoice rows are excluded from the trusted revenue ledger and are displayed with their unmatched revenue separately.

## Validation and running

`run.bat` selects an installed local Python interpreter, verifies pandas/Flask/rapidfuzz without network access, clears generated output files, validates the manifest row counts/hashes, runs identity resolution, area recovery, ledger construction, output invariants, and starts the local website. If the required offline packages are absent it stops with an actionable message rather than making a network call.

Validation checks include unique master IDs, valid entity links, valid reference areas, valid dates, disjoint and complete matched/ambiguous/unmatched alias partitions, unique source invoice rows, finite revenue, and output reconciliation. Unknown and ambiguous area outputs are separated into `output/unknown_areas.csv` and `output/ambiguous_areas.csv`. The input manifest currently has matching row counts but its byte hashes do not match these files (including after BOM/newline normalization); this is retained as a visible input-integrity warning. The pipeline does not silently present that warning as a successful hash check.

## Known limitations

Most ERP account names have no sufficiently defensible mapping to a unique registry pharmacy, so the unmatched population is large by design. Supplier branch area is contextual evidence only and is not automatically treated as a pharmacy location. The dashboard labels invoice rows/counts explicitly and keeps global data-quality counts separate from date-filtered financial rankings.
