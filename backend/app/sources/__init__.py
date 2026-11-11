"""External open-data sources (INSEE, Éducation nationale, OpenStreetMap, DLR WSF, Microsoft footprints, Sentinel-2…).

Every source degrades gracefully: on timeouts or HTTP errors it falls back to the
last cached copy (or the bundled reference snapshot) and records why in the
source health board, so an analysis never crashes on a network failure.
"""
