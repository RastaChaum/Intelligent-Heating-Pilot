# Intelligent Heating Pilot v0.5.0-rc.1

Release Candidate 0.5.0-rc.1 introduces optional schedulers, a new preheating control switch, and modernized RC release workflows.

## Major Features

### 🎛️ IHP Enable/Disable Switch ([#77](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/77))
- New per-device switch entity to toggle preheating on/off without losing learned data
- Entity: `switch.intelligent_heating_pilot_<device>_enable_preheating`
- Preserves thermal slope learning across disable/enable cycles
- Full DDD implementation with comprehensive tests

### 📋 Optional Scheduler Support ([#75](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/75))
- Schedulers no longer required; IHP works in standalone calculation mode
- New service: `intelligent_heating_pilot.calculate_anticipated_start_time`
  - **Inputs**: `target_temperature`, `current_temperature`, `outdoor_temperature` (optional)
  - **Outputs**: `anticipated_start_time`, `heating_slope_used`
  - Enables integration with other automation systems
- Configuration UI updated to mark scheduler as optional
- Backward compatible with existing Scheduler-based setups

### 🔄 RC Release Workflow Suite
- New GitHub Actions workflows: prepare, increment, promote
- CLI helper script: `scripts/rc-helper.sh` for safe RC cycle management in production
- Legacy pre-release/release workflows removed to avoid conflicts
- Documentation for the RC process

## Issues Referenced

- [#20](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/20) – Documentation/feature tracking
- [#66](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/66) – Documentation/maintenance tracking

## Pull Requests Merged

- [#77](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/77) – Add switch entity to enable/disable IHP preheating per device
- [#75](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/75) – Make scheduler optional and add service for dynamic heating calculations

## Documentation Updates

- README badges updated to 0.5.0-rc.1
- User guides refreshed with new switch and optional scheduler information
- Release process documentation aligned with RC workflow
- CHANGELOG comprehensive with all feature references

## Installation

Install via HACS custom repository:
```
HACS → Integrations → ⋮ → Custom repositories
→ Add: https://github.com/RastaChaum/Intelligent-Heating-Pilot
→ Search "Intelligent Heating Pilot"
→ Download version 0.5.0-rc.1
→ Restart Home Assistant
```

Or manually:
```bash
git clone https://github.com/RastaChaum/Intelligent-Heating-Pilot.git
cp -r Intelligent-Heating-Pilot/custom_components/intelligent_heating_pilot ~/.homeassistant/custom_components/
# Restart Home Assistant
```

## Testing & Feedback

This is a release candidate intended for community validation. Please:
- Test the new features in your environment
- Report bugs via [Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)
- Share feedback in [Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)

## Upgrade Notes

- Existing configurations remain fully compatible
- New switch entity appears automatically for each IHP device after update
- Scheduler becomes optional; leave empty if using standalone mode
- No configuration changes required unless migrating to standalone mode

---

**Release Date**: 2026-01-20  
**Status**: Release Candidate  
**Next Steps**: Community testing → Final 0.5.0 release

