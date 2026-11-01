"""Concrete, source-linked section material assembled from extracted author reports.

This layer does not rank studies, infer unreported results or invent personal judgments.
It remains useful when the optional outline-generation call cannot complete.
"""
import copy
from papers import stable_id

CORE_FIELDS=('research_question','object_conditions','method','findings','limitations','topic_relationship')
EXTRA_FIELDS=('data','evaluation_metrics')
ALL_FIELDS=CORE_FIELDS+EXTRA_FIELDS
LABELS={'research_question':'研究问题','object_conditions':'对象与适用条件','method':'方法与实施流程',
        'data':'数据与实验设置','evaluation_metrics':'评价指标','findings':'作者报告的发现',
        'limitations':'作者说明的局限','topic_relationship':'与本节的关联'}
EN_LABELS={'research_question':'Research question','object_conditions':'Population and conditions','method':'Method and procedure',
           'data':'Data and experimental setting','evaluation_metrics':'Evaluation metrics','findings':'Reported findings',
           'limitations':'Author-stated limitations','topic_relationship':'Relationship to this section'}
SECTION_FIELDS={
    'introduction':('research_question','object_conditions','data'),
    'concepts':('research_question','method'),
    'themes':('method','data','evaluation_metrics','findings','limitations'),
    'disagreements':('object_conditions','data','evaluation_metrics','findings','limitations'),
    'future':('limitations',),
    'conclusion':('findings','limitations'),
    'search':(),
}


def empty_field():
    return {'status':'not_checked','text':'','evidence_ids':[]}


def section_papers(node,state):
    directions=state.get('selected_directions',[])
    linked=[d for d in directions if d['direction_id'] in node.get('question_ids',[])]
    wanted={p for d in (linked or directions) for p in d['paper_ids']}
    approved=set(state.get('approved_paper_ids',[]))
    return [p for p in state.get('collected_papers',[]) if p['paper_id'] in approved and p.get('evidence_level')!='not_processed' and (not wanted or p['paper_id'] in wanted)]


def build_support(node,state):
    from card_inputs import card_status
    table=[];notes=[]
    evidence={e['evidence_id']:e for e in state.get('evidence',[]) if e['paper_id'] in state.get('approved_paper_ids',[]) and not e.get('is_reference')}
    cards={c['paper_id']:c for c in state.get('evidence_cards',[])}
    fields=SECTION_FIELDS[node['section_type']]
    for p in section_papers(node,state):
        card=cards.get(p['paper_id'],{})
        cells={}
        for field in fields:
            value=copy.deepcopy(card.get('fields',{}).get(field,empty_field()))
            ids=value.get('evidence_ids',[])
            valid=value.get('status')=='found' and bool(ids) and all(e in evidence and evidence[e]['paper_id']==p['paper_id'] for e in ids)
            if not valid and value.get('status')=='found':
                value=empty_field()
            cells[field]=value
            if valid:
                notes.append({'note_id':stable_id('material_',[node['node_id'],p['paper_id'],field,ids,value['text']]),
                    'paper_id':p['paper_id'],'field':field,'text':value['text'],'evidence_ids':ids,
                    'kind':'author_finding','required_level':'fulltext' if any(evidence[e]['evidence_level']=='fulltext' for e in ids) else 'abstract'})
        if fields:
            table.append({'paper_id':p['paper_id'],'cells':cells,'processing_status':card_status(card,p)})
    # If extraction failed, show an explicitly labeled source excerpt, not a made-up method/result.
    extraction_available=any(v.get('status')=='found' for card in cards.values() for f,v in card.get('fields',{}).items() if f!='topic_relationship')
    if fields and not notes and not extraction_available and node['section_type'] in ('introduction','themes'):
        for p in section_papers(node,state):
            e=next((e for e in evidence.values() if e['paper_id']==p['paper_id']),None)
            if e:
                notes.append({'note_id':stable_id('excerpt_',[node['node_id'],e['evidence_id']]),'paper_id':p['paper_id'],
                    'field':'source_excerpt','text':e['original_text'],'evidence_ids':[e['evidence_id']],
                    'kind':'source_excerpt','required_level':e['evidence_level']})
    axes=[]
    # Comparison operations describe what to juxtapose, not which study is better.
    if node['section_type'] in ('themes','disagreements'):
        for field in ('method','object_conditions','data','evaluation_metrics','findings','limitations'):
            entries=[n for n in notes if n['field']==field]
            if len({n['paper_id'] for n in entries})>=2:
                axes.append({'dimension':field,'paper_ids':list(dict.fromkeys(n['paper_id'] for n in entries)),
                    'evidence_ids':list(dict.fromkeys(e for n in entries for e in n['evidence_ids']))})
    return {'version':'section-material-v1','fields':list(fields),'source_notes':notes,'comparison_rows':table,
            'comparison_axes':axes,'status':'available' if any(n['kind']=='author_finding' for n in notes) else 'source_only' if notes else 'unavailable'}


def attach_support(outline,state):
    for node in outline.get('nodes',[]):
        node['writing_support']=build_support(node,state)
    return outline


def validate_support(support,state):
    if not isinstance(support,dict) or support.get('version')!='section-material-v1':
        raise ValueError('invalid section material')
    allowed={e['evidence_id']:e for e in state.get('evidence',[]) if e['paper_id'] in state.get('approved_paper_ids',[])}
    def ids_valid(ids,pid=None):
        return isinstance(ids,list) and all(isinstance(e,str) and e in allowed and (pid is None or allowed[e]['paper_id']==pid) for e in ids)
    if not isinstance(support.get('source_notes'),list) or not isinstance(support.get('comparison_rows'),list) or not isinstance(support.get('comparison_axes'),list):
        raise ValueError('invalid section material collections')
    for note in support['source_notes']:
        if not isinstance(note,dict) or not isinstance(note.get('text'),str) or not note.get('evidence_ids') or not ids_valid(note['evidence_ids'],note.get('paper_id')):
            raise ValueError('invalid section source')
        if note.get('kind') not in ('author_finding','source_excerpt') or note.get('field') not in ALL_FIELDS+('source_excerpt',):
            raise ValueError('invalid section source type')
        if note.get('required_level') not in ('abstract','fulltext') or (note['required_level']=='fulltext' and not any(allowed[e]['evidence_level']=='fulltext' for e in note['evidence_ids'])):
            raise ValueError('invalid section evidence level')
        if note['kind']=='source_excerpt' and not any(note['text']==allowed[e]['original_text'] for e in note['evidence_ids']):
            raise ValueError('source excerpt changed')
    for row in support['comparison_rows']:
        if not isinstance(row,dict) or row.get('paper_id') not in state.get('approved_paper_ids',[]) or not isinstance(row.get('cells'),dict):
            raise ValueError('invalid comparison row')
        for field,value in row['cells'].items():
            if field not in ALL_FIELDS or not isinstance(value,dict) or value.get('status') not in ('found','not_found_in_processed_text','not_checked') or not ids_valid(value.get('evidence_ids'),row['paper_id']):
                raise ValueError('invalid comparison cell')
            if value['status']=='found' and (not isinstance(value.get('text'),str) or not value['text'].strip() or not value['evidence_ids']):
                raise ValueError('uncited comparison cell')
            if value['status']!='found' and (value.get('text') or value.get('evidence_ids')):
                raise ValueError('unchecked comparison claim')
    for axis in support['comparison_axes']:
        if axis.get('dimension') not in ALL_FIELDS or not ids_valid(axis.get('evidence_ids')) or set(axis.get('paper_ids',[]))!={allowed[e]['paper_id'] for e in axis['evidence_ids']}:
            raise ValueError('invalid comparison axis')
    return support


def source_ids(support):
    return {e for n in support.get('source_notes',[]) for e in n['evidence_ids']}


def render_support(node,state,refs,escape,rendered_tables=None):
    from card_inputs import reason_text
    support=node.get('writing_support') or build_support(node,state)
    zh=state.get('language')=='zh'
    labels=LABELS if zh else EN_LABELS
    papers={p['paper_id']:p for p in state.get('collected_papers',[])}
    evidence={e['evidence_id']:e for e in state.get('evidence',[])}
    checks={c['claim_id']:c.get('status') for c in state.get('claim_checks',[])}
    insufficient={'unsupported','insufficient_evidence'}
    lines=[]
    if node['section_type']=='search':
        sources=list(dict.fromkeys(e.get('source','') for e in state.get('search_events',[]) if e.get('source')))
        plan=state.get('research_plan',{})
        if sources:lines.append('- '+('检索来源：' if zh else 'Sources searched: ')+escape(', '.join(sources)))
        if plan.get('year'):lines.append('- '+('年份范围：' if zh else 'Year range: ')+escape(str(plan['year'])))
        if plan.get('core_constraints'):lines.append('- '+('问题范围：' if zh else 'Scope: ')+escape('；'.join(plan['core_constraints'])))
        if state.get('selected_directions'):lines.append('- '+('本次纳入方向：' if zh else 'Included directions: ')+escape('；'.join(d['title'] for d in state['selected_directions'])))
        return lines
    notes=support['source_notes']
    rows=support['comparison_rows']
    fields=[f for f in support['fields'] if any(r['cells'].get(f,{}).get('status')=='found' for r in rows)]
    has_comparison=node['section_type'] in ('themes','disagreements') and len(rows)>=2 and bool(fields)
    table_key=stable_id('table_',[fields,rows]) if has_comparison else None
    repeated=has_comparison and rendered_tables is not None and table_key in rendered_tables
    show_table=has_comparison and not repeated
    if notes and not has_comparison:
        lines.extend(['', '**'+('可直接用于本节的文献内容' if zh else 'Source material for this section')+'**'])
    # Put the actual author-reported content ahead of organizational instructions.
    shown=[] if has_comparison else notes[:6]
    for note in shown:
        p=papers.get(note['paper_id'],{})
        label=labels.get(note['field'],'原文摘录（尚未完成字段提取）' if zh else 'Source excerpt (field extraction incomplete)')
        status=checks.get(note['note_id'])
        if status in insufficient:
            lines.append('- **'+escape(p.get('title',note['paper_id']))+' — '+label+'**：'+('当前引文支持不足，暂不列为可写结论。' if zh else 'The cited passage is insufficient; this item is not presented as a supported conclusion.')+' '+refs(note['evidence_ids']))
            continue
        content=note['text']
        if status=='partially_supported':content+=('（引文仅部分支持，需核对范围）' if zh else ' (partially supported; check scope)')
        if note['kind']=='source_excerpt' and len(content)>400:content=content[:400]+'…'
        locations=[]
        for eid in note['evidence_ids']:
            e=evidence[eid]
            where=('PDF 第 '+str(e['page_start'])+' 页' if zh else 'PDF p. '+str(e['page_start'])) if e.get('page_start') else ('摘要' if zh else 'abstract')
            if e.get('section'):where+=' · '+str(e['section'])
            locations.append(where)
        lines.append('- **'+escape(p.get('title',note['paper_id']))+' — '+label+'**：'+escape(content)+' '+refs(note['evidence_ids'])+'（'+escape('；'.join(dict.fromkeys(locations)))+'）')
    # A field-by-study matrix is useful only where comparison is part of this section.
    if show_table:
        if rendered_tables is not None:rendered_tables.add(table_key)
        lines.extend(['','**'+('文献对照' if zh else 'Study comparison')+'**',''])
        def cell(s):return escape(s).replace('|','\\|').replace('\n',' ')
        lines.append('| '+('文献' if zh else 'Study')+' | '+' | '.join(labels[f] for f in fields)+' |')
        lines.append('| '+' | '.join('---' for _ in range(len(fields)+1))+' |')
        for row in rows:
            cells=[]
            for field in fields:
                v=row['cells'].get(field,empty_field())
                note=next((n for n in notes if n['paper_id']==row['paper_id'] and n['field']==field),{})
                status=checks.get(note.get('note_id'))
                if status in insufficient:
                    cells.append(('当前引文支持不足' if zh else 'Insufficient support')+' '+refs(v['evidence_ids']))
                elif v['status']=='found':
                    cells.append(cell(v['text'])+('（需核对范围）' if zh else ' (check scope)') if status=='partially_supported' else cell(v['text']))
                    cells[-1]+=' '+refs(v['evidence_ids'])
                else:
                    reason=v.get('reason_code') or row.get('processing_status','not_started')
                    cells.append(('当前已读文本未提及' if zh else 'Not in processed text') if v['status']=='not_found_in_processed_text' else reason_text(reason,state.get('language','en')))
            ev=[evidence[e] for v in row['cells'].values() for e in v['evidence_ids'] if e in evidence]
            where='；'.join(dict.fromkeys(('PDF 第 '+str(e['page_start'])+' 页' if zh else 'PDF p. '+str(e['page_start'])) if e.get('page_start') else ('摘要' if zh else 'abstract') for e in ev))
            status=row.get('processing_status','not_started')
            suffix=('；'+reason_text(status,state.get('language','en'))) if status not in ('extracted','ready') else ''
            lines.append('| '+cell(papers[row['paper_id']]['title'])+'（'+cell(where+suffix)+'） | '+' | '.join(cells)+' |')
    elif repeated:
        lines.append('- '+('本节使用前面文献对照表中的同一组研究，下面列出本节采用的具体内容。' if zh else 'This section uses the studies in the comparison table above; its specific source material follows.'))
    axes=list(support['comparison_axes'])
    focus=(node['title']+' '+node['purpose']).lower()
    preferred=('evaluation_metrics','data','findings') if any(s in focus for s in ('评价','指标','evaluation','metric')) else ('method','data','object_conditions') if any(s in focus for s in ('方法','流程','method','procedure')) else ('object_conditions','data','limitations') if node['section_type']=='disagreements' else ()
    if preferred:axes.sort(key=lambda a:preferred.index(a['dimension']) if a['dimension'] in preferred else len(preferred))
    has_children=any(n.get('parent_id')==node['node_id'] for n in state.get('outline',{}).get('nodes',[]))
    if axes and not has_children:
        lines.extend(['','**'+('本节可以如何展开' if zh else 'How to organize this section')+'**'])
        for axis in axes[:3]:
            values=[n for n in notes if n['field']==axis['dimension'] and n['paper_id'] in axis['paper_ids'] and checks.get(n['note_id']) not in insufficient][:3]
            if len({n['paper_id'] for n in values})<2:continue
            reported='；'.join('《'+papers[n['paper_id']]['title']+'》：'+n['text'] for n in values)
            lines.append('- **'+labels[axis['dimension']]+'**：'+escape(reported)+' '+refs(axis['evidence_ids']))
        lines.append('- '+('先分别交代上表中的研究对象和条件，再按列出的流程、数据与指标组织相应文献内容。' if zh else 'Introduce each study’s population and conditions, then organize its reported procedures, data and metrics by the dimensions above.'))
        if any(a['dimension'] in ('data','evaluation_metrics','findings') for a in support['comparison_axes']):
            lines.append('- '+('将数据集、评价指标和实验条件与各自结果一起呈现；现有提取尚未核实数值结果是否可直接横向比较。' if zh else 'Keep datasets, metrics and conditions beside each result; direct numerical comparability has not been verified.'))
    if not notes:
        pending=[r for r in rows if r.get('processing_status') not in ('extracted','ready')]
        if pending:
            for row in pending:
                lines.append('- '+escape(papers[row['paper_id']]['title'])+'：'+reason_text(row.get('processing_status'),state.get('language','en')))
        else:
            lines.append('- '+('当前已读文本没有提供本节所需的明确陈述。' if zh else 'The processed text does not provide explicit statements for this section.'))
    return lines
