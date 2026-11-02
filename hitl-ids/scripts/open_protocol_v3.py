"""FUTURE operator action. Creates a separate opening receipt; never modifies frozen artifacts."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from protocol_v3.common import *
from validate_protocol_v3 import validate

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ack',choices=['OPEN-FINAL-V3'],required=True)
    args=parser.parse_args(); validate();verify_runtime(args.runtime_root)
    output=args.out.resolve()
    if output==BUNDLE or BUNDLE in output.parents: raise ValueError('Results must be outside frozen bundle')
    output.mkdir(parents=True,exist_ok=False)
    write(output/'opening.json',{'protocolVersion':VERSION,'status':'opened','runtimeSha':RUNTIME_SHA,
        'manifestHash':file_hash(BUNDLE/'manifest.json'),'outputRoot':str(output),
        'openedAt':datetime.now(timezone.utc).isoformat(),'operatorAcknowledgement':args.ack})
    print(output/'opening.json')
