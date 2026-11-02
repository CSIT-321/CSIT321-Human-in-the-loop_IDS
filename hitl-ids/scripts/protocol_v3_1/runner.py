"""Supervisor: decision journal is fsynced BEFORE any per-alert oracle access.

Worker receives only EVE/context until an authorized canonical human action is due.
Frozen artifacts are never modified. Only the explicit open command creates an opening receipt.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from .common import *
from .environment import require_python, validate_opening_environment

class Worker:
    def __init__(self,runtime,database):
        self.process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('worker.py')),str(runtime),str(database)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env={**os.environ,'PYTHONUTF8':'1'})
    def call(self,**message):
        self.process.stdin.write(json.dumps(message)+'\n'); self.process.stdin.flush()
        line=self.process.stdout.readline()
        if not line: raise RuntimeError('Worker exited: '+self.process.stderr.read())
        reply=json.loads(line)
        if not reply['ok']: raise RuntimeError(reply['error'])
        return reply['value']
    def close(self):
        self.process.stdin.close()
        try: self.process.wait(timeout=10)
        except subprocess.TimeoutExpired: self.process.terminate(); self.process.wait(timeout=5)

def append(file,record):
    file.write(canonical(record).decode()+'\n'); file.flush(); os.fsync(file.fileno())

def reveal(oracle_path,ref,decision,journal_path):
    frozen=json.loads(journal_path.read_text(encoding='utf-8').splitlines()[-1])
    if frozen['snapshotHash']!=digest(decision) or frozen['decision']['alertRef']!=ref:
        raise ValueError('Decision must be durably captured before outcome access')
    outcome=read(oracle_path).get(ref)
    if outcome not in OUTCOMES: raise ValueError('Missing/invalid oracle outcome; no safe default')
    return outcome

def run(mode,bundle,runtime,output,*,opening=None,development=False):
    require_python()
    if mode not in ('baseline','adaptive'): raise ValueError('Unknown arm')
    rows=[json.loads(line) for line in (bundle/'workload/operational-workload.jsonl').read_text(encoding='utf-8').splitlines()]
    structure=read(bundle/'expected/workload-structure.json'); contexts=read(bundle/'workload/trusted-context.json')
    if development:
        if bundle.resolve()==BUNDLE.resolve() or len(rows)>8: raise ValueError('Development fixture must be separate and at most 8 alerts')
        sensor,scope='controlled-v3-development','controlled-v3-development'
    else:
        from validate_protocol_v3_1 import validate
        validate(bundle)
        if opening is None: raise ValueError('Explicit opening receipt required; final run is NOT authorized by freeze')
        receipt=read(opening)
        validate_opening_environment(receipt)
        if receipt['manifestHash']!=file_hash(BUNDLE/'manifest.json') or receipt['runtimeSha']!=RUNTIME_SHA or receipt['status']!='opened':
            raise ValueError('Opening receipt does not bind this frozen protocol')
        if Path(receipt['outputRoot']).resolve()!=output.parent.resolve(): raise ValueError('Wrong output directory')
        sensor,scope=SENSOR,SCOPE
    runtime=verify_runtime(runtime)
    output.mkdir(parents=True,exist_ok=False)
    worker=Worker(runtime,output/'run.db')
    decisions=output/'decisions.jsonl'; feedback=[]; learning_end=None
    try:
        probe=worker.call(command='oracle-isolation-probe',path=str(bundle/'oracle/external-outcomes.json'))
        if not probe['oracleAccessDenied']: raise ValueError('Runtime can access oracle')
        with decisions.open('x',encoding='utf-8') as journal,(output/'outcomes.jsonl').open('x',encoding='utf-8') as joined,(output/'feedback.jsonl').open('x',encoding='utf-8') as feedback_journal:
            for eve,meta in zip(rows,structure):
                if mode=='baseline' and meta['phase']=='learning': continue
                if meta['phase']=='holdout' and learning_end is None:
                    learning_end=worker.call(command='snapshot'); write(output/'learning-end.json',learning_end)
                decision=worker.call(command='decision',eve=eve,context=contexts[meta['alertRef']],alertRef=meta['alertRef'],
                    actor=meta['analyst'],sensor=sensor,scope=scope)
                captured={'index':meta['index'],'phase':meta['phase'],'stratum':meta['stratum'],'pattern':meta['pattern'],
                    'decision':decision,'snapshotHash':digest(decision)}
                append(journal,captured)
                outcome=reveal(bundle/'oracle/external-outcomes.json',meta['alertRef'],decision,decisions)
                append(joined,{'alertRef':meta['alertRef'],'outcome':outcome,'decisionHash':captured['snapshotHash'],
                    'revealAfterDurableDecision':True})
                if mode=='adaptive' and (meta['phase']=='learning' or meta['driftAudit']):
                    result=worker.call(command='verdict',alertRef=meta['alertRef'],outcome=outcome,actor=meta['analyst'])
                    action={'index':meta['index'],'alertRef':meta['alertRef'],'phase':meta['phase'],
                        'pattern':meta['pattern'],'decisionHash':captured['snapshotHash'],**result}
                    feedback.append(action); append(feedback_journal,action)
                    if result['memory']['oneAlertOneVoteViolations']: raise ValueError('One-alert-one-vote violation')
        write(output/'feedback.json',feedback)
        final=worker.call(command='snapshot'); write(output/'final-memory.json',final)
        write(output/'runtime-metrics.json',worker.call(command='metrics'))
        if final['collectionRuns'] or final['foreignKeyViolations'] or final['oneAlertOneVoteViolations']:
            raise ValueError('Collection/integrity boundary violated')
        write(output/'receipt.json',{'status':'development_only' if development else 'completed','arm':mode,
            'runtimeSha':RUNTIME_SHA,'manifestHash':None if development else file_hash(BUNDLE/'manifest.json'),
            'oracleIsolation':probe,'files':{p.name:file_hash(p) for p in output.iterdir() if p.suffix in ('.json','.jsonl')}})
    finally: worker.close()
    return output

def cli(mode):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root',type=Path,required=True); parser.add_argument('--opening',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();run(mode,BUNDLE,args.runtime_root,args.out,opening=args.opening)
