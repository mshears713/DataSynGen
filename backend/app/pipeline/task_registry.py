"""
TaskRegistry: in-process registry of running asyncio tasks.
Manages pause/cancel events for each run.
"""
import asyncio
from dataclasses import dataclass, field


@dataclass
class RunTaskEntry:
    task: asyncio.Task
    pause_event: asyncio.Event
    cancel_event: asyncio.Event


class TaskRegistry:
    def __init__(self):
        self._entries: dict[str, RunTaskEntry] = {}

    def register(
        self,
        run_id: str,
        task: asyncio.Task,
        pause_event: asyncio.Event,
        cancel_event: asyncio.Event,
    ) -> None:
        self._entries[run_id] = RunTaskEntry(task, pause_event, cancel_event)

    def get_entry(self, run_id: str) -> RunTaskEntry | None:
        return self._entries.get(run_id)

    def is_running(self, run_id: str) -> bool:
        entry = self._entries.get(run_id)
        if not entry:
            return False
        return not entry.task.done()

    def signal_pause(self, run_id: str) -> bool:
        entry = self._entries.get(run_id)
        if entry and not entry.task.done():
            entry.pause_event.set()
            return True
        return False

    def signal_cancel(self, run_id: str) -> bool:
        entry = self._entries.get(run_id)
        if entry and not entry.task.done():
            entry.cancel_event.set()
            return True
        return False

    def clear_pause(self, run_id: str) -> None:
        entry = self._entries.get(run_id)
        if entry:
            entry.pause_event.clear()

    def create_events(self, run_id: str) -> tuple[asyncio.Event, asyncio.Event]:
        """Create fresh pause and cancel events for a run."""
        existing = self._entries.get(run_id)
        if existing:
            # Reuse existing events (clear them for resume)
            existing.pause_event.clear()
            return existing.pause_event, existing.cancel_event
        pause_event = asyncio.Event()
        cancel_event = asyncio.Event()
        return pause_event, cancel_event

    def cleanup(self, run_id: str) -> None:
        self._entries.pop(run_id, None)

    def running_run_ids(self) -> list[str]:
        return [rid for rid, e in self._entries.items() if not e.task.done()]


# Module-level singleton — shared across the FastAPI app
task_registry = TaskRegistry()
