"""Offline supervised command study; exports portable preview models, never executes."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import platform
import time

from research.disc_assistant.assistant.nlu.command_catalog import LABELS, CommandCatalog, digest, source
from research.disc_assistant.assistant.nlu.command_features import VERSION, counts, vector, classify
from research.disc_assistant.assistant.nlu.explain import decide
from research.disc_assistant.assistant.nlu.evaluation.encoder import Encoder
from research.disc_assistant.assistant.nlu.evaluation.intents import load_corpus, metrics, calibrate, accepted

ROOT = Path(__file__).parent
DATA = ROOT.parent / 'data'
CS = (.1, 1., 10.)


def fit_features(rows):
    frequency = Counter()
    for row in rows:
        frequency.update(counts(row['text']).keys())
    vocabulary = sorted(frequency)
    idf = [1+math.log((1+len(rows))/(1+frequency[word])) for word in vocabulary]
    return vocabulary, idf


def matrix(rows, vocabulary, idf):
    import numpy as np
    result = np.zeros((len(rows), len(vocabulary)))
    for i, row in enumerate(rows):
        for j, value in vector(row['text'], vocabulary, idf).items():
            result[i,j] = value
    return result


def export_model(estimator, vocabulary, idf):
    order = [list(estimator.classes_).index(label) for label in LABELS]
    return {'kind':'linear-text-v1', 'feature_version':VERSION, 'classes':list(LABELS),
            'vocabulary':vocabulary, 'idf':idf, 'weights':estimator.coef_[order].tolist(),
            'bias':estimator.intercept_[order].tolist(), 'threshold':0., 'margin':0.}


def evidence(probabilities, labels):
    result = []
    for scores in probabilities:
        order = sorted(range(len(labels)), key=lambda i:(-scores[i],labels[i]))
        first, second = order[:2]
        result.append({'label':str(labels[first]), 'score':float(scores[first]),
                       'margin':float(scores[first]-scores[second]), 'runner_up':str(labels[second])})
    return result


def scored(rows, outputs):
    result = metrics(rows, [o['candidate']['label'] for o in outputs])
    result['complete_positive_correct'] = sum(
        r['label']!='reject' and o['candidate']['intent']==r.get('intent') for r,o in zip(rows,outputs))
    result['cases'] = [{'id':r['id'], 'text':r['text'], 'expected':r['label'], 'expected_intent':r.get('intent'), **o}
                       for r,o in zip(rows,outputs)]
    return result


def validate_splits(authored, development, regression, challenge):
    seen = set()
    for split in (authored['examples'], development, regression, challenge):
        for row in split:
            key = ' '.join(row['text'].casefold().split())
            if key in seen:
                raise ValueError(f'duplicate text across command splits: {key}')
            seen.add(key)
    if {r['label'] for r in authored['examples']} != set(LABELS):
        raise ValueError('training needs every command/reject label')


def evaluate_locale(locale, corpus, challenge, encoder, output):
    from sklearn.linear_model import LogisticRegression
    authored = source(locale)
    training = authored['examples']
    dev = [r for r in corpus['cases'] if r['locale']==locale and r['split']=='development']
    regression = [r for r in corpus['cases'] if r['locale']==locale and r['split']=='test']
    challenge = [r for r in challenge['cases'] if r['locale']==locale]
    validate_splits(authored, dev, regression, challenge)
    rows = training+dev+regression+challenge
    vectors = encoder.encode([r['text'] for r in rows])
    vocabulary, idf = fit_features(training)
    features = matrix(rows,vocabulary,idf)
    n, d = len(training), len(dev)
    models, comparisons = {}, {}
    for name, values in [('text',features),('embeddings',vectors)]:
        best, trials = None, []
        for c in CS:
            estimator = LogisticRegression(C=c,max_iter=1000,random_state=0)
            estimator.fit(values[:n],[r['label'] for r in training])
            predictions = evidence(estimator.predict_proba(values[n:n+d]),estimator.classes_)
            calibration = calibrate(dev,predictions)
            score = calibration['development']
            trials.append({'C':c, **calibration})
            key = (-score['false_activations'],score['macro_f1'],score['correct'],-c)
            if best is None or key>best[0]:
                best=(key,estimator,calibration,c)
        _,estimator,calibration,c = best
        comparisons[name]={'C':c, 'threshold':calibration['threshold'], 'margin':calibration['margin'],
                           'development':calibration['development'], 'trials':trials, 'evaluation':{}}
        for split,items,offset in [('regression',regression,n+d),('challenge',challenge,n+d+len(regression))]:
            pred = evidence(estimator.predict_proba(values[offset:offset+len(items)]),estimator.classes_)
            comparisons[name]['evaluation'][split] = {
                'raw':metrics(items,[p['label'] for p in pred]),
                'accepted':metrics(items,[accepted(p,calibration['threshold'],calibration['margin']) for p in pred]),
                'cases':[{'id':r['id'],'expected':r['label'],**p} for r,p in zip(items,pred)]}
        models[name]=(estimator,calibration)
    estimator,calibration=models['text']
    portable = export_model(estimator,vocabulary,idf)
    portable.update(threshold=calibration['threshold'],margin=calibration['margin'],
                    training={'source_hash':digest(authored),'development_hash':digest(dev),
                              'algorithm':'multinomial logistic regression','C':comparisons['text']['C'],
                              'selection':'development only; minimize false activations, then macro-F1, correct; smallest C tie'})
    # Runtime JSON inference must agree with the training implementation on every case.
    pred = evidence(estimator.predict_proba(features),estimator.classes_)
    for row,expected in zip(rows,pred):
        actual = classify(row['text'],portable)
        if actual['label']!=expected['label'] or abs(actual['score']-expected['score'])>1e-10:
            raise AssertionError('portable inference differs from trained model')
    bundle={'version':1,'locale':locale,'source_hash':digest(authored),'classifier':portable,
            'embedding':{'pipeline':encoder.info,'signature':encoder.signature,'dimensions':encoder.info['dimensions']},
            'vectors':{row['id']:value.tolist() for row,value in zip(training,vectors[:n])}}
    bundle_path=output/(locale+'-commands.json')
    bundle_path.write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+'\n')
    catalog=CommandCatalog(output/'import-check')
    try:
        published=catalog.publish(locale,bundle)
        if published['classifier']!=portable:
            raise AssertionError('snapshot import changed the model')
    finally:
        catalog.close()
    variants={}
    for split,items in [('regression',regression),('challenge',challenge)]:
        guarded=[decide(r['text'],authored) for r in items]
        learned=[decide(r['text'],authored,portable) for r in items]
        variants[split]={'rules':metrics(items,[o['rules']['label'] for o in guarded]),
                         'guarded_rules':scored(items,guarded),'preview_with_text_classifier':scored(items,learned)}
    timings=[]
    for _ in range(3):
        for row in challenge:
            start=time.perf_counter()
            classify(row['text'],portable)
            timings.append((time.perf_counter()-start)*1000)
    timings.sort()
    return {'source_hash':digest(authored),'sizes':{'train':n,'development':d,'regression':len(regression),'challenge':len(challenge)},
            'classifiers':comparisons,'pipeline':variants,'portable_runtime':{'bundle_bytes':bundle_path.stat().st_size,
            'features':len(vocabulary),'probes':len(timings),'p50_ms':timings[len(timings)//2],
            'p95_ms':timings[int(len(timings)*.95)],'parity_cases':len(rows)},'snapshot':published['id']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='new directory outside repository')
    args=parser.parse_args()
    work,output=args.work.expanduser().resolve(),args.output.expanduser().resolve()
    repository=ROOT.parents[4]
    if any(path==repository or repository in path.parents for path in (work,output)):
        parser.error('work and output must be outside the repository')
    corpus=load_corpus(DATA/'intents.json')
    challenge=json.loads((DATA/'command_challenge.json').read_text())
    # Validate all splits before any fit or evaluation.
    for locale in ('ru','en'):
        validate_splits(source(locale),*[ [r for r in corpus['cases'] if r['locale']==locale and r['split']==split]
            for split in ('development','test')], [r for r in challenge['cases'] if r['locale']==locale])
    output.mkdir(parents=True,exist_ok=False)
    encoder=Encoder(work/'model',work/'embeddings.sqlite3')
    try:
        report={'version':1,'experiment':'supervised-command-preview-v1','corpus_hash':digest(corpus),
                'challenge_hash':digest(challenge),'model':encoder.info,'host':platform.platform(),
                'limits':'authored text; original test reused as regression; no human speech, player, or Pi validation; embedding encoder frozen',
                'locales':{}}
        for locale in ('ru','en'):
            report['locales'][locale]=evaluate_locale(locale,corpus,challenge,encoder,output)
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'output':str(output),'locales':{locale:r['portable_runtime'] for locale,r in report['locales'].items()}},indent=2))
    finally:
        encoder.close()


if __name__=='__main__':
    main()
