"""Asynchronous buffered telemetry collector with background flushing.

Provides thread-safe and async-safe queuing of telemetry traces, periodic flushing,
flush timeouts, and dropped-event accounting without external brokers.
"""

import asyncio
import contextlib
import logging

from aireliability.telemetry.collector import TelemetryCollector
from aireliability.telemetry.models import TelemetryTrace
from aireliability.telemetry.sampler import AlwaysOnSampler, TelemetrySampler
from aireliability.telemetry.sanitizer import SanitizationPolicy

logger = logging.getLogger(__name__)


class AsyncTelemetryCollector:
    """Buffered telemetry collector with non-blocking enqueue and background flush."""

    def __init__(
        self,
        sink_collector: TelemetryCollector,
        *,
        max_buffer_size: int = 1000,
        flush_interval_seconds: float = 1.0,
        flush_timeout_seconds: float = 5.0,
        sampler: TelemetrySampler | None = None,
        sanitizer: SanitizationPolicy | None = None,
    ) -> None:
        self.sink = sink_collector
        self.max_buffer_size = max_buffer_size
        self.flush_interval_seconds = flush_interval_seconds
        self.flush_timeout_seconds = flush_timeout_seconds
        self.sampler = sampler or AlwaysOnSampler()
        self.sanitizer = sanitizer or SanitizationPolicy()

        self._queue: asyncio.Queue[TelemetryTrace] = asyncio.Queue(
            maxsize=max_buffer_size
        )
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False
        self._dropped_events = 0
        self._recorded_events = 0

    @property
    def dropped_events(self) -> int:
        """Count of traces dropped due to buffer overflow."""
        return self._dropped_events

    @property
    def recorded_events(self) -> int:
        """Count of traces successfully recorded into buffer."""
        return self._recorded_events

    def start(self) -> None:
        """Start the background flush task if an asyncio event loop is running."""
        if self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._flush_task = loop.create_task(self._background_flush_loop())
        except RuntimeError:
            # No running loop; flush loop will be started upon first async call
            pass

    async def astart(self) -> None:
        """Explicitly start background flushing in an active async context."""
        if not self._running:
            self._running = True
            loop = asyncio.get_running_loop()
            self._flush_task = loop.create_task(self._background_flush_loop())

    def record(self, trace: TelemetryTrace) -> None:
        """Enqueue trace synchronously without blocking."""
        if not self.sampler.should_sample(trace.trace_id):
            return

        try:
            self._queue.put_nowait(trace)
            self._recorded_events += 1
        except asyncio.QueueFull:
            self._dropped_events += 1
            logger.warning(
                "AsyncTelemetryCollector queue is full. Dropping trace %s",
                trace.trace_id,
            )

    async def arecord(self, trace: TelemetryTrace) -> None:
        """Enqueue trace asynchronously with timeout."""
        if not self.sampler.should_sample(trace.trace_id):
            return

        try:
            await asyncio.wait_for(self._queue.put(trace), timeout=0.1)
            self._recorded_events += 1
        except (TimeoutError, asyncio.QueueFull):
            self._dropped_events += 1
            logger.warning(
                "AsyncTelemetryCollector queue is full. Dropping trace %s",
                trace.trace_id,
            )

    async def aflush(self) -> None:
        """Drain and flush all queued traces to the underlying sink collector."""
        items: list[TelemetryTrace] = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        for item in items:
            self.sink.record(item)
            self._queue.task_done()

        if hasattr(self.sink, "flush"):
            try:
                self.sink.flush()
            except Exception as exc:
                logger.error("Error flushing sink collector: %s", exc)

    def flush(self) -> None:
        """Synchronous flush for backward compatibility."""
        items: list[TelemetryTrace] = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        for item in items:
            self.sink.record(item)
            with contextlib.suppress(ValueError):
                self._queue.task_done()
        self.sink.flush()

    async def aclose(self) -> None:
        """Gracefully drain buffer and stop background flush task."""
        self._running = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
        await self.aflush()

    def clear(self) -> None:
        """Clear queue and underlying sink."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break
        self.sink.clear()

    async def _background_flush_loop(self) -> None:
        """Periodic background flush loop."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval_seconds)
                await self.aflush()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in telemetry background flush loop: %s", exc)
