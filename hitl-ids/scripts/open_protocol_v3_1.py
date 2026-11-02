"""Explicit future V3.1 opening; independently refuses incompatible Python before any writes."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from protocol_v3_1.environment import require_python, environment_receipt
from protocol_v3_1.common import *


def open_protocol(runtime, output):
    require_python()  # Independent guard: do not rely on the standalone validator.
    from validate_protocol_v3_1 import validate
    validate()
    verify_runtime(runtime)
    output = Path(output).resolve()
    if output == BUNDLE or BUNDLE in output.parents:
        raise ValueError('Results must be outside frozen bundle')
    # Never admit an old V3.0 output directory or overwrite any existing run.
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'opening.json', {
        'protocolVersion': VERSION, 'status': 'opened', 'runtimeSha': RUNTIME_SHA,
        'manifestHash': file_hash(BUNDLE / 'manifest.json'), 'outputRoot': str(output),
        'openedAt': datetime.now(timezone.utc).isoformat(),
        'operatorAcknowledgement': 'OPEN-FINAL-V3.1',
        'environment': environment_receipt(),
        'requirementsHash': file_hash(REPO / 'hitl-ids/requirements.txt')})
    return output / 'opening.json'


if __name__ == '__main__':
    require_python()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ack', choices=['OPEN-FINAL-V3.1'], required=True)
    args = parser.parse_args()
    print(open_protocol(args.runtime_root, args.out))
