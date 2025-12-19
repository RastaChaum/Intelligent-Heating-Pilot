# Release v0.4.1 - LHS Cache TTL and Docs Update

## ✨ Changes

- Added/Clarified 24-hour TTL caching for both **Global Learned Heating Slope (LHS)** and **Contextual LHS (per hour)**.
  - Contextual cache refresh occurs on-demand during anticipation calculation when stale/missing.
  - Recomputes LHS from recent heating cycles (lookback window), then updates both caches.
  - If no cycles are available, reuses fresh cached global LHS or falls back to persisted value.
- Documentation updated:
  - `docs/HOW_IT_WORKS.md`: Added detailed section describing global/contextual LHS caches, TTL behavior, on-demand refresh, and lookback inclusion.
  - `README.md`: Added summary note about LHS caches and on-demand refresh behavior.
- Version bump to `0.4.1` in manifests and README badge.

## 🔧 Notes

- No breaking changes.
- Automation will create a pre-release for `v0.4.1` and use these notes.

