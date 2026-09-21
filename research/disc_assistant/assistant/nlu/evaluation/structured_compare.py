"""Compare local structured evidence with rules/slots; never open device/runtime data."""
import argparse
import asyncio
import json
from pathlib import Path
import statistics
from research.disc_assistant.assistant.nlu.command_catalog import digest
from research.disc_assistant.assistant.nlu.interpretation_sources import LiteralSource, SlotSource, collect
from research.disc_assistant.assistant.nlu.structured_source import StructuredSource, PROMPT, SCHEMA
from research.disc_assistant.assistant.nlu.interpreter import InterpretationContext
from research.disc_assistant.assistant.nlu.understanding import single_action


async def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    original=json.loads((Path(__file__).parents[1]/'data/slot_acceptance.json').read_text())
    extra=json.loads((Path(__file__).parents[1]/'data/structured_cases.json').read_text())
    cases=[*original['cases'],*extra['cases']]
    # Preserve original gold and report the owner's earlier title ambiguity review.
    cases=[{**c, 'gold_review':'disputed_music_title_negative'} if c['id'] in ('ru-negative-3','en-negative-3') else c for c in cases]
    source=StructuredSource(dict(endpoint=args.endpoint,model=args.model,model_path=str(args.model_path),timeout=10))
    rows=[]
    for case in cases:
        context=InterpretationContext(case['locale'])
        results=await collect(case['text'],context,(LiteralSource(),SlotSource(),source),timeout_ms=12000)
        policy=single_action(case['text'],case['locale'])
        # Keep raw sources as evidence; compare actual live rules including the gate.
        live={**results[0],'source':'live_rules'}
        if not policy['supported']:live.update(status='unsupported',intent=None)
        results.append(live)
        row={**case,'results':results,'policy':policy}
        rows.append(row)
        print(json.dumps({'id':case['id'],'model_status':results[2]['status'],'intent':results[2]['intent']},ensure_ascii=False),flush=True)
    summary={}
    for name in ('live_rules','slots','structured_model'):
        summary[name]={}
        for locale in ('ru','en'):
            group=[(r,v) for r in rows if r['locale']==locale for v in r['results'] if v['source']==name]
            positives=[(r,v) for r,v in group if r['intent'] is not None]
            negatives=[(r,v) for r,v in group if r['intent'] is None]
            summary[name][locale]={'positive_total':len(positives),'exact_intents':sum(v['status']=='recognized' and v['intent']==r['intent'] for r,v in positives),
                'negative_total':len(negatives),'false_activations':sum(v['status']=='recognized' for _,v in negatives),
                'unavailable':sum(v['status']=='unavailable' for _,v in group),
                'invalid_output':sum(v.get('provenance',{}).get('failure_kind')=='invalid_output' for _,v in group),
                'undisputed_negative_total':sum('gold_review' not in r for r,_ in negatives),
                'undisputed_false_activations':sum(v['status']=='recognized' for r,v in negatives if 'gold_review' not in r),
                'median_ms':round(statistics.median(v['elapsed_ms'] for _,v in group),3)}
    report={'scope':'examined synthetic source regression; no learned execution or physical acceptance',
            'prompt_sha256':digest(PROMPT),'schema_sha256':digest(SCHEMA),'corpus_sha256':digest(cases),
            'summary':summary,'rows':rows}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--endpoint',default='http://127.0.0.1:18120/v1/chat/completions')
    p.add_argument('--model',default='disc-commands')
    p.add_argument('--model-path',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    asyncio.run(run(p.parse_args()))

if __name__=='__main__':main()
