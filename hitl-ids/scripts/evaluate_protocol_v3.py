"""Pure, offline paired evaluator. Never calls product APIs or opens collection."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from protocol_v3.common import *

PRIMARY={'stable_matching_benign','unseen_benign','malicious','suspicious'}
def rate(n,d): return {'numerator':n,'denominator':d,'value':n/d if d else None}
def load_lines(path): return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]

def load_arm(path,development=False):
    receipt=read(path/'receipt.json')
    if receipt['status']!=('development_only' if development else 'completed'): raise ValueError('Incomplete/wrong run type')
    if not development and receipt['manifestHash']!=file_hash(BUNDLE/'manifest.json'): raise ValueError('Wrong frozen manifest')
    for rel,sha in receipt['files'].items():
        if file_hash(path/rel)!=sha: raise ValueError('Result tampering: '+rel)
    decisions=load_lines(path/'decisions.jsonl'); joined=load_lines(path/'outcomes.jsonl')
    outcomes={o['alertRef']:o for o in joined}
    if len(outcomes)!=len(joined): raise ValueError('Duplicate outcomes')
    refs=[d['decision']['alertRef'] for d in decisions]
    if len(refs)!=len(set(refs)): raise ValueError('Duplicate decision identity')
    for d in decisions:
        ref=d['decision']['alertRef']; o=outcomes.get(ref)
        if digest(d['decision'])!=d['snapshotHash']: raise ValueError('Decision snapshot changed')
        if o and (o['decisionHash']!=d['snapshotHash'] or not o['revealAfterDurableDecision']): raise ValueError('Outcome order/hash violation')
    return [d for d in decisions if d['phase']=='holdout'],outcomes

def pair(baseline,adaptive,development=False):
    b,bo=load_arm(baseline,development); a,ao=load_arm(adaptive,development)
    if [d['decision']['alertRef'] for d in a]!=[d['decision']['alertRef'] for d in b]: raise ValueError('Unpaired chronology')
    if not development and len(a)!=160: raise ValueError('Expected 160 paired holdout decisions')
    feedback=read(adaptive/'feedback.json') if (adaptive/'feedback.json').exists() else []
    feedback_by_ref={f['alertRef']:f for f in feedback if f['phase']=='holdout'}
    records=[]
    for bd,ad in zip(b,a):
        x,y=bd['decision'],ad['decision']; ref=y['alertRef']
        if any(bd[k]!=ad[k] for k in ('index','stratum','pattern')): raise ValueError('Scenario metadata mismatch')
        if x['route']!=y['route'] or x['classification']!=y['classification'] or x['priority']!=y['priority']:
            raise ValueError('Non-learning runtime difference')
        outcome=ao.get(ref,{}).get('outcome')
        if outcome!=bo.get(ref,{}).get('outcome'): raise ValueError('Arms have different oracle outcomes')
        if ad['stratum'] in PRIMARY and (x['route']!='tier1_review' or y['route']!='tier1_review'):
            raise ValueError('Planned primary Tier 1 population not realized; do not silently change denominator')
        deferred=x['reviewRequired'] and not y['reviewRequired']
        kind='not-deferred' if not deferred else 'safe' if outcome in BENIGN else 'unsafe' if outcome in OUTCOMES else 'unassessed'
        records.append({'alertRef':ref,'index':ad['index'],'stratum':ad['stratum'],'pattern':ad['pattern'],
            'baselineDisposition':x['disposition'],'adaptiveDisposition':y['disposition'],
            'baselineReviewRequired':x['reviewRequired'],'adaptiveReviewRequired':y['reviewRequired'],
            'baselineDecisionTimestamp':x['decisionTimestamp'],'adaptiveDecisionTimestamp':y['decisionTimestamp'],
            'baselineReasonCodes':x['reasonCodes'],'adaptiveReasonCodes':y['reasonCodes'],
            'route':y['route'],'classification':y['classification'],'priority':y['priority'],'caseRef':y['caseRef'],
            'matchedMemoryLessonRef':y['matchedMemoryLessonRef'],'memoryMatches':y['memoryMatches'],
            'humanOverride':y['humanOverride'],'explicitAuditOverride':feedback_by_ref.get(ref,{}).get('explicitOverride',False),
            'baselineHumanOverride':x['humanOverride'],'baselineCaseRef':x['caseRef'],'oracleOutcome':outcome,'deferralClassification':kind,
            'baselineSnapshotHash':bd['snapshotHash'],'adaptiveSnapshotHash':ad['snapshotHash']})
    return records,feedback

def metrics(records):
    b=sum(r['baselineReviewRequired'] for r in records); a=sum(r['adaptiveReviewRequired'] for r in records)
    safe=sum(r['deferralClassification']=='safe' for r in records); unsafe=sum(r['deferralClassification']=='unsafe' for r in records)
    total=sum(r['baselineReviewRequired'] and not r['adaptiveReviewRequired'] for r in records)
    valid=sum(r['oracleOutcome'] in OUTCOMES for r in records)
    overrides=sum(r['humanOverride'] or r['explicitAuditOverride'] for r in records)
    return {'population':len(records),'baselineImmediateReview':b,'adaptiveImmediateReview':a,
        'baselineNoImmediateReview':len(records)-b,'adaptiveNoImmediateReview':len(records)-a,
        'immediateReviewReductionCount':b-a,'immediateReviewReductionRate':rate(b-a,b),
        'totalDeferrals':total,'safeDeferrals':safe,'unsafeDeferrals':unsafe,'unassessedDeferrals':total-safe-unsafe,
        'unsafeDeferralRate':rate(unsafe,total),'benignDeferralCoverage':rate(safe,sum(r['baselineReviewRequired'] and r['oracleOutcome'] in BENIGN for r in records)),
        'outcomeCompleteness':rate(valid,len(records)),'missingOutcomes':[r['alertRef'] for r in records if r['oracleOutcome'] not in OUTCOMES],
        'humanOverrides':overrides,'humanOverrideRate':rate(overrides,len(records)),
        'baselineHumanOverrides':sum(r['baselineHumanOverride'] for r in records),
        'baselineAuditSamples':sum('DETERMINISTIC_AUDIT_SAMPLE' in r['baselineReasonCodes'] for r in records),
        'adaptiveAuditSamples':sum('DETERMINISTIC_AUDIT_SAMPLE' in r['adaptiveReasonCodes'] for r in records)}

def csv_file(path,rows):
    if not rows: return
    with path.open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader()
        writer.writerows({k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in rows)

def evaluate(baseline,adaptive,out,development=False):
    records,feedback=pair(baseline,adaptive,development)
    if not development:
        expected=[s for s in read(BUNDLE/'expected/workload-structure.json') if s['phase']=='holdout']
        if [(r['index'],r['alertRef'],r['stratum']) for r in records]!=[(s['index'],s['alertRef'],s['stratum']) for s in expected]:
            raise ValueError('Frozen workload identity/stratum mismatch')
        allowed={s['alertRef'] for s in expected if s['driftAudit']}
        if {f['alertRef'] for f in feedback if f['phase']=='holdout'}!=allowed: raise ValueError('Holdout feedback freeze violation')
    primary=metrics([r for r in records if r['stratum'] in PRIMARY]); all_metrics=metrics(records)
    strata=[{'stratum':s,**metrics([r for r in records if r['stratum']==s])} for s in ('stable_matching_benign','unseen_benign','malicious','suspicious','unknown_tier2','drift_conflict')]
    learning=read(adaptive/'learning-end.json'); final=read(adaptive/'final-memory.json')
    memory_table=[]
    for v in learning['lessons']:
        lesson=v['lesson']; ref=lesson['lessonRef']
        source=next((f for f in feedback if f['alertRef']==lesson['sourceOperationalAlertRef']),None)
        memory_table.append({'lessonRef':ref,'outcome':lesson['outcome'],'scope':lesson['scope'],'support':v['supportCount'],
            'conflicts':v['conflictCount'],'status':v['status'],'activationSource':(v['decision'] or {}).get('decisionSource'),
            'validFrom':v['validFrom'],'expiresAt':v['expiresAt'],'learningPattern':source['pattern'] if source else None,
            'holdoutExactMatches':sum(any(m['memory']['lesson']['lessonRef']==ref and m['strength']=='high' for m in r['memoryMatches']) for r in records)})
    drift=[]; withdrawals=0; initial_deferred=0; post_unsafe=0
    for pattern in sorted({r['pattern'] for r in records if r['stratum']=='drift_conflict'}):
        sequence=[r for r in records if r['stratum']=='drift_conflict' and r['pattern']==pattern]
        initial_deferred+=not sequence[0]['adaptiveReviewRequired']
        for n,r in enumerate(sequence):
            injection=next((f for f in feedback if f['alertRef']==r['alertRef']),None)
            matches=[m for m in r['memoryMatches'] if m['strength']=='high']
            before=matches[0]['memory'] if matches else None
            after=next((v for v in injection['memory']['lessons'] if before and v['lesson']['lessonRef']==before['lesson']['lessonRef']),None) if injection else None
            if after and before['status']=='active' and after['status']!='active': withdrawals+=1
            if n>0 and not r['adaptiveReviewRequired']: post_unsafe+=1
            drift.append({'pattern':pattern,'eventIndex':r['index'],'disposition':r['adaptiveDisposition'],'oracleOutcome':r['oracleOutcome'],
                'feedbackInjected':injection is not None,'beforeSupport':before['supportCount'] if before else None,
                'beforeConflicts':before['conflictCount'] if before else None,'beforeStatus':before['status'] if before else None,
                'guidanceActive':any(m['guidanceActive'] for m in matches),'afterFeedbackSupport':after['supportCount'] if after else None,
                'afterFeedbackConflicts':after['conflictCount'] if after else None,'afterFeedbackStatus':after['status'] if after else None,
                'nextAlertDisposition':sequence[n+1]['adaptiveDisposition'] if n+1<len(sequence) else None})
    tier2=[r for r in records if r['stratum']=='unknown_tier2']
    violations=sum(r['route']!='tier2_case' or not r['caseRef'] or not r['baselineCaseRef'] or not r['adaptiveReviewRequired'] or not r['baselineReviewRequired'] for r in tier2)
    safety={'oneAlertOneVoteViolations':len(final['oneAlertOneVoteViolations']), 'tier2SafetyViolations':violations,
        'postContradictionUnsafeDeferrals':post_unsafe,'conflictTriggeredWithdrawals':withdrawals,'firstContradictionDeferred':initial_deferred,
        'activeLessonsEnteringDrift':sum(r['feedbackInjected'] and r['beforeStatus']=='active' for r in drift),
        'tier2ExpertReviewRequired':sum(r['classification']['attackCategory']=='unknown_needs_expert' for r in tier2),
        'formalTier2Cases':len({r['caseRef'] for r in tier2 if r['caseRef']}),
        'baselineFormalTier2Cases':len({r['baselineCaseRef'] for r in tier2 if r['baselineCaseRef']}),'tier2NoImmediateReview':sum(not r['adaptiveReviewRequired'] for r in tier2)}
    primary_table=[{'metric':'Immediate Review Count','baseline':primary['baselineImmediateReview'],'adaptive':primary['adaptiveImmediateReview'],'differenceOrRate':primary['immediateReviewReductionCount']},
        {'metric':'No Immediate Review Count','baseline':primary['baselineNoImmediateReview'],'adaptive':primary['adaptiveNoImmediateReview'],'differenceOrRate':None}]
    for name,key in [('Immediate Review Reduction Count','immediateReviewReductionCount'),('Immediate Review Reduction Rate','immediateReviewReductionRate'),('Total Deferrals','totalDeferrals'),('Safe Deferrals','safeDeferrals'),('Unsafe Deferrals','unsafeDeferrals'),('Unsafe Deferral Rate','unsafeDeferralRate'),('Benign Deferral Coverage','benignDeferralCoverage'),('Human Overrides','humanOverrides'),('Audit Samples','adaptiveAuditSamples'),('Outcome Completeness','outcomeCompleteness')]:
        primary_table.append({'metric':name,'baseline':primary['baselineAuditSamples'] if name=='Audit Samples' else primary['baselineHumanOverrides'] if name=='Human Overrides' else None,'adaptive':primary[key],'differenceOrRate':primary[key]})
    auto=sum(v['activationSource']=='system_policy' for v in memory_table)
    report={'kind':'development_only' if development else 'final_v3','primary':primary,'allHoldoutSupplementary':all_metrics,'strata':strata,
        'safety':safety,'memoryMetrics':{'lessonsCreated':len(memory_table),'autoActivated':auto,'activationRate':rate(auto,len(memory_table)),
            'supportDistribution':dict(Counter(v['support'] for v in memory_table)),'conflicts':sum(v['conflictCount'] for v in final['lessons']),
            'expiredLessons':sum(v['status']=='expired' for v in final['lessons'])},
        'runtimeR02':{'baseline':read(baseline/'runtime-metrics.json'),'adaptive':read(adaptive/'runtime-metrics.json')},
        'methodologicalPass':not all_metrics['missingOutcomes'],
        'criticalSafetyPass':not any(safety[k] for k in ('oneAlertOneVoteViolations','tier2SafetyViolations','postContradictionUnsafeDeferrals'))}
    out.mkdir(parents=True,exist_ok=False)
    for name,value in [('metrics',report),('records',records),('primary-table',primary_table),('stratum-table',strata),('memory-table',memory_table),('drift-timeline',drift),('learning-timeline',feedback)]:
        write(out/(name+'.json'),value)
        if isinstance(value,list):csv_file(out/(name+'.csv'),value)
    lines=['# '+('DEVELOPMENT ONLY — NOT FINAL RESULTS' if development else 'Final V3 controlled evaluation'),'',
        '| Metric | Baseline | Adaptive | Difference / Rate |','|---|---|---|---|']
    def display(v):
        if v is None:return 'N/A'
        if isinstance(v,dict) and 'denominator' in v:return f"{v['numerator']} / {v['denominator']} = {v['value'] if v['value'] is not None else 'N/A'}"
        return str(v)
    for row in primary_table:lines.append('| '+' | '.join(display(v) for v in row.values())+' |')
    for name,table,columns in [('Strata',strata,['stratum','population','baselineImmediateReview','adaptiveImmediateReview','adaptiveNoImmediateReview','safeDeferrals','unsafeDeferrals']),
        ('Memory',memory_table,['lessonRef','outcome','scope','support','conflicts','status','activationSource','validFrom','expiresAt','learningPattern','holdoutExactMatches']),
        ('Drift timeline',drift,['pattern','eventIndex','disposition','oracleOutcome','feedbackInjected','beforeSupport','beforeConflicts','beforeStatus','guidanceActive','afterFeedbackStatus','nextAlertDisposition'])]:
        lines.extend(['',f'## {name}','','| '+' | '.join(columns)+' |','|'+'|'.join('---' for _ in columns)+'|'])
        for row in table: lines.append('| '+' | '.join(display(row.get(k)) for k in columns)+' |')
    lines+=['','R02 is supplementary observed runtime safety, not the external-oracle unsafe deferral rate.',
        'No detector accuracy, human time savings, population inference or statistical significance is claimed.']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--adaptive',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();evaluate(a.baseline,a.adaptive,a.out)
