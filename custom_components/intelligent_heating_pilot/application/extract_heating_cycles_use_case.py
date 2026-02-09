"""Use case for extracting heating cycles with lifecycle management.

Orchestrates heating cycle extraction with:
- Initial extraction on startup
- Periodic 24h refresh
- Configuration change handling
- Timer lifecycle management
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable

from homeassistant.util import dt as dt_util

from ..domain.interfaces.device_config_reader_interface import DeviceConfig
from ..domain.interfaces.heating_cycle_service_interface import IHeatingCycleService
from ..domain.value_objects import HistoricalDataKey, HistoricalDataSet
from ..domain.value_objects.heating import HeatingCycle

if TYPE_CHECKING:
    from ..domain.interfaces import (
        ICycleCache,
        IHistoricalDataAdapter,
        ITimerScheduler,
    )

_LOGGER = logging.getLogger(__name__)

REFRESH_INTERVAL_HOURS = 24


class ExtractHeatingCyclesUseCase:
    """Orchestrate heating cycle extraction with lifecycle management.

    Responsibilities:
    - Extract cycles from HA recorder via injected adapters
    - Initialize and manage 24h periodic refresh timer
    - React to retention configuration changes
    - Handle cache lifecycle (init, incremental updates, pruning)

    Uses domain service (IHeatingCycleService) to extract cycles,
    orchestrates infrastructure adapters (IHistoricalDataAdapter[]).
    """

    def __init__(
        self,
        device_config: DeviceConfig,
        heating_cycle_service: IHeatingCycleService,
        historical_adapters: list[IHistoricalDataAdapter],
        cycle_cache: ICycleCache | None = None,
        timer_scheduler: ITimerScheduler | None = None,
    ) -> None:
        """Initialize with injected dependencies.

        Args:
            device_config: Device configuration
            heating_cycle_service: Domain service for cycle extraction logic
            historical_adapters: List of adapters (Climate, Sensor, etc.)
              implementing IHistoricalDataAdapter
            cycle_cache: Optional cache for incremental updates
            timer_scheduler: Optional timer for 24h refresh scheduling
        """
        _LOGGER.debug("Initializing ExtractHeatingCyclesUseCase")

        self._device_config = device_config
        self._cycle_service = heating_cycle_service
        self._adapters = historical_adapters
        self._cache = cycle_cache
        self._timer_scheduler = timer_scheduler

        self._refresh_cancel: Callable[[], None] | None = None
        self._device_id: str | None = None
        self._current_retention_days: int | None = None

    async def execute(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[HeatingCycle]:
        """Extract cycles and initialize refresh timer.

        This is the ENTRY POINT for all extraction (initial, reconfiguration, etc).

        Args:
            device_id: Device identifier
            start_time: Extraction window start
            end_time: Extraction window end

        Returns:
            Extracted heating cycles
        """
        _LOGGER.debug(
            "Entering ExtractHeatingCyclesUseCase.execute: device_id=%s, window=%s to %s",
            device_id,
            start_time,
            end_time,
        )

        self._device_id = device_id
        # Calculate retention days from time window, don't reload from config
        # (allows on_retention_changed to update retention before calling execute)
        if not self._current_retention_days:
            self._current_retention_days = (end_time - start_time).days

        try:
            # STEP 1: Fetch historical data via injected adapters
            historical_data_set = await self._fetch_combined_historical_data(
                device_id, start_time, end_time
            )

            # STEP 2: Extract cycles using domain service
            # Get device config for cycle split parameter

            cycles = await self._cycle_service.extract_heating_cycles(
                device_id=device_id,
                history_data_set=historical_data_set,
                start_time=start_time,
                end_time=end_time,
                cycle_split_duration_minutes=self._device_config.cycle_split_duration_minutes,
            )

            _LOGGER.info(
                "Extracted %d heating cycles for device=%s (window: %d days)",
                len(cycles),
                device_id,
                self._current_retention_days,
            )

            # STEP 3: Append to cache with retention metadata
            if self._cache:
                await self._cache.append_cycles(
                    device_id=device_id,
                    new_cycles=cycles,
                    search_end_time=end_time,
                    retention_days=self._current_retention_days,
                )

            # STEP 4: Schedule periodic 24h refresh (if not already scheduled)
            if self._timer_scheduler and not self._refresh_cancel:
                await self._schedule_periodic_refresh()

            _LOGGER.debug("Exiting ExtractHeatingCyclesUseCase.execute")
            return cycles

        except Exception as exc:
            _LOGGER.warning(
                "Failed to extract cycles for device=%s: %s",
                device_id,
                exc,
            )
            return []

    async def _fetch_combined_historical_data(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> HistoricalDataSet:
        """Fetch and combine historical data from all adapters.

        ORCHESTRATION: Calls each IHistoricalDataAdapter and combines results.

        Args:
            device_id: Device identifier (vtherm entity ID)
            start_time: Window start
            end_time: Window end

        Returns:
            Combined HistoricalDataSet
        """
        _LOGGER.debug(
            "Fetching combined historical data from %d adapters",
            len(self._adapters),
        )

        combined_data: dict[HistoricalDataKey, list] = {}

        # Fetch climate data (indoor temp, target temp, heating state)
        # These use the device_id which maps to the vtherm entity
        for key in [
            HistoricalDataKey.INDOOR_TEMP,
            HistoricalDataKey.TARGET_TEMP,
            HistoricalDataKey.HEATING_STATE,
        ]:
            try:
                # Find adapter that can handle climate data
                # (assume first adapter is ClimateDataAdapter by convention)
                adapter = self._adapters[0]

                result = await adapter.fetch_historical_data(
                    device_id,
                    key,
                    start_time,
                    end_time,
                )
                combined_data.update(result.data)

                await asyncio.sleep(0.1)  # Yield to event loop

            except Exception as exc:
                _LOGGER.warning(
                    "Failed to fetch %s: %s",
                    key,
                    exc,
                )

        # Fetch optional sensor data (humidity, etc.)
        for key, entity_id_attr in [
            (HistoricalDataKey.INDOOR_HUMIDITY, "humidity_in_entity_id"),
            (HistoricalDataKey.OUTDOOR_HUMIDITY, "humidity_out_entity_id"),
        ]:
            try:
                entity_id = getattr(self._device_config, entity_id_attr, None)

                if not entity_id:
                    continue

                # Find adapter that can handle sensors
                # (assume second adapter is SensorDataAdapter by convention)
                if len(self._adapters) > 1:
                    adapter = self._adapters[1]
                    result = await adapter.fetch_historical_data(
                        entity_id,
                        key,
                        start_time,
                        end_time,
                    )
                    combined_data.update(result.data)

                await asyncio.sleep(0.1)  # Yield to event loop

            except Exception as exc:
                _LOGGER.warning(
                    "Failed to fetch %s: %s",
                    key,
                    exc,
                )

        _LOGGER.debug(
            "Successfully fetched combined historical data with %d keys",
            len(combined_data),
        )
        return HistoricalDataSet(data=combined_data)

    async def _schedule_periodic_refresh(self) -> None:
        """Schedule 24h periodic refresh timer."""
        _LOGGER.debug("Scheduling periodic 24h refresh")

        if not self._timer_scheduler:
            _LOGGER.warning("No timer scheduler available, cannot schedule refresh")
            return

        now = dt_util.utcnow()
        next_refresh = now + timedelta(hours=REFRESH_INTERVAL_HOURS)

        try:
            self._refresh_cancel = self._timer_scheduler.schedule_timer(
                next_refresh,
                self._perform_periodic_refresh,
            )

            _LOGGER.info(
                "Refresh timer scheduled for %s (device=%s)",
                next_refresh.isoformat(),
                self._device_id,
            )
        except Exception as exc:
            _LOGGER.warning(
                "Failed to schedule refresh timer: %s",
                exc,
            )

    async def _perform_periodic_refresh(self) -> None:
        """Periodic callback: extract last 24h cycles and reschedule."""
        _LOGGER.debug("Entering _perform_periodic_refresh")

        if not self._device_id or not self._current_retention_days:
            _LOGGER.warning("Device ID or retention days not set, cannot refresh")
            return

        now = dt_util.utcnow()
        refresh_start = now - timedelta(hours=REFRESH_INTERVAL_HOURS)

        try:
            # Fetch incremental data (last 24h)
            historical_data_set = await self._fetch_combined_historical_data(
                self._device_id,
                refresh_start,
                now,
            )

            # Extract cycles

            new_cycles = await self._cycle_service.extract_heating_cycles(
                device_id=self._device_id,
                history_data_set=historical_data_set,
                start_time=refresh_start,
                end_time=now,
                cycle_split_duration_minutes=self._device_config.cycle_split_duration_minutes,
            )

            _LOGGER.info(
                "Periodic refresh: extracted %d cycles for device=%s",
                len(new_cycles),
                self._device_id,
            )

            # Append to cache (incremental, dedup by cache)
            if self._cache:
                await self._cache.append_cycles(
                    device_id=self._device_id,
                    new_cycles=new_cycles,
                    search_end_time=now,
                    retention_days=self._current_retention_days,
                )

                # Prune old cycles
                await self._cache.prune_old_cycles(self._device_id, now)

        except Exception as exc:
            _LOGGER.warning(
                "Periodic refresh failed: %s",
                exc,
            )

        # Reschedule next refresh
        await self._schedule_periodic_refresh()

        _LOGGER.debug("Exiting _perform_periodic_refresh")

    async def on_retention_changed(self, new_retention_days: int) -> None:
        """React to retention configuration change.

        Called by Coordinator when user reconfigures retention.
        Handles cache re-initialization if needed.

        Args:
            new_retention_days: New retention in days (0 = disabled)
        """
        _LOGGER.debug(
            "Entering on_retention_changed: new_retention=%d, current=%s",
            new_retention_days,
            self._current_retention_days,
        )

        if not self._device_id:
            _LOGGER.warning("Device ID not set, cannot handle retention change")
            return

        # If retention disabled (0 days)
        if new_retention_days == 0:
            await self.cancel()
            if self._cache:
                await self._cache.clear_cache(self._device_id)
            self._current_retention_days = 0
            _LOGGER.info(
                "Cycle extraction disabled for device=%s (retention=0)",
                self._device_id,
            )
            return

        # If retention changed to different value
        if new_retention_days != self._current_retention_days:
            _LOGGER.info(
                "Retention reconfigured for device=%s: %d → %d days",
                self._device_id,
                self._current_retention_days or 0,
                new_retention_days,
            )

            # Clear old cache
            if self._cache:
                await self._cache.clear_cache(self._device_id)

            # Cancel current timer
            await self.cancel()

            # Update retention days BEFORE re-extract (so execute() uses new value)
            self._current_retention_days = new_retention_days

            # Re-extract on new window
            now = dt_util.utcnow()
            await self.execute(
                device_id=self._device_id,
                start_time=now - timedelta(days=new_retention_days),
                end_time=now,
            )

        _LOGGER.debug("Exiting on_retention_changed")

    async def cancel(self) -> None:
        """Cancel refresh timer and cleanup."""
        _LOGGER.debug("Cancelling periodic refresh timer")

        if self._refresh_cancel:
            self._refresh_cancel()
            self._refresh_cancel = None
            _LOGGER.info("Refresh timer cancelled for device=%s", self._device_id)
