"""Offline acceptance tests for the human-selected literature review workflow."""
import os
os.environ['MOCK_MODE']='1'
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from langgraph.types import Command
from graph import build_graph
from papers import normalize_paper
from projects import project_json, load_project, exports, export_project
from runtime import BudgetExceeded
import workflow as w
import review_workflow as review


class LiteratureReviewWorkflow(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app=build_graph()
        self.config={'configurable':{'thread_id':self.id()},'recursion_limit':100}
        self.initial={'topic':'retrieval evidence','language':'zh','settings':{'cache_dir':self.directory.name,'initial_supplement_rounds':0}}

    def start(self):
        self.app.invoke(self.initial,self.config)
        return self.app.get_state(self.config).values

    def confirm(self, ids=None, pdfs=None):
        state=self.app.get_state(self.config).values
        ids=set(ids if ids is not None else [p['paper_id'] for p in state['paper_decisions'][:1]])
        from directions import relevant_papers
        decisions={p['paper_id']:{'decision':'keep' if p['paper_id'] in ids else 'exclude','reason':'explicit fixture decision'} for p in relevant_papers(state)}
        self.app.invoke(Command(resume={'action':'confirm','decisions':decisions,'local_pdfs':pdfs or {}}),self.config)
        current=self.app.get_state(self.config)
        if current.interrupts and current.interrupts[0].value['kind']=='directions' and current.values.get('direction_options'):
            self.app.invoke(Command(resume={'action':'generate','selected_ids':[d['direction_id'] for d in current.values['direction_options']]}),self.config)
        return self.app.get_state(self.config).values

    def resume(self, response):
        self.app.invoke(Command(resume=response),self.config)
        return self.app.get_state(self.config).values

    def test_no_download_or_evidence_before_human_selection(self):
        with patch('documents.prepare_document') as prepare:
            state=self.start()
        prepare.assert_not_called()
        self.assertNotIn('evidence',state)
        self.assertEqual(state.get('search_round',0),0)
        self.assertEqual(self.app.get_state(self.config).interrupts[0].value['kind'],'papers')
        with patch('documents.prepare_document',wraps=__import__('documents').prepare_document) as prepare:
            state=self.confirm()
        self.assertEqual(prepare.call_count,1)
        self.assertEqual(len(state['approved_paper_ids']),1)
        self.assertTrue(all(e['paper_id'] in state['approved_paper_ids'] for e in state['evidence']))

    def test_default_inclusion_and_explicit_direction_selection(self):
        self.start()
        state=self.resume({'action':'confirm','decisions':{}})
        self.assertEqual(state['review_action'],'confirm')
        self.assertNotIn('outline',state)
        self.assertEqual(self.app.get_state(self.config).interrupts[0].value['kind'],'directions')
        state=self.resume({'action':'generate','selected_ids':[d['direction_id'] for d in state['direction_options']]})
        self.assertEqual(self.app.get_state(self.config).interrupts[0].value['kind'],'outline')
        self.assertNotIn('outline_acceptance',state)
        state=self.resume({'action':'accept'})
        self.assertEqual(state['outline_acceptance'],'accepted_partial')
        self.assertFalse(self.app.get_state(self.config).interrupts)
        self.assertNotEqual(state['citation_check'],'passed')

    def test_machine_rejection_override_requires_reason(self):
        p=normalize_paper({'title':'Rejected fixture','abstract':'retrieval evidence'})
        p.update(relevance_status='rejected',screen_fingerprint='s')
        base={'topic':'retrieval','paper_decisions':[p]}
        for reason,expected in (('', 'review'),('important counterexample','review')):
            with patch.object(review,'interrupt',return_value={'action':'confirm','decisions':{p['paper_id']:{'decision':'keep','reason':reason}}}):
                result=review.review_papers(base)
            self.assertEqual(result['review_action'],expected)
            self.assertEqual(p['relevance_status'],'rejected')

    def test_card_missing_fields_and_no_invented_abstract_pages(self):
        self.start()
        state=self.confirm()
        self.assertEqual(len(state['evidence_cards']),1)
        card=state['evidence_cards'][0]
        self.assertEqual(card['fields']['method']['status'],'not_checked')
        self.assertEqual(card['fields']['method']['text'],'')
        self.assertEqual(card['evidence_level'],'abstract')
        self.assertEqual(card['support_status'],'not_checked')
        self.assertTrue(all(e.get('page_start') is None for e in card['excerpts']))
        self.assertIn('abstract; no page',state['final_report'])
        self.assertEqual(state['outline_checks']['coherence'],'not_checked')

    def test_manual_gap_search_preserves_prior_decisions_and_new_is_unapproved(self):
        self.start()
        before=self.confirm()
        self.assertEqual(before.get('search_round',0),0)
        version=before['corpus_version']
        state=self.resume({'action':'search','gap_ids':['corpus_size']})
        self.assertEqual(state['search_round'],1)
        self.assertEqual(state['corpus_version'],version)
        self.assertEqual(state['human_decisions'],before['human_decisions'])
        self.assertEqual(state['outline'],before['outline'])
        self.assertEqual(state['collected_papers'],before['collected_papers'])
        restored=load_project(project_json(state))
        self.assertEqual(restored['resume_stage'],'papers')
        new=[p for p in state['paper_decisions'] if p['paper_id'] not in before['human_decisions']]
        self.assertTrue(new)
        self.assertTrue(all(p['paper_id'] not in state['approved_paper_ids'] for p in new))
        self.assertEqual(self.app.get_state(self.config).interrupts[0].value['kind'],'papers')

    def test_invalid_gap_and_search_budget_never_auto_accept(self):
        self.start()
        self.confirm()
        state=self.resume({'action':'search','gap_ids':['invented']})
        self.assertEqual(state['outline_action'],'review')
        state=self.app.get_state(self.config).values
        state['search_round']=state['settings']['max_search_rounds']
        with patch.object(review,'interrupt',return_value={'action':'search','gap_ids':['corpus_size']}):
            update=review.review_outline(state)
        self.assertEqual(update['outline_action'],'review')
        self.assertNotIn('outline_acceptance',update)

    def test_edited_text_and_order_survive_supplementary_search(self):
        self.start()
        before=self.confirm()
        edited=copy.deepcopy(before['outline'])
        edited['nodes'][0]['title']='用户自己的综述范围'
        edited['nodes'][0]['order']=9
        state=self.resume({'action':'edit','outline':edited})
        self.assertEqual(state['outline_version'],2)
        self.assertTrue(state['outline']['nodes'][0]['user_edited'])
        self.resume({'action':'search','gap_ids':['corpus_size']})
        state=self.confirm(before['approved_paper_ids'])
        node=next(n for n in state['outline']['nodes'] if n['node_id']=='section_introduction')
        self.assertEqual(node['title'],'用户自己的综述范围')
        self.assertEqual(node['order'],9)
        self.assertTrue(state['outline_history'])

    def test_unknown_citations_rejected_without_overwriting_draft(self):
        self.start()
        before=self.confirm()
        edited=copy.deepcopy(before['outline'])
        edited['nodes'][3]['argument_points'][0]['evidence_ids']=['e_invented']
        state=self.resume({'action':'edit','outline':edited})
        self.assertEqual(state['outline'],before['outline'])
        self.assertEqual(state['outline_version'],before['outline_version'])
        self.assertTrue(state['review_error'])

    def test_removed_paper_invalidates_user_text_citations_and_keeps_wording(self):
        state=self.start()
        ids=[p['paper_id'] for p in state['paper_decisions']]
        state=self.confirm(ids)
        edited=copy.deepcopy(state['outline'])
        node=edited['nodes'][3]
        point=node['argument_points'][0]
        point['text']='保留的用户比较观点'
        removed=next(e['paper_id'] for e in state['evidence'] if e['evidence_id']==point['evidence_ids'][0])
        retained=[pid for pid in ids if pid!=removed]
        self.resume({'action':'edit','outline':edited})
        self.resume({'action':'papers'})
        state=self.confirm(retained)
        node=next(n for n in state['outline']['nodes'] if n['node_id']==node['node_id'])
        point=next(p for p in node['argument_points'] if p['text']=='保留的用户比较观点')
        self.assertEqual(point['kind'],'user_idea')
        self.assertEqual(point['evidence_ids'],[])
        self.assertTrue(point['needs_evidence'])
        self.assertEqual(node['status'],'needs_material')
        self.assertTrue(state['corpus_history'])

    def test_export_restore_in_fresh_graph_preserves_budget_and_gate(self):
        self.start()
        state=self.confirm()
        state['telemetry']['requests']=79
        raw=project_json(state)
        restored=load_project(raw)
        fresh=build_graph()
        config={'configurable':{'thread_id':'fresh'}}
        with patch('nodes.create_client') as client:
            fresh.invoke(restored,config)
        client.assert_not_called()
        actual=fresh.get_state(config)
        self.assertEqual(actual.interrupts[0].value['kind'],'outline')
        self.assertEqual(actual.values['telemetry']['requests'],79)
        self.assertEqual(actual.values['outline'],state['outline'])
        self.assertEqual(actual.values['local_pdfs'],{})
        target=export_project(Path(self.directory.name)/'export',state)
        self.assertEqual({p.name for p in target.iterdir()},{'outline.md','evidence_cards.csv','paper_decisions.csv','project.json'})
        self.assertIn('原文证据', (target/'outline.md').read_text(encoding='utf-8'))
        self.assertIn('human_decision',(target/'paper_decisions.csv').read_text(encoding='utf-8-sig'))

    def test_invalid_project_and_credential_serialization_rejected(self):
        self.start()
        state=self.confirm()
        for location in ('top','nested'):
            bad=copy.deepcopy(state)
            bad['human_decisions']['api_key' if location=='top' else 'fixture']={'api_key':'fixture-secret'}
            with self.assertRaises(ValueError):
                project_json(bad)
        data=json.loads(project_json(state))
        data['state']['evidence'][0]['paper_id']='unknown'
        with self.assertRaises(ValueError): load_project(json.dumps(data))
        data=json.loads(project_json(state))
        data['state']['outline']['nodes'][3]['argument_points'][0]['evidence_ids']=['unknown']
        with self.assertRaises(ValueError): load_project(json.dumps(data))

    def test_card_validator_rejects_unknown_ids_and_unchecked_claims(self):
        empty={f:{'status':'not_checked','text':'','evidence_ids':[]} for f in review.CARD_FIELDS}
        bad=copy.deepcopy(empty)
        bad['findings']={'status':'found','text':'invented','evidence_ids':['unknown']}
        with self.assertRaises(ValueError): review.validate_card(bad,[])
        bad=copy.deepcopy(empty)
        bad['method']['text']='invented method'
        with self.assertRaises(ValueError): review.validate_card(bad,[])

    def test_fulltext_local_pdf_location_and_document_reuse(self):
        state=self.start()
        pid=state['paper_decisions'][0]['paper_id']
        state=self.confirm([pid],{pid:str(Path('tests/fixtures/original_cc0.pdf').resolve())})
        self.assertEqual(state['evidence_cards'][0]['evidence_level'],'fulltext')
        self.assertTrue(any(e.get('page_start') for e in state['evidence']))
        self.resume({'action':'papers'})
        with patch('documents.prepare_document') as prepare:
            state=self.confirm([pid])
        prepare.assert_not_called()
        self.assertTrue(state['document_events'][0]['session_reuse'])

    def test_restore_fulltext_then_reconfirm_reuses_portable_text(self):
        state=self.start()
        pid=state['paper_decisions'][0]['paper_id']
        before=self.confirm([pid],{pid:str(Path('tests/fixtures/original_cc0.pdf').resolve())})
        restored=load_project(project_json(before))
        fresh=build_graph()
        config={'configurable':{'thread_id':'restored-pdf'}}
        fresh.invoke(restored,config)
        fresh.invoke(Command(resume={'action':'papers'}),config)
        with patch('documents.prepare_document') as prepare:
            fresh.invoke(Command(resume={'action':'confirm','decisions':{}}),config)
        prepare.assert_not_called()
        state=fresh.get_state(config).values
        self.assertEqual(state['corpus_version'],before['corpus_version'])
        self.assertEqual(state['evidence_cards'][0]['evidence_level'],'fulltext')

    def test_changed_metadata_does_not_reuse_human_inclusion(self):
        state=self.start()
        state=self.confirm()
        papers=copy.deepcopy(state['paper_decisions'])
        kept=state['approved_paper_ids'][0]
        next(p for p in papers if p['paper_id']==kept)['screen_fingerprint']='changed-content'
        with patch.object(review,'interrupt',return_value={'action':'confirm','decisions':{}}):
            result=review.review_papers({**state,'paper_decisions':papers})
        self.assertEqual(result['review_action'],'confirm')
        self.assertEqual(result['human_decisions'][kept]['screen_fingerprint'],'changed-content')

    def test_fulltext_budget_is_shared_across_corpus_changes(self):
        self.initial['settings']['max_fulltexts']=1
        state=self.start()
        ids=[p['paper_id'] for p in state['paper_decisions']]
        state=self.confirm(ids[:1],{ids[0]:str(Path('tests/fixtures/original_cc0.pdf').resolve())})
        self.assertEqual(state['telemetry']['fulltext_attempts'],1)
        self.resume({'action':'papers'})
        state=self.confirm(ids[1:2],{ids[1]:str(Path('tests/fixtures/original_cc0.pdf').resolve())})
        self.assertEqual(state['telemetry']['fulltext_attempts'],1)
        self.assertEqual(state['document_events'][0]['reason'],'fulltext_budget_exhausted')
        self.assertEqual(state['evidence_cards'][0]['evidence_level'],'abstract')

    def test_metadata_only_does_not_consume_fulltext_attempt_budget(self):
        state=self.start()
        pid=next(p['paper_id'] for p in state['paper_decisions'] if not p.get('open_access_url'))
        state=self.confirm([pid])
        self.assertEqual(state['telemetry']['fulltext_attempts'],0)

    def test_changed_processed_content_updates_corpus_version(self):
        from documents import chunks_from_pages
        from settings import Settings
        self.start()
        before=self.confirm()
        changed=copy.deepcopy(before)
        changed['document_cache']={}
        p=changed['collected_papers'][0]
        chunks=chunks_from_pages(p['paper_id'],['Changed retrieval evidence in the processed abstract.'],Settings.load(changed['settings']),'abstract')
        with patch('documents.prepare_document',return_value=(chunks,{'paper_id':p['paper_id'],'evidence_level':'abstract'})):
            update=review.prepare_approved_evidence(changed)
        self.assertNotEqual(update['corpus_version'],before['corpus_version'])
        self.assertTrue(update['corpus_history'])

    def test_candidates_outside_model_shortlist_remain_visible(self):
        papers=[normalize_paper({'title':str(i),'abstract':'retrieval evidence'}) for i in range(25)]
        with patch.object(w,'_embedding_shortlist',return_value=papers[:20]):
            result=w.process_papers({'topic':'retrieval','candidate_papers':papers})
        self.assertEqual(len(result['paper_decisions']),25)
        self.assertEqual(sum(p['relevance_reason']=='outside model screening shortlist' for p in result['paper_decisions']),5)

    def test_streamlit_edit_search_reconfirm_and_export(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file('streamlit_app.py',default_timeout=30).run()
        app.text_input(key='research_topic_input').set_value('retrieval evidence')
        app.button(key='start_research').click().run()
        app.button(key='continue_research').click().run()
        self.assertEqual(app.session_state['interrupt_payload']['kind'],'directions')
        for control in app.checkbox:
            if control.key and control.key.startswith('direction_choice_'):
                control.check()
        app.button(key='generate_selected_outline').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['interrupt_payload']['kind'],'outline')
        title=next(c for c in app.text_input if c.key and c.key.startswith('node_') and c.key.endswith('section_introductiontitle'))
        title.set_value('用户编辑的综述结构')
        app.button(key='apply_outline_edits').click().run()
        self.assertFalse(app.exception)
        next(c for c in app.multiselect if c.key and c.key.startswith('gap_selection_2_')).select('corpus_size').run()
        app.button(key='supplement_search').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['interrupt_payload']['kind'],'papers')
        app.button(key='continue_research').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['interrupt_payload']['kind'],'directions')
        app.button(key='generate_selected_outline').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['interrupt_payload']['kind'],'outline')
        self.assertTrue(any(n['title']=='用户编辑的综述结构' for n in app.session_state['interrupt_payload']['outline']['nodes']))
        app.button(key='accept_outline').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['phase'],'done')
        self.assertEqual(len(app.get('download_button')),4)

    def test_model_budget_failure_preserves_partial_outline_truthfully(self):
        self.start()
        state=self.confirm()
        with patch.object(w,'is_mock',return_value=False), patch.object(w,'ask',side_effect=BudgetExceeded('fixture')):
            update=review.generate_outline(state)
            checked=review.check_outline({**state,**update})
        self.assertEqual(update['outline_error'],'outline_generation_failed:BudgetExceeded')
        self.assertEqual(checked['citation_check'],'needs_review')
        self.assertTrue(any(n['writing_support']['source_notes'] for n in checked['outline']['nodes']))
        self.assertTrue(checked['gap_list'])
        self.assertGreaterEqual(len(checked['outline']['nodes']),7)

    def test_incremental_screening_preserves_valid_decisions_on_failure(self):
        papers=[normalize_paper({'title':t,'abstract':'retrieval evidence','year':2024}) for t in ('A','B')]
        with patch.object(w,'screen',return_value=[{**papers[0],'relevance_status':'accepted','relevance_reason':'match','question_ids':['q1']} ]):
            first=w.process_papers({'topic':'retrieval','candidate_papers':papers[:1]})
        with patch.object(w,'screen',return_value=[{**papers[1],'relevance_status':'unjudged','relevance_reason':'budget','question_ids':[]}]) as screen:
            next_state=w.process_papers({'topic':'retrieval','candidate_papers':papers,**first})
        self.assertEqual(len(screen.call_args.args[1]),1)
        self.assertEqual(next(p for p in next_state['paper_decisions'] if p['paper_id']==papers[0]['paper_id'])['relevance_status'],'accepted')

    def test_partial_screen_batch_keeps_valid_items(self):
        papers=[normalize_paper({'title':t,'abstract':'retrieval'}) for t in ('A','B')]
        data=[{'paper_id':papers[0]['paper_id'],'relevant':True,'reason':'match','question_ids':['q1']}, {'paper_id':papers[1]['paper_id'],'relevant':'yes'}]
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=[data,BudgetExceeded('fixture')]):
            result=w.screen('retrieval',papers,'en',[{'question_id':'q1'}],{})
        self.assertEqual(result[0]['relevance_status'],'accepted')
        self.assertEqual(result[1]['relevance_status'],'unjudged')

    def test_title_entities_unicode_and_doi_link(self):
        raw={'title':'A &amp; B: <i>α</i> &lt; β, cafe\u0301 [test]','doi':'10.1234/title'}
        p=normalize_paper(raw)
        self.assertEqual(p['title'],'A & B: α < β, café [test]')
        self.assertEqual(p['raw_title'],raw['title'])
        self.assertEqual(p['landing_url'],'https://doi.org/10.1234/title')
        self.assertEqual(normalize_paper(p)['paper_id'],p['paper_id'])

    def test_bm25_fallback_works_without_model_weights(self):
        self.start()
        state=self.confirm()
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'_get_embedder',side_effect=OSError('offline')):
            update=review.prepare_approved_evidence(state)
        self.assertTrue(update['evidence'])
        self.assertEqual(update['retrieval_trace'][0]['mode'],'bm25_fallback')


if __name__=='__main__':
    unittest.main()
