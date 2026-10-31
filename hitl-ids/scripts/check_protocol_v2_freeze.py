"""Read-only preregistration gate. Never creates a collection run or writes a file."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess

SOURCE_SHA = '7a961450dda7aa193653180f2d4c03b2a24ac5bb'
PROTOCOL_SHA = 'cfc9539c0b325919a60eb8a5722826affa53e1c253e3b96c15e3a6db41dd2541'
PROTOCOL = 'config/prospective-context-protocol-v2.json'
MANIFEST = 'config/prospective-protocol-v2-manifest.json'
ARTIFACTS = {PROTOCOL, MANIFEST, 'scripts/check_protocol_v2_freeze.py',
             'tests/test_protocol_v2_freeze.py', 'docs/prospective-protocol-v2-preregistration.md'}
CONFIGS = {'context-provenance-v1.json', 'external-admission.json', 'operational-triage-v1.json',
           'prospective-context-protocol-v1.json', 'prospective-context-protocol-v2-draft.json',
           'selective-review-v1.json', 'severity-chart.json', 'triage-memory-v1.json'}
METRICS = {'eligibleAlerts','baselineImmediateReviews','selectiveImmediateReviews',
           'noImmediateReviewCount','immediateReviewReductionRate','unsafeDeferrals','unsafeDeferralRate',
           'safeDeferrals','recalls','conflictTriggeredRecalls','humanOverrides',
           'completeTrustedContextCoverage','blockedByUnknownContext','blockedByExpiredContext',
           'blockedByConflictingContext','informativeOutcomeCompleteness','unlabeledOrInconclusive',
           'analystReviewSeconds','totalTaskSeconds','measuredAnalystTimeReduction'}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stamp(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    require(value.tzinfo is not None and value.utcoffset() is not None, 'aware dates required')
    return value


def validate_artifacts(source, artifacts):
    source, artifacts = Path(source), Path(artifacts)
    protocol, manifest = read(artifacts/PROTOCOL), read(artifacts/MANIFEST)
    require(digest(protocol) == PROTOCOL_SHA, 'immutable V2 protocol hash mismatch')
    require(protocol['reviewedCodeSha'] == manifest['commitSha'] == SOURCE_SHA, 'reviewed SHA mismatch')
    require(manifest['cleanTreeAtSourceCapture'] is True, 'source was not clean at capture')
    require(manifest['reviewedBranch'] == protocol['reviewedBranch'], 'review branch mismatch')
    require(manifest['hashAlgorithm'] == protocol['hashAlgorithm'], 'hash algorithm mismatch')
    require(manifest['generatedAt'] == protocol['registeredAt'], 'registration timestamp mismatch')
    expected = {'config/'+name for name in CONFIGS} | {PROTOCOL}
    entries = manifest['configs']
    require(len(entries) == len(expected) and {e['path'] for e in entries} == expected, 'config inventory mismatch')
    require(set(protocol['configHashes']) == expected-{PROTOCOL}, 'protocol config inventory mismatch')
    for entry in entries:
        value = read((artifacts if entry['path'] == PROTOCOL else source)/entry['path'])
        require(value['version'] == entry['version'], 'config version mismatch: '+entry['path'])
        require(digest(value) == entry['sha256'], 'config hash mismatch: '+entry['path'])
        if entry['path'] != PROTOCOL:
            require(entry['sha256'] == protocol['configHashes'][entry['path']], 'protocol/manifest hash mismatch')
    require(protocol['evaluationMode'] == 'prospective_recorded', 'wrong evaluation mode')
    require(stamp(protocol['registeredAt']) < stamp(protocol['holdoutStart']) <
            stamp(protocol['holdoutEnd']) < stamp(protocol['outcomeCutoff']), 'registration/date ordering')
    require(set(protocol['metrics']) == METRICS, 'metric inventory mismatch')
    require(protocol['participantClass'] == 'proxy_student_analyst', 'participant classification mismatch')
    require(not protocol['collectionOpened'] and protocol['openActionRequired'], 'collection must remain unopened')
    return protocol


def git(source, *args):
    return subprocess.check_output(['git', '--no-optional-locks', '-C', str(source), *args], text=True).strip()


def validate_source(source, *, artifact_only=False):
    source = Path(source).resolve()
    require(git(source, 'rev-parse', '--show-toplevel').replace('\\', '/') ==
            source.parent.as_posix(), 'source must be this repository hitl-ids directory')
    if artifact_only:
        names = git(source.parent, 'diff', '--name-only', SOURCE_SHA).splitlines()
        untracked = git(source.parent, 'ls-files', '--others', '--exclude-standard').splitlines()
        allowed = {'hitl-ids/'+p for p in ARTIFACTS}
        require(set(names+untracked) <= allowed, 'non-artifact change from reviewed source')
    else:
        require(git(source, 'rev-parse', 'HEAD') == SOURCE_SHA, 'runtime must use exact reviewed SHA')
        require(not git(source, 'status', '--porcelain', '--untracked-files=normal'), 'runtime tree must be clean')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--artifacts', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--artifacts-only', action='store_true', help='Does NOT authorize runtime or opening.')
    parser.add_argument('--pre-open', action='store_true', help='Also require completion before the future start.')
    args = parser.parse_args()
    try:
        require(not (args.pre_open and args.artifacts_only), 'pre-open requires runtime validation')
        protocol = validate_artifacts(args.source, args.artifacts)
        validate_source(args.source, artifact_only=args.artifacts_only)
        if args.pre_open:
            require(datetime.now(timezone.utc) < stamp(protocol['holdoutStart']),
                    'window missed; remain unopened and preregister a later version')
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, 'FREEZE_MISMATCH: '+str(exc)+'\n')
    print(json.dumps({'status':'passed', 'scope':'artifacts_only' if args.artifacts_only else 'runtime',
                      'reviewedCodeSha':SOURCE_SHA, 'collectionOpened':False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
