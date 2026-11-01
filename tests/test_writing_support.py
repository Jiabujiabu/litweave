"""Original synthetic source text only; no research result or paid request."""
import os
os.environ['MOCK_MODE']='1'
import copy
import json
import unittest
from unittest.mock import patch
from documents import chunks_from_pages
from papers import normalize_paper
from settings import Settings
from projects import project_json,load_project
from runtime import BudgetExceeded
from writing_support import ALL_FIELDS,CORE_FIELDS,empty_field,build_support,validate_support,attach_support,render_support
import workflow as w
import review_workflow as review


def synthetic_material_state():
    records=[
        {'research_question':'How does retrieval support document question answering?',
         'object_conditions':'English document question answering.',
         'method':'Retrieve complete documents, then generate an answer from the retrieved context.',
         'data':'Synthetic Alpha dataset: 40 questions.',
         'evaluation_metrics':'Answer accuracy: the fraction of answers marked correct.',
         'findings':'Reported answer accuracy was 0.75 on Synthetic Alpha.',
         'limitations':'Only English questions were tested.'},
        {'research_question':'Can reranking passages reduce factual errors in document answers?',
         'object_conditions':'Document answers over a synthetic internal corpus.',
         'method':'Retrieve passages, rerank them, then generate an answer with passage citations.',
         'data':'Synthetic Beta dataset: 80 questions.',
         'evaluation_metrics':'Fact error rate: the fraction of answers containing an annotated factual error.',
         'findings':'Reported fact error rate was 0.12 on Synthetic Beta.'}
    ]
    state={'topic':'检索支持的文档问答','language':'zh','demo_mode':True,'corpus_version':'synthetic-corpus','settings':{'fulltext':False},
        'research_plan':{'core_constraints':['document question answering'],'questions':[{'question_id':'q1','text':'document question answering','query':'document question answering'}]},
        'collected_papers':[],'evidence':[],'chunks':[],'evidence_cards':[], 'outline_version':1, 'citation_check':'not_checked'}
    for i,fields in enumerate(records):
        text=' '.join(fields.values())
        p=normalize_paper({'title':'合成文献 '+('A' if i==0 else 'B'),'authors':['Synthetic fixture'],'abstract':text,'year':2024,
            'url':'https://example.org/synthetic-study-'+str(i+1), 'open_access_url':'https://example.org/synthetic-study-2.pdf' if i else None})
        level='abstract' if i==0 else 'fulltext'
        chunks=chunks_from_pages(p['paper_id'],[text] if i==0 else ['',text],Settings(),level)
        c=chunks[0]
        # All text is short enough to remain in the first chunk.
        e={**c,'evidence_id':'synthetic_e'+str(i),'original_text':c['text'],'question_id':'d_methods'}
        values={f:empty_field() for f in ALL_FIELDS}
        for f,value in fields.items():
            values[f]={'status':'found','text':value,'evidence_ids':[e['evidence_id']],'kind':'author_finding'}
        if i==1:values['limitations']={'status':'not_found_in_processed_text','text':'','evidence_ids':[]}
        p['evidence_level']=level
        state['collected_papers'].append(p);state['evidence'].append(e);state['chunks'].extend(chunks)
        state['evidence_cards'].append({'card_id':'synthetic_card'+str(i),'paper_id':p['paper_id'],'corpus_version':state['corpus_version'],
            'fields':values,'excerpts':[e],'evidence_level':level,'support_status':'not_checked','error':'','provenance':'synthetic_fixture'})
    state['approved_paper_ids']=[p['paper_id'] for p in state['collected_papers']]
    state['corpus_signatures']={p['paper_id']:'synthetic-signature-'+str(i) for i,p in enumerate(state['collected_papers'])}
    state['selected_directions']=[{'direction_id':'d_methods','title':'方法与评价的比较','question':'如何组织检索方法与评价条件的比较？','search_query':'retrieval methods evaluation',
        'paper_ids':state['approved_paper_ids'],'evidence_ids':[],'description':'Organize reported methods and evaluation settings.'}]
    state['selected_direction_ids']=['d_methods'];state['selected_scope_version']='synthetic-methods'
    return state


class WritingMaterial(unittest.TestCase):
    def setUp(self):
        self.state=synthetic_material_state()
        self.outline=review.skeleton(self.state)

    def node(self,kind):
        return next(n for n in self.outline['nodes'] if n['section_type']==kind)

    def test_introduction_identifies_actual_question_population_and_data(self):
        support=build_support(self.node('introduction'),self.state)
        texts=[n['text'] for n in support['source_notes']]
        self.assertIn('English document question answering.',texts)
        self.assertIn('Synthetic Alpha dataset: 40 questions.',texts)
        self.assertTrue(all(n['evidence_ids'] for n in support['source_notes']))
        self.assertIn(self.state['topic'],self.node('introduction')['purpose'])

    def test_comparison_is_filled_with_methods_data_metrics_and_findings(self):
        support=build_support(self.node('themes'),self.state)
        self.assertEqual(len(support['comparison_rows']),2)
        self.assertIn('rerank',support['comparison_rows'][1]['cells']['method']['text'])
        self.assertIn('40 questions',support['comparison_rows'][0]['cells']['data']['text'])
        self.assertIn('Answer accuracy',support['comparison_rows'][0]['cells']['evaluation_metrics']['text'])
        self.assertIn('Fact error rate',support['comparison_rows'][1]['cells']['evaluation_metrics']['text'])
        self.assertIn('method',{a['dimension'] for a in support['comparison_axes']})

    def test_child_uses_only_its_linked_papers(self):
        child=copy.deepcopy(self.outline['nodes'][-1])
        state=copy.deepcopy(self.state)
        state['selected_directions'][0]['paper_ids']=state['approved_paper_ids'][:1]
        support=build_support(child,state)
        self.assertEqual(len(support['comparison_rows']),1)
        self.assertTrue(all(n['paper_id']==state['approved_paper_ids'][0] for n in support['source_notes']))

    def test_missing_and_unchecked_fields_remain_distinct(self):
        state=copy.deepcopy(self.state)
        state['evidence_cards'][0]['fields']['limitations']=empty_field()
        support=build_support(self.node('themes'),state)
        self.assertEqual(support['comparison_rows'][0]['cells']['limitations']['status'],'not_checked')
        self.assertEqual(support['comparison_rows'][1]['cells']['limitations']['status'],'not_found_in_processed_text')
        self.assertTrue(all(n['field']!='limitations' for n in support['source_notes']))

    def test_unsupported_material_is_not_displayed_as_an_author_finding(self):
        node=copy.deepcopy(self.node('themes'))
        node['writing_support']=build_support(node,self.state)
        method=next(n for n in node['writing_support']['source_notes'] if n['field']=='method')
        state={**self.state,'claim_checks':[{'claim_id':method['note_id'],'status':'unsupported'}]}
        rendered='\n'.join(render_support(node,state,lambda ids:'[source]',str))
        self.assertNotIn(method['text'],rendered)
        self.assertIn('当前引文支持不足',rendered)

    def test_partial_support_is_explained_without_showing_check_code(self):
        node=copy.deepcopy(self.node('introduction'))
        node['writing_support']=build_support(node,self.state)
        first=node['writing_support']['source_notes'][0]
        state={**self.state,'claim_checks':[{'claim_id':first['note_id'],'status':'partially_supported'}]}
        rendered='\n'.join(render_support(node,state,lambda ids:'[source]',str))
        self.assertIn('引文仅部分支持，需核对范围',rendered)
        self.assertNotIn('partially_supported',rendered)

    def test_source_locations_and_comparison_boundaries_render_without_code(self):
        state=copy.deepcopy(self.state)
        state['outline']=attach_support(copy.deepcopy(self.outline),state)
        rendered=review.render_outline(state,detailed=False)
        self.assertIn('可直接用于本节的文献内容',rendered)
        self.assertIn('PDF 第 2 页',rendered)
        self.assertIn('摘要',rendered)
        self.assertIn('#page=2',rendered)
        self.assertIn('| 方法与实施流程 | 数据与实验设置 | 评价指标 |',rendered)
        self.assertIn('现有提取尚未核实数值结果是否可直接横向比较',rendered)
        self.assertIn('0.75',rendered);self.assertIn('0.12',rendered)
        self.assertNotIn('根据证据补充比较、转折与个人判断',rendered)
        self.assertNotIn('```json',rendered)
        self.assertNotIn('B is better',rendered)

    def test_uploaded_pdf_page_is_not_linked_to_a_different_remote_pdf(self):
        state=copy.deepcopy(self.state)
        state['outline']=attach_support(self.outline,state)
        state['document_events']=[{'paper_id':state['approved_paper_ids'][1],'source_url':'local_pdf'}]
        rendered=review.render_outline(state,detailed=False)
        self.assertIn('PDF 第 2 页',rendered)
        self.assertNotIn('synthetic-study-2.pdf#page=2',rendered)
        self.assertIn('https://example.org/synthetic-study-2',rendered)

    def test_identical_study_tables_are_not_repeated_per_direction(self):
        state=copy.deepcopy(self.state)
        state['outline']=attach_support(self.outline,state)
        rendered=review.render_outline(state,detailed=False)
        self.assertEqual(rendered.count('**文献对照**'),2)
        self.assertIn('本节使用前面文献对照表中的同一组研究',rendered)

    def test_legacy_boilerplate_is_replaced_when_displaying_saved_outlines(self):
        state=copy.deepcopy(self.state)
        state['outline']=copy.deepcopy(self.outline)
        state['outline']['nodes'][0].update(purpose='围绕研究问题组织证据，明确可写内容与缺口。',user_writing_tasks=['根据证据补充比较、转折与个人判断。'])
        rendered=review.render_outline(state,detailed=False)
        self.assertNotIn('围绕研究问题组织证据',rendered)
        self.assertNotIn('根据证据补充比较',rendered)
        self.assertIn(self.state['topic'],rendered)

    def test_generated_personal_stance_and_homework_are_not_added(self):
        draft=copy.deepcopy(self.outline)
        draft['nodes'][0]['argument_points']=[{'point_id':'opinion','text':'My preferred method is always best.','kind':'hypothesis','evidence_ids':[],'required_level':'abstract'}]
        draft['nodes'][0]['user_writing_tasks']=['Write your personal judgment here.']
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',return_value=draft):
            result=review.generate_outline(self.state)
        self.assertEqual(result['outline_error'],'')
        self.assertFalse(result['outline']['nodes'][0]['argument_points'])
        self.assertFalse(result['outline']['nodes'][0]['user_writing_tasks'])

    def test_budget_failure_keeps_concrete_source_material(self):
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',side_effect=BudgetExceeded('fixture')):
            result=review.generate_outline(self.state)
        self.assertEqual(result['outline_error_category'],'budget_exhausted')
        state={**self.state,**result}
        rendered=review.render_outline(state,detailed=False)
        self.assertIn('Synthetic Alpha dataset: 40 questions.',rendered)
        self.assertIn('0.75',rendered)
        self.assertIn('章节综合尚未完成',rendered)
        self.assertFalse(any(n['user_writing_tasks'] for n in result['outline']['nodes']))

    def test_whitelist_and_same_paper_mapping_are_enforced(self):
        support=build_support(self.node('themes'),self.state)
        validate_support(support,self.state)
        for key,value in (('evidence_ids',['unknown']),('paper_id',self.state['approved_paper_ids'][1]),('required_level','fulltext')):
            bad=copy.deepcopy(support);bad['source_notes'][0][key]=value
            with self.assertRaises(ValueError):validate_support(bad,self.state)

    def test_invalid_card_citation_is_not_used_for_material(self):
        state=copy.deepcopy(self.state)
        state['evidence_cards'][0]['fields']['method']['evidence_ids']=['unknown']
        support=build_support(self.node('themes'),state)
        self.assertEqual(support['comparison_rows'][0]['cells']['method']['status'],'not_checked')
        self.assertTrue(all(n['field']!='method' or n['paper_id']!=state['approved_paper_ids'][0] for n in support['source_notes']))

    def test_legacy_six_field_cards_get_explicit_unchecked_extra_fields(self):
        fields={k:copy.deepcopy(self.state['evidence_cards'][0]['fields'][k]) for k in CORE_FIELDS}
        validated=review.validate_card(fields,self.state['evidence'])
        self.assertEqual(validated['data']['status'],'not_checked')
        self.assertEqual(validated['evaluation_metrics']['status'],'not_checked')
        self.assertEqual(validated['method']['status'],'found')

    def test_one_invalid_extracted_field_does_not_erase_valid_findings(self):
        raw=copy.deepcopy(self.state['evidence_cards'][0]['fields'])
        raw['method']['evidence_ids']=['unknown']
        state=copy.deepcopy(self.state);state['collected_papers']=state['collected_papers'][:1];state['evidence_cards']=[]
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',return_value=raw):
            result=review.extract_evidence_cards(state)
        card=result['evidence_cards'][0]
        self.assertEqual(card['fields']['method']['status'],'not_checked')
        self.assertEqual(card['fields']['findings']['status'],'found')
        self.assertEqual(card['fields']['data']['status'],'found')
        self.assertIn('method',card['error'])

    def test_repeated_material_is_checked_once_per_unique_statement(self):
        state=copy.deepcopy(self.state)
        state['outline']=attach_support(self.outline,state)
        with patch.object(w,'is_mock',return_value=False),patch.object(w,'ask',return_value={'status':'supported','reason':'synthetic fixture only','contradiction':False}) as ask:
            result=review.check_outline(state)
        unique={json.dumps({k:n[k] for k in ('text','evidence_ids','kind','required_level')},sort_keys=True) for node in state['outline']['nodes'] for n in node['writing_support']['source_notes'] if n['kind']=='author_finding'}
        self.assertEqual(ask.call_count,len(unique))
        self.assertGreater(len(result['claim_checks']),ask.call_count)
        self.assertTrue(all(c['claim_id'] for c in result['claim_checks']))

    def test_project_roundtrip_and_unknown_material_citations_rejected(self):
        state=copy.deepcopy(self.state)
        state['outline']=attach_support(self.outline,state);state['project_phase']='outline'
        restored=load_project(project_json(state))
        self.assertEqual(restored['outline']['nodes'][0]['writing_support']['source_notes'][0]['text'],state['outline']['nodes'][0]['writing_support']['source_notes'][0]['text'])
        raw=json.loads(project_json(state))
        raw['state']['outline']['nodes'][0]['writing_support']['source_notes'][0]['evidence_ids']=['unknown']
        with self.assertRaises(ValueError):load_project(json.dumps(raw))

    def test_stale_material_is_rebuilt_when_a_paper_is_removed(self):
        previous=attach_support(copy.deepcopy(self.outline),self.state)
        previous['nodes'][0]['user_edited']=True
        state=copy.deepcopy(self.state)
        removed=state['approved_paper_ids'].pop()
        state['collected_papers']=[p for p in state['collected_papers'] if p['paper_id']!=removed]
        state['evidence']=[e for e in state['evidence'] if e['paper_id']!=removed]
        state['evidence_cards']=[c for c in state['evidence_cards'] if c['paper_id']!=removed]
        merged=review.preserve_edits(review.skeleton(state),previous,state)
        attach_support(merged,state)
        self.assertTrue(all(n['paper_id']!=removed for node in merged['nodes'] for n in node['writing_support']['source_notes']))

    def test_extraction_failure_uses_labeled_quote_not_invented_metadata(self):
        state=copy.deepcopy(self.state)
        state['evidence_cards']=[]
        support=build_support(self.node('themes'),state)
        self.assertEqual(support['status'],'source_only')
        self.assertTrue(all(n['kind']=='source_excerpt' for n in support['source_notes']))
        self.assertEqual(support['source_notes'][0]['text'],state['evidence'][0]['original_text'])
        self.assertFalse(support['comparison_axes'])

    def test_frontend_has_no_check_panels_or_json_outline_editor(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file('streamlit_app.py',default_timeout=30).run()
        app.text_input(key='research_topic_input').set_value('retrieval evidence')
        app.button(key='start_research').click().run()
        app.button(key='continue_research').click().run()
        for c in app.checkbox:
            if c.key and c.key.startswith('direction_choice_'):c.check()
        app.button(key='generate_selected_outline').click().run()
        self.assertFalse(app.exception)
        labels=' '.join(x.label for x in app.expander)
        self.assertNotIn('Citation and evidence checks',labels)
        self.assertFalse(any('Outline JSON'==x.label for x in app.text_area))
        visible=' '.join(str(x.value) for x in app.markdown)
        self.assertIn('Source material for this section',visible)
        self.assertNotIn('根据证据补充比较',visible)
        app.button(key='accept_outline').click().run()
        self.assertFalse(app.exception)
        self.assertNotIn('Evidence and check details',' '.join(x.label for x in app.expander))


if __name__=='__main__':unittest.main()
