"""Shared training/inference features and portable JSON linear classifier."""
from collections import Counter
import math
import re
import unicodedata

VERSION = 'word-char-tfidf-v1'


def counts(text):
    text = ' '.join(unicodedata.normalize('NFC', text).casefold().split())
    tokens = re.findall(r'[^\W_]+', text)
    features = Counter('w:'+token for token in tokens)
    features.update('b:'+a+' '+b for a,b in zip(tokens,tokens[1:]))
    for token in tokens:
        padded = ' '+token+' '
        for size in (2,3,4,5):
            features.update('c:'+padded[i:i+size] for i in range(max(0,len(padded)-size+1)))
    return features


def vector(text, vocabulary, idf):
    observed = counts(text)
    values = {i:observed[word]*idf[i] for i,word in enumerate(vocabulary) if word in observed}
    norm = math.sqrt(sum(v*v for v in values.values()))
    return {i:v/norm for i,v in values.items()} if norm else {}


def classify(text, model):
    values = vector(text,model['vocabulary'],model['idf'])
    logits = [bias+sum(weights[i]*v for i,v in values.items()) for weights,bias in zip(model['weights'],model['bias'])]
    exp = [math.exp(v-max(logits)) for v in logits]
    scores = [v/sum(exp) for v in exp]
    order = sorted(range(len(scores)),key=lambda i:(-scores[i],model['classes'][i]))
    first,second = order[:2]
    return {'label':model['classes'][first],'score':scores[first],
            'margin':scores[first]-scores[second],'runner_up':model['classes'][second],
            'accepted':bool(values) and scores[first]>=model['threshold'] and scores[first]-scores[second]>=model['margin'],
            'score_kind':'softmax score; not calibrated confidence'}
