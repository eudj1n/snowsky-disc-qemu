import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock

from research.disc_assistant.experiments.nlu.encoder import VectorCache, digest
from research.disc_assistant.experiments.nlu.intents import load_corpus, accepted, calibrate, metrics
from research.disc_assistant.experiments.nlu.retrieval import Retrieval

PACKAGE = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def test_frozen_corpus_has_separate_splits_and_valid_spans(self):
        corpus=load_corpus(PACKAGE/'intents.json')
        self.assertEqual(len(corpus['cases']),182)
        data=copy.deepcopy(corpus)
        data['cases'][1]['text']=data['cases'][0]['text']
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'corpus.json';path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'leak'):
                load_corpus(path)

    def test_threshold_calibration_minimizes_false_activation_before_recall(self):
        rows=[{'label':'pause'},{'label':'reject'}]
        evidence=[{'label':'pause','score':.65,'margin':.1},
                  {'label':'pause','score':.8,'margin':.1}]
        selected=calibrate(rows,evidence)
        predictions=[accepted(e,selected['threshold'],selected['margin']) for e in evidence]
        self.assertEqual(predictions,['reject','reject'])
        self.assertEqual(selected['development']['false_activations'],0)
        # Rule-first fallback cannot hide an existing rules false positive.
        selected=calibrate(rows,evidence,['pause','play'])
        self.assertEqual(selected['development']['false_activations'],1)

    def test_metrics_separate_wrong_actions_false_activation_and_rejection(self):
        result=metrics([{'label':l} for l in ['pause','next','reject','play']],['resume','reject','play','play'])
        self.assertEqual(result['false_activations'],1)
        self.assertEqual(result['correct_commands'],1)
        self.assertEqual(result['rejected_commands'],1)
        self.assertEqual(result['confusion']['pause']['resume'],1)

    def test_cache_reuses_only_matching_pipeline_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'vectors.db'
            a=VectorCache(path,'model-a',2);b=VectorCache(path,'model-b',2)
            try:
                a.put('text',[1.,0.])
                self.assertEqual(a.get('text'),[1.,0.])
                self.assertIsNone(b.get('text'))
                self.assertIsNone(a.get('different'))
                for invalid in ([1.],[0.,0.],[float('nan'),0.],[True,0.]):
                    with self.assertRaises(ValueError):a.put('bad',invalid)
                a.db.execute('UPDATE vectors SET value=? WHERE text_hash=?',('[0,0]',digest('text')))
                a.db.commit()
                with self.assertRaises(ValueError):a.get('text')
            finally:
                a.close();b.close()


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_vector_errors_and_foreign_snapshot_hits_fail_instead_of_fallback(self):
        base=Mock(signature='sig');client=Mock()
        client.multi_search.perform=AsyncMock(return_value={'results':[{'error':'failed'}]})
        encoder=Mock();encoder.encode.return_value=[Mock(tolist=lambda:[1.,0.])]
        search=Retrieval(base,client,'isolated',{},encoder,'hybrid')
        search.semantic_query='Тишина'
        with self.assertRaisesRegex(ValueError,'incomplete'):
            await search.search(Mock(),'test','tishina')
        encoder.encode.assert_called_once_with(['Тишина'])
        params=client.multi_search.perform.call_args.args[0]['searches'][0]
        self.assertEqual(params['q'],'tishina')
        client.multi_search.perform.return_value={'results':[{'found':1,'hits':[{'document':{'id':'foreign'}}]}]}
        with self.assertRaisesRegex(ValueError,'pinned'):
            await search.search(Mock(),'test','query')
