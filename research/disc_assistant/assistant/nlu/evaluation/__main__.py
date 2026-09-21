"""Opt-in experiments: python -m research.disc_assistant.assistant.nlu.evaluation --help."""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import platform
import resource
import time

from research.disc_assistant.assistant.nlu.evaluation.encoder import Encoder, prepare
from research.disc_assistant.assistant.nlu.evaluation.intents import evaluate, load_corpus

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[4]
DATA = PACKAGE.parent / 'data'


async def run(args):
    work = args.work.expanduser().resolve()
    if work == ROOT or ROOT in work.parents:
        raise ValueError('model/cache directory must be outside the repository')
    work.mkdir(parents=True, exist_ok=True)
    if args.command == 'prepare':
        result = prepare(work / 'model')
        print(json.dumps({'model':result['model'],'revision':result['revision']},indent=2))
        return
    output = args.output.expanduser().resolve()
    if output.exists():
        raise FileExistsError('choose a new report output path')
    corpus=load_corpus(DATA/'intents.json')
    music=json.loads((DATA/'music.json').read_text())
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    start=time.monotonic()
    encoder=Encoder(work/'model',work/'embeddings.sqlite3')
    startup_ms=(time.monotonic()-start)*1000
    try:
        report={'version':1,'scope':'Read-only authored text experiments, not microphone or physical-player acceptance',
                'model':encoder.info,'pipeline_signature':encoder.signature,
                'platform':{'system':platform.system(),'release':platform.release(),'machine':platform.machine()},
                'intent':await evaluate(corpus,encoder)}
        if args.with_retrieval:
            from research.disc_assistant.assistant.nlu.evaluation.retrieval import evaluate as retrieval_evaluate
            report['retrieval']=await retrieval_evaluate(music,encoder)
        # Explicit uncached single-query probes after warmup, not batch/cached timings.
        samples=[r['text'] for r in corpus['cases'] if r['split']=='test'][:12]
        encoder.encode(['Warmup'],cached=False)
        latencies=[]
        for text in samples:
            tick=time.monotonic();encoder.encode([text],cached=False)
            latencies.append((time.monotonic()-tick)*1000)
        latency=sorted(latencies)
        report['resources']={'encoder_startup_ms':round(startup_ms,3),'verified_model_load_ms':encoder.load_ms,
                             'model_files_bytes':encoder.model_bytes,'encoded_texts':encoder.encoded,'cache_hits':encoder.cache_hits,
                             'warm_uncached_query_count':len(samples),
                             'warm_uncached_query_p50_ms':round(latency[math.ceil(.5*len(latency))-1],3),
                             'warm_uncached_query_p95_ms':round(latency[math.ceil(.95*len(latency))-1],3),
                             'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if platform.system()=='Darwin' else 1024),
                             'total_ms':round((time.monotonic()-start)*1000,3)}
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
        print(json.dumps({'report':str(output),'intent':{locale:{name:value['test'] for name,value in entry['variants'].items()} for locale,entry in report['intent']['locales'].items()},
                          'retrieval':{name:entry['test'] for name,entry in report.get('retrieval',{}).get('variants',{}).items()},
                          'resources':report['resources']},ensure_ascii=False,indent=2))
    finally:
        encoder.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','evaluate'))
    parser.add_argument('--work',type=Path,required=True,help='External model/cache directory')
    parser.add_argument('--output',type=Path,help='New report file, required for evaluate')
    parser.add_argument('--with-retrieval',action='store_true',help='Start and remove disposable Typesense; requires local Docker image')
    args=parser.parse_args()
    if args.command=='evaluate' and args.output is None:parser.error('evaluate requires --output')
    asyncio.run(run(args))


if __name__=='__main__':main()
