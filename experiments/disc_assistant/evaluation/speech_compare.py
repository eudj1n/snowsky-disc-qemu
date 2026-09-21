"""Replay saved synthetic WAVs through CLI/resident STT, with and without hints."""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import statistics
import time
from experiments.disc_assistant.assistant.voice.backends import WhisperCpp
from experiments.disc_assistant.assistant.voice.resident import WhisperServer
from experiments.disc_assistant.assistant.voice.files import load_audio, command_text
from experiments.disc_assistant.assistant.voice.vocabulary import prompt
from experiments.disc_assistant.assistant.speech import SpeechContext
from experiments.disc_assistant.assistant.nlu.interpreter import interpret_request, InterpretationContext, UnsupportedCommand

# Fixed catalog names, independent of any sample's expected transcript or slots.
VOCABULARY = ('Linkin Park', 'Numb', 'Meteora', 'In the End', 'Hybrid Theory', 'Артист Ё', 'Тишина', 'Альбом', 'Cue Artist', 'Cue entry')


async def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    settings=dict(model=str(args.model),whisper_executable=str(args.executable),server_url=args.server,timeout=120)
    variants=[('cli',WhisperCpp(settings),()),('resident',WhisperServer(settings),()),('resident-hints',WhisperServer(settings),VOCABULARY)]
    cases=[]
    for locale in ('ru','en'):
        manifest=json.loads((args.samples/locale/'manifest.json').read_text())
        for case in manifest['cases']:
            audio=load_audio(args.samples/locale/case['file'])
            if hashlib.sha256(audio.data).hexdigest()!=case['sha256']:
                raise ValueError('sample fingerprint changed')
            cases.append((locale,case,audio))
    records=[]
    for repeat in range(2):
        for locale,case,audio in cases:
            for name,provider,vocabulary in variants:
                started=time.perf_counter()
                try:
                    result=await provider.transcribe(audio,SpeechContext(locale,'comparison',vocabulary))
                    elapsed=round((time.perf_counter()-started)*1000,3)
                    text=command_text(result.text)
                    try:
                        intent=await interpret_request(text,InterpretationContext(locale))
                        actual={'status':'recognized','intent':asdict(intent)}
                    except UnsupportedCommand:
                        actual={'status':'unsupported'}
                    except ValueError:
                        actual={'status':'unrecognized'}
                    record=dict(text=result.text,actual=actual,correct=actual==case['expected'],stt_ms=elapsed)
                except Exception as exc:
                    record=dict(error_type=type(exc).__name__,correct=False,stt_ms=round((time.perf_counter()-started)*1000,3))
                row=dict(repeat=repeat,locale=locale,case=case['id'],variant=name,audio_sha256=case['sha256'],expected=case['expected'],**record)
                records.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    report={'scope':'examined synthetic STT + interpreter regression, no device execution',
            'model':variants[0][1].evidence(),'server_model_binding':'operator launched same model; endpoint does not attest it',
            'vocabulary_sha256':hashlib.sha256(prompt(VOCABULARY).encode()).hexdigest(),
            'decoder':'CPU, beam_size=5, best_of=5, temperature=0, no fallback, no token timestamps',
            'server_startup':'excluded; first request separate in rows, repeat 1 is warm',
            'summary':{name: {'correct':sum(r['correct'] for r in records if r['variant']==name),
                             'total':sum(r['variant']==name for r in records),
                             'median_ms':round(statistics.median(r['stt_ms'] for r in records if r['variant']==name),3)}
                       for name,_,_ in variants}, 'rows':records}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('samples','model','executable','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--server',default='http://127.0.0.1:18119/inference')
    asyncio.run(run(p.parse_args()))

if __name__=='__main__':main()
