"""Explicit model preparation and local-only embeddings with versioned cache."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time

MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
REVISION = 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'
FILES = ['config.json', 'config_sentence_transformers.json', 'modules.json',
         'sentence_bert_config.json', '1_Pooling/config.json', 'model.safetensors',
         'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json',
         'sentencepiece.bpe.model', 'unigram.json']


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def prepare(directory):
    from huggingface_hub import snapshot_download
    directory = Path(directory).expanduser().resolve()
    snapshot_download(MODEL, revision=REVISION, local_dir=directory, allow_patterns=FILES)
    metadata = {'model': MODEL, 'revision': REVISION, 'files': file_hashes(directory)}
    (directory / 'disc-model.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return metadata


def file_hashes(directory):
    result = {}
    for name in FILES:
        with (directory / name).open('rb') as stream:
            result[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result


class VectorCache:
    """Text+pipeline identities; no pickle, no cross-model vector reuse."""
    def __init__(self, path, signature, dimensions):
        self.signature, self.dimensions = signature, dimensions
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS vectors (pipeline TEXT, text_hash TEXT, value TEXT, PRIMARY KEY(pipeline,text_hash))')

    def validate(self, value):
        import math
        if (not isinstance(value, list) or len(value) != self.dimensions or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in value) or
                abs(sum(v*v for v in value) - 1) > .002):
            raise ValueError('invalid cached embedding')
        return value

    def get(self, text):
        row = self.db.execute('SELECT value FROM vectors WHERE pipeline=? AND text_hash=?',
                              (self.signature, digest(text))).fetchone()
        return None if row is None else self.validate(json.loads(row[0]))

    def put(self, text, value):
        value = self.validate(value)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?)',
                            (self.signature, digest(text), json.dumps(value)))

    def close(self):
        self.db.close()


class Encoder:
    def __init__(self, directory, cache_path):
        import importlib.metadata
        import torch
        from sentence_transformers import SentenceTransformer
        start = time.monotonic()
        directory = Path(directory).expanduser().resolve()
        metadata = json.loads((directory / 'disc-model.json').read_text())
        if metadata != {'model': MODEL, 'revision': REVISION, 'files': file_hashes(directory)}:
            raise ValueError('model files changed; prepare the pinned model again')
        torch.set_num_threads(4)
        self.model = SentenceTransformer(str(directory), device='cpu', local_files_only=True,
                                         trust_remote_code=False, model_kwargs={'use_safetensors': True})
        self.info = {**metadata, 'normalize': True, 'device': 'cpu', 'threads': 4,
                     'max_sequence_length': self.model.max_seq_length,
                     'dimensions': self.model.get_sentence_embedding_dimension(),
                     'versions': {name: importlib.metadata.version(name) for name in
                                  ('sentence-transformers', 'torch', 'transformers', 'numpy', 'scikit-learn', 'typesense')}}
        self.signature = digest(self.info)
        self.cache = VectorCache(cache_path, self.signature, self.info['dimensions'])
        self.load_ms = round((time.monotonic()-start)*1000, 3)
        self.model_bytes = sum((directory / name).stat().st_size for name in FILES)
        self.encoded, self.cache_hits = 0, 0

    def encode(self, texts, *, cached=True):
        import numpy as np
        values = [self.cache.get(text) if cached else None for text in texts]
        missing = sorted({text for text, value in zip(texts, values) if value is None})
        self.cache_hits += sum(value is not None for value in values)
        if missing:
            vectors = self.model.encode(missing, batch_size=32, show_progress_bar=False,
                                        normalize_embeddings=True, convert_to_numpy=True)
            lookup = {text: vector.tolist() for text, vector in zip(missing, vectors)}
            self.encoded += len(missing)
            for text, vector in lookup.items():
                self.cache.validate(vector)
                if cached:
                    self.cache.put(text, vector)
            values = [value if value is not None else lookup[text] for text, value in zip(texts, values)]
        return np.asarray(values, dtype=np.float32)

    def close(self):
        self.cache.close()
