"""Generic compact controller context and exact choice prompt token preflight."""
import copy
import json


def describe_action(action):
    parts=action.get('segments') or [{'buttons':action['buttons'],'frames':action['frames']}]
    inputs=[]
    for part in parts:
        guard=','.join(f'{m} {op} {v}' for m,op,v in part.get('requires',()))
        inputs.append(('+'.join(part['buttons']) or 'RELEASE')+f" {part['frames']}f"+
            (f' [requires {guard}]' if guard else ''))
    return (action.get('description') or action.get('label') or action.get('skill','Motor action'))+' Inputs: '+' -> '.join(inputs)


def compact(context):
    result=copy.deepcopy(context)
    omitted=('skill_catalog','metric_names','candidates','motor_capabilities','goal_kinds',
        'goal_verifiers','goal_evidence_note','executable_action_catalog')
    for field in omitted: result.pop(field,None)
    if result.get('plan'):
        result['plan']={k:result['plan'][k] for k in ('objective','guidance','review_after_frames') if k in result['plan']}
    if result.get('intent_progress'):
        q=result['intent_progress']
        q['stages']=[{k:s[k] for k in ('id','status')} for s in q['stages']]
        q.pop('semantics',None)
    if result.get('execution_feedback'):
        result['execution_feedback']={k:v for k,v in result['execution_feedback'].items()
            if k not in ('before','intent_progress','milestone_status')}
    rows=result.get('recent_trajectory',[])
    selected=rows[-19::6]
    if rows and (not selected or selected[-1]!=rows[-1]): selected.append(rows[-1])
    result['recent_trajectory']=selected
    result['context_projection']={'version':'local-controller-intent-v2',
        'trajectory_samples_omitted':len(rows)-len(selected),
        'catalog_omitted':'all offered actions remain in criteria with exact input sequences; full trace in journal',
        'other_omissions':'brain rationale, duplicate plan stages, stage proof details, duplicate previous progress/before metrics; current/upcoming goals retained'}
    return trim_audit_fields(result)


def trim_audit_fields(context):
    """Decision data stays intact; archival bookkeeping stays in the journal.

    Works on an already projected archived request too, for exact-token regression.
    No text truncation, candidate removal, hazard filtering or lower token reserve.
    """
    result=copy.deepcopy(context)
    trajectory_omitted=result.get('context_projection',{}).get('trajectory_samples_omitted',0)
    for field in ('session_id','observation_id','game_time_s','planning_window',
                  'plan_id','plan_progress','plan_contract','context_projection'):
        result.pop(field,None)
    feedback=result.get('execution_feedback')
    if feedback:
        keys=('frame_start','frame_end','requested_frames','executed_frames',
              'executed_segments','discarded_remaining_frames','interruption','terminal')
        result['execution_feedback']={k:feedback[k] for k in keys if k in feedback}
        if not feedback.get('executed_segments') and 'buttons' in feedback:
            result['execution_feedback']['buttons']=feedback['buttons']
    q=result.get('intent_progress')
    if q:
        # Keep every current/upcoming goal verbatim, including its coordinate region.
        q.pop('stages',None)
        q.pop('semantics',None)
    result['context_projection']={'version':'local-controller-audit-trim-v3',
        'trajectory_samples_omitted':trajectory_omitted,
        'omitted':'IDs, duplicate clocks/plan contract/completed stages/after-state/reward metadata; full journal retained',
        'preserved':'observation, current/upcoming goals, global guidance, sampled trajectory, executed segments; all action criteria unchanged'}
    return result


def messages(payload):
    system=('Answer a fixed set of questions about the state the user provides. '
        'Each question lists its allowed answers; reply with exactly one label '
        'per question.\n')
    for qid,q in payload['questions'].items():
        if q['type']!='choice' or not 2<=len(q['criteria'])<=26: raise ValueError('choice_count')
        system+=f"\nQuestion {qid}: {q['instructions'].strip()}\n"
        for i,(name,desc) in enumerate(q['criteria'].items()):
            label=chr(65+i)
            system+=f"  {label}: {name} ({str(desc).strip()})\n" if desc else f"  {label}: {name}\n"
    system+='\nReply with one line per question, in this order, formatted as "id: label".'
    return [{'role':'system','content':system},{'role':'user','content':payload['state']}]
