"""Offline regressions for the concise literature -> multi-select -> outline experience."""
import os
os.environ['MOCK_MODE']='1'
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from langgraph.types import Command
from graph import build_graph, is_sufficient
from papers import normalize_paper
from projects import project_json, load_project
from runtime import BudgetExceeded
import directions as d
import workflow as w
import review_workflow as review


class DirectionSelection(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app=build_graph()
        self.config={'configurable':{'thread_id':self.id()},'recursion_limit':100}
        self.app.invoke({'topic':'retrieval evidence','language':'zh','settings':{'cache_dir':self.temp.name}},self.config)

    def state(self):
        return self.app.get_state(self.config).values

    def resume(self,value):
        self.app.invoke(Command(resume=value),self.config)
        return self.state()

    def directions(self):
        return self.resume({'action':'confirm'})

    def test_result_payload_hides_rejected_and_unjudged(self):
        state=self.state()
        papers=state['paper_decisions']
        self.assertTrue(any(p.get('relevance_status')=='unjudged' for p in papers))
        payload=self.app.get_state(self.config).interrupts[0].value
        self.assertEqual(len(payload['papers']),2)
        self.assertTrue(all(p['relevance_status']=='demo_unjudged' for p in payload['papers']))
        self.assertNotIn('请审核论文与约束',payload['literature_summary'])
        self.assertNotIn('摘要缺失不可作为结论证据',payload['literature_summary'])
        self.assertNotIn(papers[0]['title'],payload['literature_summary'])

    def test_substantively_related_is_accepted_but_inconsistent_labels_are_not(self):
        papers=[normalize_paper({'title':x,'abstract':'A useful method for retrieval evidence'}) for x in ('Related method','Inconsistent result')]
        data=[{'paper_id':p['paper_id'],'relevant':True,'match_type':'related' if i==0 else 'irrelevant','reason':'method connection','question_ids':['q1']} for i,p in enumerate(papers)]
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',return_value=data):
            result=w.screen('retrieval',papers,'en',[{'question_id':'q1'}],{})
        self.assertEqual(result[0]['relevance_status'],'accepted')
        self.assertEqual(result[0]['match_type'],'related')
        self.assertEqual(result[1]['relevance_status'],'unjudged')

    def test_ending_before_direction_selection_is_not_an_approved_outline(self):
        self.directions()
        state=self.resume({'action':'end'})
        self.assertEqual(state['citation_check'],'not_applicable')
        self.assertEqual(state['outline_acceptance'],'ended')
        self.assertNotIn('outline',state)
        self.assertIn('MOCK / DEMO',state['final_report'])

    def test_initial_search_is_bounded_and_manual_search_remains_available(self):
        self.assertEqual(self.state()['search_round'],1)
        payload=self.app.get_state(self.config).interrupts[0].value
        self.assertTrue(payload['can_search'])
        state=self.resume({'action':'search'})
        self.assertEqual(state['search_round'],2)
        self.assertFalse(self.app.get_state(self.config).interrupts[0].value['can_search'])
        state=self.resume({'action':'search'})
        self.assertEqual(state['review_action'],'review')
        self.assertNotIn('outline',state)
        self.assertEqual(is_sufficient({'retrieval_status':'insufficient_evidence','results_shown':True}),'summarize_literature')

    def test_default_inclusion_and_no_download_before_direction_choice(self):
        with patch('documents.prepare_document') as doc:
            state=self.directions()
        doc.assert_not_called()
        self.assertEqual(self.app.get_state(self.config).interrupts[0].value['kind'],'directions')
        self.assertEqual(len(state['direction_options']),5)
        self.assertEqual(len(state['approved_paper_ids']),2)
        self.assertTrue(all(x['decision']=='keep' for x in state['human_decisions'].values()))
        self.assertNotIn('outline',state)

    def test_remove_a_paper_excludes_it_from_all_direction_sources(self):
        paper=self.app.get_state(self.config).interrupts[0].value['papers'][0]
        state=self.resume({'action':'confirm','decisions':{paper['paper_id']:{'decision':'exclude','reason':''}}})
        self.assertEqual(len(state['approved_paper_ids']),1)
        self.assertTrue(all(paper['paper_id'] not in x['paper_ids'] for x in state['direction_options']))
        self.assertTrue(all(e['paper_id']!=paper['paper_id'] for e in state['direction_evidence']))

    def test_removal_survives_search_and_updated_metadata(self):
        p=self.app.get_state(self.config).interrupts[0].value['papers'][0]
        state=self.resume({'action':'search','decisions':{p['paper_id']:{'decision':'exclude','reason':''}}})
        state['paper_decisions']=copy.deepcopy(state['paper_decisions'])
        next(x for x in state['paper_decisions'] if x['paper_id']==p['paper_id'])['screen_fingerprint']='changed-source'
        with patch.object(review,'interrupt',return_value={'action':'confirm'}):
            result=review.review_papers(state)
        self.assertEqual(result['human_decisions'][p['paper_id']]['decision'],'exclude')
        self.assertTrue(all(x['paper_id']!=p['paper_id'] for x in result['collected_papers']))

    def test_invalid_or_empty_direction_choice_never_generates_outline(self):
        self.directions()
        for ids in ([],['invented'],['d_demo_1','d_demo_1']):
            with patch('documents.prepare_document') as doc:
                state=self.resume({'action':'generate','selected_ids':ids})
            doc.assert_not_called()
            self.assertEqual(state['direction_action'],'review')
            self.assertNotIn('outline',state)

    def test_multi_select_produces_one_outline_covering_exact_selected_directions(self):
        state=self.directions()
        selected=[x['direction_id'] for x in state['direction_options'][1:3]]
        state=self.resume({'action':'generate','selected_ids':selected})
        self.assertEqual(self.app.get_state(self.config).interrupts[0].value['kind'],'outline')
        self.assertEqual(state['selected_direction_ids'],selected)
        themes=[n for n in state['outline']['nodes'] if n.get('parent_id')=='section_themes']
        self.assertEqual({q for n in themes for q in n['question_ids']},set(selected))
        self.assertEqual(len(themes),2)
        self.assertTrue(all(e['question_id'] in selected or e['question_id'] is None for e in state['evidence']))

    def test_direction_sources_and_mapping_are_strict(self):
        state=self.directions()
        self.assertEqual(d.validate_directions(copy.deepcopy(state['direction_options']),state),state['direction_options'])
        for key,value in (('paper_ids',['invented']),('evidence_ids',['invented'])):
            bad=copy.deepcopy(state['direction_options'])
            bad[0][key]=value
            with self.assertRaises(ValueError):d.validate_directions(bad,state)
        bad=copy.deepcopy(state['direction_options'])
        bad[1]['direction_id']=bad[0]['direction_id']
        with self.assertRaises(ValueError):d.validate_directions(bad,state)

    def test_real_direction_failure_has_no_template_or_mock_success(self):
        state=self.directions()
        state['direction_source_version']='force-refresh'
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=BudgetExceeded('fixture')):
            result=d.suggest_directions(state)
        self.assertEqual(result['direction_status'],'unavailable')
        self.assertEqual(result['direction_options'],[])
        self.assertIn('BudgetExceeded',result['direction_error'])

    def test_fewer_than_five_supported_options_are_not_padded(self):
        state=self.directions()
        state['direction_source_version']='force-refresh'
        one=[copy.deepcopy(state['direction_options'][0])]
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',return_value={'directions':one}):
            result=d.suggest_directions(state)
        self.assertEqual(result['direction_status'],'partial')
        self.assertEqual(len(result['direction_options']),1)

    def test_restore_at_direction_gate_does_not_repeat_model_calls(self):
        state=self.directions()
        state['telemetry']['model_calls']=12
        restored=load_project(project_json(state))
        fresh=build_graph(); cfg={'configurable':{'thread_id':'restored-directions'}}
        with patch('nodes.create_client') as client,patch.object(w,'ask') as ask:
            fresh.invoke(restored,cfg)
        client.assert_not_called();ask.assert_not_called()
        self.assertEqual(fresh.get_state(cfg).interrupts[0].value['kind'],'directions')
        self.assertEqual(fresh.get_state(cfg).values['telemetry']['model_calls'],12)

    def test_direction_restore_after_removing_previously_used_paper(self):
        state=self.directions()
        self.resume({'action':'generate','selected_ids':[d['direction_id'] for d in state['direction_options']]})
        self.resume({'action':'papers'})
        removed=self.state()['approved_paper_ids'][0]
        state=self.resume({'action':'confirm','decisions':{removed:{'decision':'exclude','reason':''}}})
        restored=load_project(project_json(state))
        self.assertEqual(restored['resume_stage'],'directions')
        self.assertTrue(restored['pending_outline'])
        self.assertTrue(all(e['paper_id']!=removed for e in restored['evidence']))
        fresh=build_graph();cfg={'configurable':{'thread_id':'changed-corpus'}}
        fresh.invoke(restored,cfg)
        self.assertEqual(fresh.get_state(cfg).interrupts[0].value['kind'],'directions')

    def test_tampered_direction_project_is_rejected(self):
        state=self.directions()
        data=json.loads(project_json(state))
        data['state']['direction_evidence'][0]['text']='tampered'
        with self.assertRaises(ValueError):load_project(json.dumps(data))
        data=json.loads(project_json(state))
        data['state']['direction_options'][0]['paper_ids']=['unknown']
        with self.assertRaises(ValueError):load_project(json.dumps(data))

    def test_compact_outline_omits_diagnostics_and_raw_passages(self):
        state=self.directions()
        state=self.resume({'action':'generate','selected_ids':[state['direction_options'][0]['direction_id']]})
        compact=review.render_outline(state,detailed=False)
        self.assertIn(state['selected_directions'][0]['title'],compact)
        self.assertNotIn('corpus:',compact)
        self.assertNotIn('Original evidence and locations',compact)
        self.assertNotIn('```json',compact)
        self.assertIn('https://',compact)

    def test_compact_references_contain_only_used_sources(self):
        state=self.directions()
        state=self.resume({'action':'generate','selected_ids':[state['direction_options'][0]['direction_id']]})
        state=copy.deepcopy(state)
        state['collected_papers'].append(normalize_paper({'title':'Unused catalog entry','url':'https://example.org/unused'}))
        compact=review.render_outline(state,detailed=False)
        self.assertNotIn('Unused catalog entry',compact)
        self.assertNotIn('https://example.org/unused',compact)

    def test_legacy_summary_is_not_shown_in_result_payload(self):
        state=self.state()
        state['literature_summary']='请审核论文与约束；摘要缺失不可作为结论证据。 OLD VERBOSE PAPER CONTENT'
        with patch.object(review,'interrupt',return_value={'action':'end'}) as pause:
            review.review_papers(state)
        self.assertNotIn('OLD VERBOSE',pause.call_args.args[0]['literature_summary'])

    def test_web_defaults_removal_multi_select_and_clean_outline(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file('streamlit_app.py',default_timeout=30).run()
        app.text_input(key='research_topic_input').set_value('retrieval evidence')
        app.button(key='start_research').click().run()
        self.assertFalse(app.exception)
        controls=[c for c in app.checkbox if c.key and c.key.startswith('include_')]
        self.assertEqual(len(controls),2)
        self.assertTrue(all(c.value for c in controls))
        visible=' '.join(str(x.value) for x in app.markdown)
        self.assertNotIn('请审核论文与约束',visible)
        self.assertNotIn('摘要缺失不可作为结论证据',visible)
        controls[-1].uncheck().run()
        app.button(key='continue_research').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['interrupt_payload']['papers']),1)
        self.assertTrue(app.button(key='generate_selected_outline').disabled)
        choices=[c for c in app.checkbox if c.key and c.key.startswith('direction_choice_')]
        self.assertEqual(len(choices),5)
        choices[0].check();choices[2].check()
        app.button(key='generate_selected_outline').click().run()
        self.assertFalse(app.exception)
        payload=app.session_state['interrupt_payload']
        self.assertEqual(payload['kind'],'outline')
        self.assertEqual(len([n for n in payload['outline']['nodes'] if n.get('parent_id')=='section_themes']),2)
        visible=' '.join(str(x.value) for x in app.markdown)
        self.assertNotIn('corpus:',visible)
        self.assertNotIn('原文证据与位置 / Original evidence',visible)


if __name__=='__main__':unittest.main()
