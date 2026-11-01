"""Paper-local extraction inputs, separate from topic-wide top-k retrieval."""
import copy
import hashlib
from documents import chunks_from_pages
from papers import stable_id

CARD_VERSION='card-v3-paper-inputs'
REASONS={
    'ready':('已分配可读材料','Readable material allocated'),
    'extracted':('已完成提取','Extraction complete'),
    'partial':('部分字段尚未完成','Some fields are incomplete'),
    'not_selected':('未纳入当前方向','Outside selected directions'),
    'material_missing':('没有可读摘要或正文，可补充 PDF','No readable abstract or text; add a PDF'),
    'context_budget':('文本分配额度不足，尚未执行提取','Text allocation limit reached; extraction not run'),
    'model_budget':('本轮模型或 token 额度不足，尚未完成提取','Model/token budget exhausted; extraction incomplete'),
    'request_budget':('本轮请求额度不足，尚未完成提取','Request budget exhausted; extraction incomplete'),
    'invalid_response':('返回字段或引用无效，可重试提取','Invalid returned fields/citations; retry extraction'),
    'provider_error':('模型请求失败，可重试提取','Model request failed; retry extraction'),
    'field_not_returned':('模型未返回该字段','Field not returned by model'),
    'not_started':('该项尚未完成，可重试提取','This item is incomplete; retry extraction'),
}


def reason_text(code,language='zh'):
    return REASONS.get(code,REASONS['not_started'])[0 if language=='zh' else 1]


def active_ids(state):
    approved=set(state.get('approved_paper_ids',[]))
    selected={pid for d in state.get('selected_directions',[]) for pid in d['paper_ids']}
    return approved & selected if state.get('selected_directions') else approved


def _window(chunk,limit):
    if limit<1:return None
    text=chunk['text']
    if len(text)<=limit:return copy.deepcopy(chunk)
    # New exact text slice, hash and ID; never pretend a shortened chunk is the original.
    end=limit
    boundary=max(text.rfind(' ',0,end),text.rfind('\n',0,end))
    if boundary>=int(limit*.75):end=boundary
    text=text[:end]
    return {**chunk,'text':text,'content_hash':hashlib.sha256(text.encode()).hexdigest(),
        'chunk_id':stable_id('c_',[CARD_VERSION,chunk['chunk_id'],0,end]),
        'parent_chunk_id':chunk['chunk_id'],'slice_start':0,'slice_end':end,'card_input_window':True}


def allocate_card_inputs(state,chunks,cfg):
    """Reserve a first excerpt for every readable active paper before extra excerpts."""
    active=active_ids(state)
    source_chunks={c['chunk_id']:c for c in chunks}
    candidates={}; allocation={}
    for paper in state.get('collected_papers',[]):
        pid=paper['paper_id']
        if pid not in active:
            allocation[pid]={'paper_id':pid,'status':'not_selected','evidence_ids':[],'units':0}
            continue
        document=[c for c in chunks if c['paper_id']==pid and not c.get('is_reference') and not c.get('card_input_window') and c.get('text','').strip()
                  and not (paper.get('abstract') and c.get('evidence_level')=='abstract')]
        abstracts=[{**c,'source_role':'metadata_abstract'} for c in chunks_from_pages(pid,[paper.get('abstract') or ''],cfg,'abstract')]
        source_chunks.update((c['chunk_id'],c) for c in abstracts)
        # A full abstract is usually a better initial cross-paper overview than page-one headers.
        def priority(c):
            section=(c.get('section') or '').lower()
            return (0 if any(k in section for k in ('method','result','evaluation','方法','结果','评价')) else 1,
                    c.get('page_start') or 0,c['chunk_id'])
        ordered=abstracts[:1]+sorted(document,key=priority)+abstracts[1:]
        seen=set(); candidates[pid]=[]
        for c in ordered:
            if c['content_hash'] not in seen:
                seen.add(c['content_hash']);candidates[pid].append(c)
        allocation[pid]={'paper_id':pid,'status':'ready' if candidates[pid] else 'material_missing','evidence_ids':[],'units':0}
    usable=sorted(pid for pid,cs in candidates.items() if cs)
    remaining=cfg.context_tokens
    evidence=[]
    for round_index in range(cfg.per_paper_chunks):
        pending=[pid for pid in usable if len(candidates[pid])>round_index]
        if not pending:break
        share=remaining//len(pending)
        if share<=512:break
        for pid in pending:
            c=_window(candidates[pid][round_index],share-512)
            if not c:continue
            cost=len(c['text'])+512
            if cost>remaining:continue
            remaining-=cost;source_chunks[c['chunk_id']]=c
            qids=[d['direction_id'] for d in state.get('selected_directions',[]) if pid in d['paper_ids']]
            eid=stable_id('ec_',[CARD_VERSION,pid,c['chunk_id']])
            evidence.append({**c,'evidence_id':eid,'original_text':c['text'],'question_id':qids[0] if qids else None,
                'question_ids':qids,'method':'per_paper_extraction','score':None})
            allocation[pid]['evidence_ids'].append(eid);allocation[pid]['units']+=cost
    for item in allocation.values():
        if item['status']=='ready' and not item['evidence_ids']:item['status']='context_budget'
    return evidence,list(source_chunks.values()),list(allocation.values()),remaining


def card_status(card,paper=None):
    """Explain old snapshots too; do not turn a missing extraction into a missing finding."""
    status=card.get('processing_status')
    if status:return status
    error=card.get('error','')
    if 'BudgetExceeded' in error:return 'model_budget'
    if card.get('evidence_level')=='not_processed' or (paper or {}).get('evidence_level')=='not_processed':return 'not_selected'
    if card.get('evidence_level')=='unavailable':return 'material_missing'
    if 'invalid' in error:return 'invalid_response'
    if error:return 'provider_error'
    fields=list(card.get('fields',{}).values())
    if fields and all(v.get('status')!='not_checked' for v in fields):return 'extracted'
    if any(v.get('status')=='found' for v in fields):return 'partial'
    if not card.get('excerpts'):return 'material_missing'
    return 'not_started'


def cacheable(card):
    from writing_support import ALL_FIELDS
    fields=card.get('fields',{})
    return card_status(card)=='extracted' and not card.get('error') and all(
        isinstance(fields.get(f),dict) and fields[f].get('status') in ('found','not_found_in_processed_text')
        and (bool(fields[f].get('text')) and bool(fields[f].get('evidence_ids')) if fields[f]['status']=='found' else not fields[f].get('text') and not fields[f].get('evidence_ids')) for f in ALL_FIELDS)


def preserved_sources(state,chunks):
    """Keep previously valid citations only when their exact source chunk still exists."""
    table={c['chunk_id']:c for c in chunks}
    keep={eid for card in state.get('evidence_cards',[]) if card['paper_id'] in active_ids(state)
          for v in card.get('fields',{}).values() if v.get('status') in ('found',) for eid in v.get('evidence_ids',[])}
    candidates=list(state.get('evidence',[]))+[e for c in state.get('evidence_cards',[]) for e in c.get('excerpts',[])]
    result={}
    for e in candidates:
        c=table.get(e.get('chunk_id'))
        if e.get('evidence_id') in keep and c and all(e.get(k)==c.get(k) for k in ('paper_id','text','content_hash','evidence_level','page_start','page_end')) and e.get('original_text')==c.get('text'):
            result[e['evidence_id']]=e
    return list(result.values())


def retryable_ids(state):
    papers={p['paper_id']:p for p in state.get('collected_papers',[])}
    readable={c['paper_id'] for c in state.get('chunks',[]) if c.get('text') and not c.get('is_reference')}
    return [c['paper_id'] for c in state.get('evidence_cards',[]) if c['paper_id'] in active_ids(state) and not cacheable(c)
            and (papers.get(c['paper_id'],{}).get('abstract') or c['paper_id'] in readable)]


def can_retry(state,cfg):
    usage=state.get('telemetry',{})
    return bool(retryable_ids(state)) and state.get('card_retry_count',0)<cfg.max_review_rounds and usage.get('model_calls',0)<cfg.max_model_calls and usage.get('requests',0)<cfg.max_requests and cfg.max_total_tokens-usage.get('reserved_tokens',0)>min(cfg.max_output_tokens,2048)+512
