# Release v0.4.2 - Performance & UX Improvements

## 🚀 Performance Enhancements

### Incremental Cycle Cache System

This release introduces a major performance improvement for long-term learning capabilities:

- **Reduced Database Load**: Incremental cycle caching drastically reduces Home Assistant recorder queries
- **Extended Retention**: Enables learning from heating cycles beyond HA's native history retention period
- **Smart Deduplication**: Automatic detection and removal of duplicate cycle data
- **Graceful Fallback**: Seamlessly falls back to direct recorder queries if cache is unavailable

**Technical Details:**
- New `CycleCacheData` value object for structured cycle storage
- New `ICycleCache` interface with DDD-compliant abstraction
- `HACycleCache` adapter using HA Store for JSON persistence
- Retention-based automatic pruning
- 28 new unit and integration tests ensuring reliability

## 📚 Documentation Overhaul

Complete redesign of the README for better clarity and user experience:

- **60% Size Reduction**: From ~300 to ~120 lines
- **Eliminated Redundancies**: Removed duplicated content from dedicated docs
- **Improved Flow**: Natural chapter progression and clearer call-to-action
- **Visual Clarity**: Less clutter, more breathing room
- **Version Consistency**: Fixed outdated version references (0.3.0 → 0.4.2)
- **Concrete Examples**: Added visual example of what IHP does
- **Better Navigation**: Clear documentation table for all user types

## 📋 What's Changed

### Added
- Incremental cycle cache system with comprehensive test coverage
- Improved README with modern, user-friendly structure

### Changed
- README structure completely redesigned for clarity
- Version references updated throughout documentation

## 🔗 Full Changelog

See [CHANGELOG.md](https://github.com/RastaChaum/Intelligent-Heating-Pilot/blob/v0.4.2/CHANGELOG.md) for complete details.

---

**Installation**: Via HACS or [manual download](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/tag/v0.4.2)

**Documentation**: [User Guide](https://github.com/RastaChaum/Intelligent-Heating-Pilot/blob/v0.4.2/docs/USER_GUIDE.md) | [Installation](https://github.com/RastaChaum/Intelligent-Heating-Pilot/blob/v0.4.2/docs/INSTALLATION.md) | [Configuration](https://github.com/RastaChaum/Intelligent-Heating-Pilot/blob/v0.4.2/docs/CONFIGURATION.md)
