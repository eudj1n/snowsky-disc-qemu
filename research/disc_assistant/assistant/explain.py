"""Diagnostic interpretation only. Never registered as an executing provider."""
from dataclasses import asdict
import re

from research.disc_assistant.assistant.command_catalog import CommandCatalog
from research.disc_assistant.assistant.command_features import classify
from research.disc_assistant.assistant.intents import parse, language_target, Intent, ControlIntent, LanguageIntent
from research.disc_assistant.assistant.interpreter import validate_intent
from research.disc_assistant.assistant.languages import load_languages, normalized


def label_of(intent):
    return (intent.action if type(intent) is ControlIntent else 'play' if type(intent) is Intent
            else 'language' if type(intent) is LanguageIntent else 'reject')


def template_value(text, templates, placeholder):
    for template in templates:
        prefix,suffix = template.split('{'+placeholder+'}')
        pattern = (r'\s*'+re.escape(prefix).replace(r'\ ',r'\s+')+
                   r'(?P<value>.+?)'+re.escape(suffix).replace(r'\ ',r'\s+')+r'\s*')
        match = re.fullmatch(pattern,text,re.IGNORECASE)
        if match:
            start,end = match.span('value')
            return match['value'], {'name':placeholder,'start':start,'end':end,'text':text[start:end]}
    return None


def blocked(text, patterns):
    if text.lstrip().startswith(tuple(patterns['quotes'])):
        return 'quoted_command'
    for category in ('negation','reported'):
        if any(re.search(r'(?<!\w)'+re.escape(p)+r'(?!\w)',text,re.IGNORECASE) for p in patterns[category]):
            return 'negated_command' if category=='negation' else 'reported_or_explanatory_text'
    return None


def decide(text, authored, classifier=None):
    if not isinstance(text,str) or not 1<=len(text)<=1000 or any(ord(c)<32 for c in text):
        raise ValueError('explain needs 1..1000 characters without control characters')
    rules = load_languages((authored['locale'],))
    try:
        baseline = parse(text,rules)
    except ValueError:
        baseline = None
    prediction = classify(text,classifier) if classifier else None
    intent, reason, origin, spans = None, 'unrecognized', 'guarded_rules', []
    patterns = authored['patterns']
    music = template_value(text,patterns['play'],'query')
    language = template_value(text,patterns['language'],'language')
    # A clearly delimited music reference may itself contain a command or negation.
    controls = {normalized(row['text']):row['label'] for row in authored['examples']
                if row['label'] in ('pause','resume','stop','next','previous')}
    negatives = {normalized(row['text']) for row in authored['examples'] if row['label']=='reject'}
    if normalized(text) in negatives:
        reason = 'authored_negative_example'
    elif normalized(text) in controls:
        intent = ControlIntent(controls[normalized(text)])
        reason = 'authored_control_example'
    elif music:
        value, span = music
        spans = [span]
        if normalized(value) in {normalized(v) for v in patterns['empty_music']}:
            reason = 'empty_music_request'
        else:
            prefix = next(p for p,action in rules.commands if action=='play')
            intent = parse(prefix+' '+value,rules)
            reason = 'music_reference_extracted'
    elif language:
        value, span = language
        spans = [span]
        try:
            intent = LanguageIntent(language_target(value,rules))
            reason = 'language_argument_extracted'
        except ValueError:
            reason = 'unsupported_language_argument'
    elif (rejection := blocked(text,patterns)):
        reason = rejection
    elif baseline is not None:
        intent, reason = baseline, 'literal_rule'
    else:
        if prediction:
            origin = 'linear_classifier'
            if not prediction['accepted']:
                reason = 'below_acceptance_threshold'
            elif prediction['label']=='reject':
                reason = 'classifier_rejected'
            elif prediction['label'] in ('play','language'):
                reason = 'missing_music_reference' if prediction['label']=='play' else 'missing_language_argument'
            else:
                intent = ControlIntent(prediction['label'])
                reason = 'classified_control'
    if intent is not None:
        validate_intent(intent)
    status = 'recognized' if intent is not None else 'incomplete' if reason.startswith('missing_') else 'rejected'
    return {'rules':{'label':label_of(baseline),'intent':asdict(baseline) if baseline else None},
            'candidate':{'status':status,'label':label_of(intent),'intent':asdict(intent) if intent else None,
                         'source':origin,'reason':reason,'spans':spans},
            'classifier':prediction or {'status':'unavailable','reason':'no trained command snapshot imported'}}


def preview(config, text, trace=None):
    catalog = CommandCatalog(config.data_dir)
    try:
        snapshot = catalog.current(config.locale)
        result = {'status':'explained','locale':config.locale,'text':text,'snapshot':snapshot['id'],
                  'source_hash':snapshot['source_hash'],'mutation_attempted':False,
                  **decide(text,snapshot['source'],snapshot['classifier'])}
        if trace:
            trace.event('explain',result)
        return result
    finally:
        catalog.close()
