"""Small provider-compatible JSON schemas for the existing structured tasks."""
def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def array(item):
    return {'type':'array','items':item}


S={'type':'string'}
STRINGS=array(S)
CLAIM=obj({'claim_id':S,'text':S,'evidence_ids':STRINGS,
           'kind':{'type':'string','enum':['author_finding','synthesis','hypothesis']},
           'required_level':{'type':'string','enum':['abstract','fulltext']}})
SCHEMAS={
    'plan':obj({'domain':{'type':'string','enum':['cs','humanities','interdisciplinary']},
                'core_constraints':STRINGS,'questions':array(obj({'question_id':S,'text':S,'query':S}))}),
    'screen':obj({'items':array(obj({'paper_id':S,'relevant':{'type':'boolean'},'match_type':{'type':'string','enum':['direct','related','irrelevant']},'reason':S,'question_ids':STRINGS}))}),
    'support':obj({'status':{'type':'string','enum':['supported','partially_supported','unsupported','insufficient_evidence']},
                   'reason':S,'contradiction':{'type':'boolean'}}),
    'draft':obj({'sections':array(obj({'heading':S,'claims':array(CLAIM)}))}),
}

# Provider adapters decide how (and whether) to send these schemas.
CARD_FIELD=obj({'status':{'type':'string','enum':['found','not_found_in_processed_text','not_checked']},
                'text':S,'evidence_ids':STRINGS})
SCHEMAS['card']=obj({name:CARD_FIELD for name in ('research_question','object_conditions','method','findings','limitations','topic_relationship','data','evaluation_metrics')})
OUTLINE_POINT=obj({'point_id':S,'text':S,'kind':{'type':'string','enum':['author_finding','synthesis','hypothesis','user_idea']},
                   'evidence_ids':STRINGS,'required_level':{'type':'string','enum':['abstract','fulltext']}})
SCHEMAS['outline']=obj({'nodes':array(obj({'node_id':S,'parent_id':{'type':['string','null']},'order':{'type':'integer'},
    'section_type':{'type':'string','enum':['introduction','search','concepts','themes','disagreements','future','conclusion']},
    'title':S,'purpose':S,'question_ids':STRINGS,'argument_points':array(OUTLINE_POINT),'counterevidence_ids':STRINGS,
    'conditions':STRINGS,'gaps':STRINGS,'user_writing_tasks':STRINGS}))})
SCHEMAS['directions']=obj({'directions':array(obj({'direction_id':S,'title':S,'description':S,'question':S,
    'search_query':S,'paper_ids':STRINGS,'evidence_ids':STRINGS}))})
