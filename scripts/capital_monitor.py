import os
import signal
import sys
import time
import traceback

from services.capital_lab import sync_all_open_positions, update_monitor_state

INTERVAL = max(5.0, float(os.getenv("CAPITAL_MONITOR_INTERVAL", "10")))
_running = True


def _stop(*_args):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def main():
    cycle = 0
    update_monitor_state("running", cycle_count=0, last_closed_count=0, started=True)

    while _running:
        closed_count = 0
        error = None
        try:
            result = sync_all_open_positions()
            closed_count = int(result.get("closed") or 0)
            if result.get("errors"):
                error = "; ".join(
                    "company %s: %s" % (item.get("company_id"), item.get("error"))
                    for item in result["errors"][:5]
                )
        except Exception:
            error = traceback.format_exc(limit=4)

        cycle += 1
        try:
            update_monitor_state(
                "running",
                cycle_count=cycle,
                last_closed_count=closed_count,
                last_error=error,
            )
        except Exception:
            print("CAPITAL MONITOR HEARTBEAT ERROR", file=sys.stderr)
            traceback.print_exc()

        slept = 0.0
        while _running and slept < INTERVAL:
            step = min(1.0, INTERVAL - slept)
            time.sleep(step)
            slept += step

    try:
        update_monitor_state("stopped", cycle_count=cycle, last_closed_count=0)
    except Exception:
        pass


if __name__ == "__main__":
    main()
