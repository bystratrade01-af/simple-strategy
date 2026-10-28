"""Research software monitor. No market signals, LLM agents or order execution."""
import argparse
import json
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STOP = False

def stop(*_):
    global STOP
    STOP = True

def emit(event, **values):
    print(json.dumps(dict(timestamp=datetime.now(timezone.utc).isoformat(), event=event,
                         execution_eligible=False, **values)), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    root = Path(__file__).resolve().parent
    next_check = 0.0
    last_status = 'NOT_RUN'
    while not STOP:
        now = time.monotonic()
        if now >= next_check:
            emit('software_check_started', scope='synthetic acceptance-gate regression tests')
            try:
                result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover',
                    '-s', 'ict_team_setup/tests', '-p', 'test_team_gate.py', '-q'],
                    cwd=root, capture_output=True, text=True, timeout=120)
                last_status = 'PASS' if result.returncode == 0 else 'FAIL'
                emit('software_check_finished', status=last_status,
                     output=(result.stdout + result.stderr)[-4000:])
            except subprocess.TimeoutExpired:
                last_status = 'FAIL'
                emit('software_check_finished', status='FAIL', reason='timeout')
            if args.once:
                return 0 if last_status == 'PASS' else 1
            if last_status != 'PASS':
                return 1
            next_check = time.monotonic() + 21600
        emit('heartbeat', software_checks=last_status, research_acceptance='BLOCKED',
             reason='No live market pipeline or independent LLM review configured')
        for _ in range(60):
            if STOP:
                break
            time.sleep(1)
    emit('stopped')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
