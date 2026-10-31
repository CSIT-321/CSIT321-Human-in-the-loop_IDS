"""Pristine synthetic S16 browser fixture. Never opens or copies data/demo.db."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from apps.api import auth
from apps.api.main import create_app
from packages.contracts import db,models as m
from packages.detection.feedback.learning import family_key
from packages.detection.fusion.cef import EVIDENCE_PRIORITY, FusionConfig
from packages.detection.pipeline.store import guardrail_snapshot

STAMP=datetime(2026,1,1,tzinfo=timezone.utc)
FAMILY={1696,3873,3153,3044,4526}


def build_pristine_fixture(path):
    """Seven narrative alerts plus inert rows required by the unchanged 5,000-alert assertion."""
    path=Path(path)
    if path.exists(): raise FileExistsError('S16 fixture refuses to overwrite any database')
    with closing(db.connect(path)) as conn:
        db.create_schema(conn)
        dataset=db.insert(conn,m.Dataset(name='SYNTHETIC pristine S16 browser fixture',version='s16-fixture-v1',
            source_file='synthetic:no-capture',total_records=5000,class_distribution={},created_at=STAMP,
            preparation_meta={'synthetic':True,'purpose':'Pristine learning-gate workflow regression; not detector performance evidence'}))
        db.insert(conn,m.MlModel(version='synthetic-s16',model_type='synthetic_fixture',model_file='synthetic:no-model',created_at=STAMP))
        run=db.insert(conn,m.DetectionRun(dataset_id=dataset,model_version='synthetic-s16',rule_set_version='synthetic-no-rules',
            fusion_weights=FusionConfig().snapshot(),guardrail_config=guardrail_snapshot(conn),
            status='completed',alert_count=5000,started_at=STAMP,completed_at=STAMP,seed=16))
        for number in range(1,5001):
            record=f'AL-{number:05d}'
            attack='Web Attack' if number==478 else 'Port Scan' if number in FAMILY else 'Benign'
            evidence='ml_only' if number==478 or number in FAMILY else 'none'
            score=99.89 if number==478 else 60.0 if number in FAMILY else 36.94 if number==3086 else 0.0
            band='tier2_candidate' if number==478 else evidence
            port=445 if number in FAMILY else 80 if number in (478,3086) else 12345
            explanation=None
            if number==478:
                explanation=m.MlExplanation(status='available',method='synthetic_fixture',output_space='synthetic_margin',
                    explained_class='Web Attack',base_value=0,raw_model_margin=1,
                    top_supporting_features=[m.ShapAttribution(feature_name='Flow Duration',feature_value=1,shap_contribution=1,direction='supports_prediction')],
                    additivity_check=m.AdditivityCheck(passed=True,difference=0,tolerance=0))
            alert=m.Alert(id=number,alert_ref=uuid5(NAMESPACE_URL,'synthetic-s16:'+record),dataset_id=dataset,run_id=run,
                combined_score=score,detection_score=score,severity='Critical' if number==478 else 'Low',confidence=.9989 if number==478 else .9,
                ml_probability=.9989 if number==478 else .9,ml_predicted_class=attack,attack_category=attack,
                shap_attributions=explanation,explanation='SYNTHETIC S16 workflow fixture; no model inference or network traffic',
                is_critical=number==478,requires_review=number==478,evidence_class=evidence,evidence_priority=EVIDENCE_PRIORITY[evidence],
                queue_class=band,queue_priority=m.QUEUE_PRIORITY[band],created_at=STAMP,updated_at=STAMP,
                family_key=family_key('Port Scan',445,'tcp',None,'198.51.100.16','ml_only') if number in FAMILY else None)
            db.insert(conn,alert)
            db.insert(conn,m.FlowRecord(alert_id=number,source_record_id=record,src_ip='192.0.2.16',dst_ip='198.51.100.16',
                src_port=40000,dst_port=port,protocol='TCP',duration=1,packets=2,bytes=128,
                flow_features={'Timestamp':STAMP.isoformat(),'Flow Duration':1}))
        conn.commit()
        auth.ensure_demo_accounts(conn)
        assert conn.execute('SELECT count(*) FROM feedback_events').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM alert_families').fetchone()[0]==0
    return path


def main():
    import uvicorn
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8001)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hitl-s16-pristine-') as folder:
        path=build_pristine_fixture(Path(folder)/'s16.db')
        print(f'Serving pristine SYNTHETIC S16 fixture: {path}',flush=True)
        uvicorn.run(create_app(path),host='127.0.0.1',port=args.port,log_level='warning')


if __name__=='__main__': main()
