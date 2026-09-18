"""Command snapshots, portable inference and non-executing explanation boundaries."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from research.disc_assistant.assistant import __main__ as cli
from research.disc_assistant.assistant.command_catalog import CommandCatalog, LABELS, digest, source, command
from research.disc_assistant.assistant.command_features import VERSION, classify, counts
from research.disc_assistant.assistant.config import load
from research.disc_assistant.assistant.console import Application
from research.disc_assistant.assistant.explain import decide
from research.disc_assistant.assistant.journal import Trace, history_command
from research.disc_assistant.assistant.preferences import language_command
from research.disc_assistant.experiments.nlu.train_commands import validate_splits


def model(label='pause'):
    return {'kind':'linear-text-v1', 'feature_version':VERSION, 'classes':list(LABELS),
            'vocabulary':['w:hold'], 'idf':[1.], 'weights':[[10. if name==label else 0.] for name in LABELS],
            'bias':[0.]*len(LABELS), 'threshold':.8, 'margin':.2}


def bundle(locale='en'):
    authored=source(locale)
    pipeline={'dimensions':2, 'model':'unit-fixture', 'revision':'fixed'}
    return {'version':1, 'locale':locale, 'source_hash':digest(authored), 'classifier':model(),
            'embedding':{'dimensions':2, 'pipeline':pipeline, 'signature':digest(pipeline)},
            'vectors':{row['id']:[1.,0.] for row in authored['examples']}}


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.path=self.root/'config.toml'
        self.path.write_text(f'[device]\nkey="fixture"\nhost="127.0.0.1"\n'
                             f'[storage]\ndata_dir="{self.root}/data"\n[language]\nlocale="en"\n')
        self.config=load(self.path)
        self.catalog=CommandCatalog(self.config.data_dir)
        self.addCleanup(self.catalog.close)

    def test_publication_is_idempotent_and_locales_are_independent(self):
        english=self.catalog.current('en')
        russian=self.catalog.current('ru')
        self.assertNotEqual(english['id'],russian['id'])
        self.assertEqual(self.catalog.publish('en')['id'],english['id'])
        trained=self.catalog.publish('en',bundle())
        self.assertNotEqual(trained['id'],english['id'])
        self.assertEqual(self.catalog.current('ru')['id'],russian['id'])
        self.assertEqual(self.catalog.db.execute('SELECT count(*) FROM command_snapshots').fetchone()[0],3)
        vectors=self.catalog.db.execute('SELECT vector_json FROM command_examples WHERE snapshot_id=?',(trained['id'],)).fetchall()
        self.assertTrue(all(json.loads(row[0])==[1.,0.] for row in vectors))
        self.assertEqual(self.catalog.publish('en')['id'],english['id'])
        self.assertFalse(self.catalog.info('en')['classifier'])

    def test_bad_imports_do_not_replace_active_snapshot(self):
        current=self.catalog.publish('en',bundle())['id']
        corruptions=[lambda b:b.update(source_hash='stale'), lambda b:b.update(locale='ru'),
            lambda b:b['vectors'].pop(next(iter(b['vectors']))),
            lambda b:b['vectors'].update({next(iter(b['vectors'])):[float('nan'),0.]}),
            lambda b:b['vectors'].update({next(iter(b['vectors'])):[.5,0.]}),
            lambda b:b['embedding'].update(signature='wrong'),
            lambda b:b['embedding'].update(dimensions=3),
            lambda b:b['classifier'].update(weights=[[0.]]),
            lambda b:b['classifier'].update(threshold=float('inf')),
            lambda b:b['classifier'].update(classes=['shell']),
            lambda b:b['classifier'].update(kind='pickle')]
        for corrupt in corruptions:
            bad=bundle(); corrupt(bad)
            with self.assertRaises(ValueError): self.catalog.publish('en',bad)
            self.assertEqual(self.catalog.current('en')['id'],current)
        self.assertEqual(self.catalog.db.execute('SELECT count(*) FROM command_snapshots').fetchone()[0],1)

    def test_database_failure_rolls_back_complete_publication(self):
        old=self.catalog.current('en')['id']
        self.catalog.db.execute("CREATE TRIGGER fail_head BEFORE UPDATE ON command_heads BEGIN SELECT RAISE(ABORT,'fixture'); END")
        self.catalog.db.commit()
        with self.assertRaises(sqlite3.IntegrityError): self.catalog.publish('en',bundle())
        self.assertEqual(self.catalog.current('en')['id'],old)
        self.assertEqual(self.catalog.db.execute('SELECT count(*) FROM command_snapshots').fetchone()[0],1)

    def test_changed_examples_and_rules_require_explicit_rebuild(self):
        self.catalog.publish('en',bundle())
        for key in ('examples','rules'):
            authored=deepcopy(source('en'))
            if key=='examples': authored['examples'][0]['text']='New phrase'
            else: authored['rules']['fixture']='changed grammar'
            with patch('research.disc_assistant.assistant.command_catalog.source',return_value=authored):
                with self.assertRaisesRegex(ValueError,'stale'): self.catalog.current('en')
                with self.assertRaisesRegex(ValueError,'retrain'): self.catalog.publish('en',bundle())
                self.catalog.publish('en')
                self.assertIsNone(self.catalog.current('en')['classifier'])
            self.catalog.publish('en',bundle())

    def test_v2_migration_preserves_history_and_preferences(self):
        with Trace(self.config,'ask','synthetic') as trace: trace.finish({'status':'planned'})
        language_command(self.config,['ru'])
        for table in ('command_heads','command_examples','command_snapshots'):
            self.catalog.db.execute('DROP TABLE '+table)
        self.catalog.db.execute('PRAGMA user_version=2')
        self.catalog.db.commit()
        reopened=CommandCatalog(self.config.data_dir)
        try:
            self.assertEqual(reopened.db.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertEqual(language_command(self.config)['locale'],'ru')
            self.assertEqual(history_command(self.config)['requests'][0]['id'],trace.id)
            self.assertIsNone(reopened.current('ru')['classifier'])
        finally: reopened.close()

    def test_shared_features_unicode_and_rejection_without_known_features(self):
        self.assertEqual(counts(' CAFÉ  MUSIC '),counts('cafe\u0301 music'))
        self.assertEqual(classify('hold',model())['label'],'pause')
        self.assertTrue(classify('hold',model())['accepted'])
        self.assertFalse(classify('unseen',model())['accepted'])
        conservative=model(); conservative['threshold']=1.01
        self.assertFalse(classify('hold',conservative)['accepted'])

    def test_music_names_keep_negation_control_words_and_original_spans(self):
        for locale,text,query in [('en','Please play song Do Not Disturb','Do Not Disturb'),
                                  ('ru','Пожалуйста включи трек Пауза','Пауза'),
                                  ('ru','Хочу послушать песню Не отпускай','Не отпускай')]:
            result=decide(text,source(locale))['candidate']
            self.assertEqual(result['intent']['query'],query)
            self.assertEqual(result['intent']['kind'],'track')
            span=result['spans'][0]
            self.assertEqual(text[span['start']:span['end']],span['text'])
        self.assertEqual(decide('Play the previous song',source('en'))['candidate']['intent'],{'action':'previous'})

    def test_negation_reported_speech_and_unsupported_language_rejected(self):
        for locale,text in [('en','Do not pause the music'),('en','He said pause the music'),
                            ('en','"Pause"'),('en','Play nothing'),('ru','Не ставь музыку на паузу'),
                            ('ru','Он сказал включи Numb'),('en','Use Martian for commands')]:
            result=decide(text,source(locale),model())['candidate']
            self.assertEqual(result['status'],'rejected',(locale,text,result))
            self.assertIsNone(result['intent'])
        self.assertEqual(decide('Please switch language to Russian',source('en'))['candidate']['intent'],{'locale':'ru'})

    def test_learned_music_or_language_never_invents_missing_arguments(self):
        for label in ('play','language'):
            candidate=decide('hold',source('en'),model(label))['candidate']
            self.assertEqual(candidate['status'],'incomplete')
            self.assertIsNone(candidate['intent'])
        self.assertEqual(decide('hold',source('en'),model())['candidate']['intent'],{'action':'pause'})
        with self.assertRaises(ValueError): decide('pause\nstop',source('en'))

    def invoke(self,*args):
        output=io.StringIO()
        with redirect_stdout(output),redirect_stderr(io.StringIO()):
            code=cli.main(['--config',str(self.path),*args])
        return code,json.loads(output.getvalue())

    def test_cli_and_console_explain_never_execute_search_or_change_language(self):
        app=Application(self.config)
        app.device_call=Mock(side_effect=AssertionError('device'))
        app.interpret=Mock(side_effect=AssertionError('live interpreter'))
        with patch.object(cli,'control',side_effect=AssertionError('control')), \
                patch.object(cli,'execute',side_effect=AssertionError('execute')), \
                patch.object(cli,'create_client',side_effect=AssertionError('search')):
            for text in ('Pause','Switch language to Russian','Play Queen'):
                code,result=self.invoke('explain',text)
                self.assertEqual(code,0)
                self.assertEqual(result['status'],'explained')
                self.assertFalse(result['mutation_attempted'])
                console=app.request('/explain '+text)
                self.assertEqual(console['candidate'],result['candidate'])
                record=history_command(self.config,['show',result['request_id']])
                self.assertIn('explain',[event['phase'] for event in record['events']])
                self.assertNotIn('execution_started',[event['phase'] for event in record['events']])
        self.assertEqual(language_command(self.config)['locale'],'en')
        self.assertFalse((self.config.data_dir/'library.sqlite3').exists())

    def test_command_import_and_rebuild_work_in_cli_and_console(self):
        file=self.root/'model with spaces.json'
        file.write_text(json.dumps(bundle()))
        self.assertEqual(self.invoke('commands','import',str(file))[0],0)
        self.assertTrue(self.invoke('commands')[1]['classifier'])
        app=Application(self.config)
        self.assertFalse(app.request('/commands rebuild')['classifier'])
        self.assertTrue(app.request(f'/commands import "{file}"')['classifier'])
        self.assertEqual(app.request('/explain hold')['candidate']['intent'],{'action':'pause'})
        with self.assertRaises(ValueError): command(self.config,['unexpected'])

    def test_training_splits_do_not_overlap(self):
        root=Path(__file__).parents[2]/'experiments'/'nlu'
        corpus=json.loads((root/'intents.json').read_text())
        challenge=json.loads((root/'command_challenge.json').read_text())
        for locale in ('ru','en'):
            development=[r for r in corpus['cases'] if r['locale']==locale and r['split']=='development']
            regression=[r for r in corpus['cases'] if r['locale']==locale and r['split']=='test']
            fresh=[r for r in challenge['cases'] if r['locale']==locale]
            authored=source(locale)
            validate_splits(authored,development,regression,fresh)
            with self.assertRaisesRegex(ValueError,'duplicate'):
                validate_splits(authored,development,regression,fresh+[authored['examples'][0]])


if __name__=='__main__': unittest.main()
