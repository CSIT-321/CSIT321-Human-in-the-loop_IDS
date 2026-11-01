"""Serve only a disposable synthetic queue database. Never opens collection or demo.db."""
import argparse
from pathlib import Path
import sys
import tempfile

HITL = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(HITL))
sys.path.insert(0, str(HITL/'tests'))
import uvicorn
from apps.api.main import create_app
from operational_queue_fixture import build_queue_fixture

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8010)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hitl-operational-queue-e2e-') as directory:
        path = Path(directory)/'queue.db'
        build_queue_fixture(path)
        print(f'Disposable synthetic operational queue: {path}', flush=True)
        uvicorn.run(create_app(path), host='127.0.0.1', port=args.port, log_level='warning')
