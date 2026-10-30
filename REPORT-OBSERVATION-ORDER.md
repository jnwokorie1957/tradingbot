# Observation order in reports

New reports select the greatest UTC `observed_at` instant within the existing
Chicago daily/weekly boundaries. Equal instants select the greatest journal
sequence. `last_recorded_snapshot` separately identifies the final in-period
receipt in completion order. Journal records are never reordered or rewritten.

Missing, malformed, non-string or timezone-naive observation timestamps reject
a new report before claiming its period. Such a receipt cannot safely be assigned
to a period and requires explicit reconciliation, not silent omission. Already
committed reports return their original payload unchanged, including legacy reports.

Synthetic tests cover observation/recording disagreement, equal instants with
different offsets, invalid timestamps, idempotent recovery and Chicago boundaries.
No market experiments, strategy promotions, runtime or broker probes are involved.
