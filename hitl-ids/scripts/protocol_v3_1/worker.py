"""Oracle-blind runtime subprocess. Product actions use authenticated HTTP TestClient calls.

Only account/schema setup and the existing synthetic trusted-fact producer write prerequisites.
No direct Memory, work-claim, routing or Selective Review state writes are permitted here.
"""
import json
import sys
import time
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

def reject_oracle(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = str(args[0]).replace('\\', '/').lower()
        if '/oracle/' in path or 'external-outcomes' in path:
            raise PermissionError('Oracle files are forbidden in the runtime subprocess')

sys.addaudithook(reject_oracle)
runtime, database = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(runtime))
from fastapi.testclient import TestClient
from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db, models as m
from packages.detection.adapters.staging import stage_file
from packages.detection.adapters.operational_v2 import read_projection
from packages.detection.context_store import seed_synthetic_facts
from packages.detection.triage_policy import TriageContext
from packages.detection import triage_memory as memory

if database.exists(): raise ValueError('Run database must be new')
with closing(db.connect(database)) as c:
    db.create_schema(c)
    for i in range(1,4):
        db.insert(c,m.User(username=f'v3-analyst-{i}',display_name=f'V3 Analyst {i}',
            password_hash=auth.hash_password('controlled-v3-demo'),email=f'v3-{i}@example.test',role='security_analyst'))
    c.commit()
client = TestClient(create_app(database)); tokens = {}
for i in range(1,4):
    name=f'v3-analyst-{i}'
    response=client.post('/api/auth/login',json={'username':name,'password':'controlled-v3-demo'})
    response.raise_for_status(); tokens[name]={'Authorization':'Bearer '+response.json()['token']}
actor='v3-analyst-1'; counter=0; writes=[]
def get(path):
    r=client.get(path,headers=tokens[actor]); r.raise_for_status(); return r.json()
def post(path,body):
    global counter
    counter+=1
    body={'requestId':str(uuid5(NAMESPACE_URL,f'controlled-v3:{database.stem}:{counter}:{path}')),**body}
    r=client.post(path,headers=tokens[actor],json=body)
    if not r.is_success: raise ValueError(f'{path}: {r.status_code}: {r.text}')
    writes.append({'path':path,'actor':actor,'requestId':body['requestId']})
    return r.json()

def memory_snapshot():
    with closing(db.connect(database)) as c:
        lessons=[]; violations=[]; authors={}
        for row in c.execute('SELECT id,lesson_ref FROM triage_memory_lessons ORDER BY id').fetchall():
            v=memory.read_memory(c,row['lesson_ref']).model_dump(mode='json',by_alias=True)
            evidence=memory.effective_evidence(c,row['id'])[0]
            refs=[str(e.source_operational_alert_ref) for e in evidence]
            if len(refs)!=len(set(refs)): violations.append(row['lesson_ref'])
            v['effectiveVotes']=[e.model_dump(mode='json',by_alias=True) for e in evidence]
            for e in evidence:
                author=e.source_conclusion.actor_id if e.source_conclusion else e.verdict_author_id
                authors[str(author)]=authors.get(str(author),0)+1
            lessons.append(v)
        return {'lessons':lessons,'oneAlertOneVoteViolations':violations,'evidenceAuthorDistribution':authors,
            'collectionRuns':c.execute('SELECT count(*) FROM prospective_runs').fetchone()[0],
            'foreignKeyViolations':len(c.execute('PRAGMA foreign_key_check').fetchall()),
            'verdictEvents':c.execute('SELECT count(*) FROM analyst_verdict_events').fetchone()[0],
            'writes':list(writes)}

class EveInput:
    def __init__(self,record): self.record=record
    def read_text(self,**kwargs): return json.dumps([self.record])

def handle(message):
    global actor
    command=message['command']; actor=message.get('actor','v3-analyst-1')
    if command=='decision':
        record=message['eve']; at=datetime.fromisoformat(record['timestamp']); started=time.monotonic()
        # Controlled scenario clock only; no policy/threshold/claim-arbitration patch.
        m.utc_now=lambda:at+timedelta(seconds=time.monotonic()-started)
        with closing(db.connect(database)) as c:
            stage_file(c,EveInput(record),message['sensor'],capture_scope=message['scope'])
            row=c.execute('SELECT id FROM external_alert_inbox WHERE canonical_alert_id=?',(message['alertRef'],)).fetchone()
            if row is None: raise ValueError('Identity disagrees with the actual Suricata adapter')
            inbox=row[0]
        eligible=post(f'/api/v2/external-alerts/{inbox}/eligibility',{'expectedReviewId':None,'decision':'accepted','reason':'Controlled V3 source contract checked'})
        admitted=post(f'/api/v2/external-alerts/{inbox}/admit',{'expectedReviewId':eligible['reviewId'],'reason':'Controlled V3 chronological admission'})['view']
        ref=admitted['operationalAlertRef']; assert ref==message['alertRef']
        with closing(db.connect(database)) as c:
            alert=read_projection(c,admitted['operationalAlertId'])
            seed_synthetic_facts(c,alert,TriageContext.model_validate(message['context']),m.utc_now())
        review=get(f'/api/v2/alerts/{ref}/selective-review')
        post(f'/api/v2/alerts/{ref}/selective-review/evaluate',{'expectedVersion':review['version'],'reason':'Controlled V3 evaluate frozen trusted context before outcome reveal'})
        review=get(f'/api/v2/alerts/{ref}/selective-review'); route=get(f'/api/v2/alerts/{ref}/triage-state')
        matches=get(f'/api/v2/alerts/{ref}/triage-memory/matches?limit=200')['items']
        return {'alertRef':ref,'disposition':review['disposition'],'reviewRequired':review['disposition']!='no_immediate_review',
            'reasonCodes':review['reasonCodes'],'route':route['state']['handlingRoute'],'classification':route['classification'],
            'priority':route['state']['operationalPriority'],'caseRef':route['caseRef'],'humanOverride':review['humanOverride'],
            'decisionTimestamp':review['lastDecision']['createdAt'],'reviewEvent':review['lastDecision'],
            'matchedMemoryLessonRef':review['policyEvaluation']['result']['matchedLessonRef'], 'memoryMatches':matches}
    if command=='verdict':
        ref=message['alertRef']; override=False
        work=get(f'/api/v2/alerts/{ref}/work')
        if not work['canClaim'] and not work['isOwner']:
            review=get(f'/api/v2/alerts/{ref}/selective-review')
            post(f'/api/v2/alerts/{ref}/selective-review/require-human',{'expectedVersion':review['version'],'reason':'Controlled V3 predefined explicit drift audit'})
            override=True; work=get(f'/api/v2/alerts/{ref}/work')
        if not work['isOwner']:
            post(f'/api/v2/alerts/{ref}/work/claim',{'expectedRevision':work['revision']})
        current=get(f'/api/v2/alerts/{ref}/verdict')
        result=post(f'/api/v2/alerts/{ref}/verdict',{'expectedRevision':current['revision'],
            'expectedStateVersion':current['sourceStateVersion'],'outcome':message['outcome'],
            'reason':'Controlled scenario human assessment after frozen pre-outcome decision'})
        return {'verdict':result,'explicitOverride':override,'memory':memory_snapshot(),
            'postFeedbackReview':get(f'/api/v2/alerts/{ref}/selective-review')}
    if command=='snapshot': return memory_snapshot()
    if command=='metrics': return get('/api/v2/selective-review/metrics')
    if command=='oracle-isolation-probe':
        try: open(message['path'],encoding='utf-8')
        except PermissionError: return {'oracleAccessDenied':True}
        raise ValueError('Oracle isolation failed')
    raise ValueError('Unknown worker command')

for line in sys.stdin:
    try: result={'ok':True,'value':handle(json.loads(line))}
    except Exception as exc: result={'ok':False,'error':f'{type(exc).__name__}: {exc}'}
    print(json.dumps(result,ensure_ascii=False),flush=True)
