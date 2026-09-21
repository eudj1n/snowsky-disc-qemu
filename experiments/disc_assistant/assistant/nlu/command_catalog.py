"""Versioned, locale-scoped command references. Publication never executes an intent."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
import tomllib

from experiments.disc_assistant.assistant.database import connect
from experiments.disc_assistant.assistant.nlu.languages import load_languages
from experiments.disc_assistant.assistant.responses import locale_code

LABELS = ('pause', 'resume', 'stop', 'next', 'previous', 'play', 'language', 'reject')
DEFINITIONS = {name: {'required': ['query'] if name == 'play' else ['locale'] if name == 'language' else [],
                      'executable': name != 'reject'} for name in LABELS}
DIRECTORY = Path(__file__).parents[1] / 'locales' / 'commands'
REFERENCES = Path(__file__).parent / 'data/command_references'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def source(locale):
    locale_code(locale)
    rules = asdict(load_languages((locale,)))
    with (DIRECTORY / (locale + '.toml')).open('rb') as stream:
        data = tomllib.load(stream)
    if data.get('version') != 1 or data.get('locale') != locale:
        raise ValueError('command catalog locale/version mismatch')
    patterns = data.get('patterns', {})
    keys = {'play', 'language', 'negation', 'reported', 'empty_music', 'quotes'}
    if not isinstance(patterns, dict) or set(patterns) != keys:
        raise ValueError('incomplete command extraction patterns')
    for key, values in patterns.items():
        if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() or len(v)>300 for v in values):
            raise ValueError('invalid command pattern')
        for value in values:
            placeholder = '{query}' if key == 'play' else '{language}' if key == 'language' else None
            remainder = value.replace(placeholder, '') if placeholder else value
            if '{' in remainder or '}' in remainder or (placeholder and value.count(placeholder) != 1):
                raise ValueError('invalid command template placeholder')
    if set(data) != {'version', 'locale', 'patterns'}:
        raise ValueError('locale command files contain templates only')
    reference_path = REFERENCES / (locale + '.toml')
    examples = []
    if reference_path.exists():
        with reference_path.open('rb') as stream:
            references = tomllib.load(stream)
        if (set(references) != {'version', 'locale', 'examples'}
                or references['version'] != 1 or references['locale'] != locale):
            raise ValueError('command references locale/version mismatch')
        examples = references['examples']
    data = {**data, 'examples': examples}
    seen, texts = set(), set()
    if not isinstance(examples, list) or not 0 <= len(examples) <= 2000:
        raise ValueError('command catalog allows up to 2000 examples')
    for row in examples:
        if (not isinstance(row, dict) or set(row) != {'id','label','text'} or row['label'] not in LABELS
                or not isinstance(row['id'], str)
                or not re.fullmatch(r'[a-z0-9_-]{1,100}', row['id']) or row['id'] in seen
                or not isinstance(row['text'], str) or not 1 <= len(row['text']) <= 1000
                or any(ord(c)<32 for c in row['text'])):
            raise ValueError('invalid command example')
        normalized = ' '.join(row['text'].casefold().split())
        if normalized in texts:
            raise ValueError('duplicate command example text')
        seen.add(row['id']); texts.add(normalized)
    return {**data, 'definitions': DEFINITIONS, 'rules': rules}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_classifier(model):
    from experiments.disc_assistant.assistant.nlu.command_features import VERSION
    if (not isinstance(model, dict) or model.get('kind') != 'linear-text-v1'
            or model.get('feature_version') != VERSION or model.get('classes') != list(LABELS)):
        raise ValueError('unsupported command classifier')
    vocabulary, idf, weights, bias = (model.get(k) for k in ('vocabulary','idf','weights','bias'))
    if (not isinstance(vocabulary,list) or not 1<=len(vocabulary)<=20000
            or any(not isinstance(v,str) or not 1<=len(v)<=200 for v in vocabulary)
            or len(set(vocabulary))!=len(vocabulary) or not isinstance(idf,list) or len(idf)!=len(vocabulary)
            or any(not finite(v) or v<=0 for v in idf) or not isinstance(weights,list) or len(weights)!=len(LABELS)
            or any(not isinstance(w,list) or len(w)!=len(vocabulary) or any(not finite(v) for v in w) for w in weights)
            or not isinstance(bias,list) or len(bias)!=len(LABELS) or any(not finite(v) for v in bias)
            or any(not finite(model.get(k)) or not 0<=model[k]<=1.01 for k in ('threshold','margin'))):
        raise ValueError('invalid command classifier dimensions/values')


class CommandCatalog:
    def __init__(self, directory):
        self.db = connect(directory)

    def close(self):
        self.db.close()

    def publish(self, locale, bundle=None):
        authored = source(locale)
        source_hash = digest(authored)
        payload = {'version':1, 'locale':locale, 'source_hash':source_hash, 'source':authored,
                   'classifier':None, 'embedding':None}
        vectors = {}
        if bundle is not None:
            if (not isinstance(bundle, dict) or bundle.get('version') != 1 or bundle.get('locale') != locale
                    or bundle.get('source_hash') != source_hash):
                raise ValueError('command model does not match current locale/source; retrain')
            validate_classifier(bundle.get('classifier'))
            embedding = bundle.get('embedding')
            if (not isinstance(embedding,dict) or type(embedding.get('dimensions')) is not int
                    or not 1<=embedding['dimensions']<=4096 or not isinstance(embedding.get('pipeline'),dict)
                    or embedding['pipeline'].get('dimensions') != embedding['dimensions']
                    or embedding.get('signature') != digest(embedding['pipeline'])):
                raise ValueError('invalid embedding provenance')
            vectors = bundle.get('vectors', {})
            if not isinstance(vectors,dict) or set(vectors) != {r['id'] for r in authored['examples']}:
                raise ValueError('embedding example IDs differ from command references')
            for vector in vectors.values():
                if (not isinstance(vector,list) or len(vector)!=embedding['dimensions']
                        or any(not finite(v) for v in vector) or abs(sum(v*v for v in vector)-1)>.002):
                    raise ValueError('invalid command reference vector')
            payload.update(classifier=bundle['classifier'], embedding=embedding)
        snapshot = digest({'payload':payload,'vectors':vectors})
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO command_snapshots(id,locale,source_hash,payload_json) VALUES (?,?,?,?)',
                            (snapshot,locale,source_hash,json.dumps(payload,ensure_ascii=False)))
            self.db.executemany('INSERT OR IGNORE INTO command_examples VALUES (?,?,?,?,?)',
                [(snapshot,r['id'],r['label'],r['text'],json.dumps(vectors[r['id']]) if r['id'] in vectors else None)
                 for r in authored['examples']])
            self.db.execute('INSERT INTO command_heads VALUES (?,?) ON CONFLICT(locale) DO UPDATE SET snapshot_id=excluded.snapshot_id',
                            (locale,snapshot))
        return self.current(locale)

    def current(self, locale):
        row = self.db.execute('SELECT s.id,s.payload_json FROM command_snapshots s JOIN command_heads h ON s.id=h.snapshot_id WHERE h.locale=?',
                              (locale,)).fetchone()
        if row is None:
            return self.publish(locale)
        payload = json.loads(row[1])
        if payload['source_hash'] != digest(source(locale)):
            raise ValueError('command catalog is stale; use commands rebuild, then retrain/import the optional classifier')
        return {'id':row[0], **payload}

    def info(self, locale):
        snapshot = self.current(locale)
        return {'locale':locale,'snapshot':snapshot['id'],'source_hash':snapshot['source_hash'],
                'example_count':len(snapshot['source']['examples']),
                'negative_count':sum(r['label']=='reject' for r in snapshot['source']['examples']),
                'classifier':snapshot['classifier'] is not None,'embedding':snapshot['embedding'],
                'scope':'explain preview only; live interpreter unchanged'}


def command(config, arguments):
    catalog = CommandCatalog(config.data_dir)
    try:
        if not arguments:
            return catalog.info(config.locale)
        if arguments == ['rebuild']:
            catalog.publish(config.locale)
        elif len(arguments)==2 and arguments[0]=='import':
            with Path(arguments[1]).expanduser().open('rb') as stream:
                data = stream.read(16*1024*1024+1)
            if len(data)>16*1024*1024:
                raise ValueError('command model bundle exceeds 16 MiB')
            bundle = json.loads(data)
            if not isinstance(bundle,dict):
                raise ValueError('command model bundle must be an object')
            catalog.publish(config.locale,bundle)
        else:
            raise ValueError('use commands [rebuild|import FILE]')
        return catalog.info(config.locale)
    finally:
        catalog.close()
