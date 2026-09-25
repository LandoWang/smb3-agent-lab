"""Hand-authored, symmetric motor vocabulary; NOT learned or guaranteed safe.

Names describe control intent, not achieved physics. All frames/buttons remain
explicit. Opposite input decelerates before reversing; it is not an instant stop.
"""
from ..contracts import Action, Segment


SPECS={
    'release':((), '松键/惯性滑行', 'Release all controls including A; momentum can continue.'),
    'move_left':(('LEFT',), '向左制动/移动', 'Left correction: brake rightward speed, then move left; release A.'),
    'move_right':(('RIGHT',), '向右制动/移动', 'Right correction: brake leftward speed, then move right; release A.'),
    'run_left':(('LEFT','B'), '向左跑', 'Run left, or adjust left in air; release A. Reversal is not instant.'),
    'run_right':(('RIGHT','B'), '向右跑', 'Run right, or adjust right in air; release A. Reversal is not instant.'),
    'jump_up':(('A',), '原地起跳/续按跳跃', 'Press or hold A without directional input; drift can remain. No second midair jump.'),
    'jump_left':(('LEFT','A'), '左跳/空中左修正', 'Press or hold A with left input; brake rightward momentum first if moving right.'),
    'jump_right':(('RIGHT','A'), '右跳/空中右修正', 'Press or hold A with right input; brake leftward momentum first if moving left.'),
    'running_jump_left':(('LEFT','A','B'), '向左跑跳/续跳', 'Press or hold A+B with left input; no separate run-up phase.'),
    'running_jump_right':(('RIGHT','A','B'), '向右跑跳/续跳', 'Press or hold A+B with right input; no separate run-up phase.'),
}
SKILLS={name:{'description':desc,'label':label,'buttons':list(buttons)}
    for name,(buttons,label,desc) in SPECS.items()}
ACTIONS=[Action(f'{name}_{n}',name,buttons,n,label,desc)
    for name,(buttons,label,desc) in SPECS.items() for n in (6,12)]
for direction in ('left','right'):
    button=direction.upper();skill='runup_jump_'+direction
    desc=f'Run {direction} releasing A for 6f; grounded takeoff holds A+B for 12f; release A while running 6f. No landing guarantee.'
    label=('向左' if direction=='left' else '向右')+'助跑跳'
    SKILLS[skill]={'description':desc,'label':label}
    ACTIONS.append(Action(skill+'_24',skill,(button,'B'),24,label,desc,(
        Segment('runup_release_A',(button,'B'),6),
        Segment('takeoff_hold_A',(button,'A','B'),12,
            (('airborne','eq',False),('a_held_frames','eq',0))),
        Segment('release_A_continue',(button,'B'),6))))


def eligible(action,sample):
    if sample.terminal or not sample.state.get('valid_for_decisions',True):
        return False,'terminal_or_invalid_state'
    if action.skill.startswith('runup_jump_') and sample.metrics.get('airborne') is not False:
        return False,'runup_requires_ground_at_selection'
    if 'A' in action.buttons and sample.metrics.get('airborne') is False:
        held=sample.metrics.get('a_held_frames')
        if type(held) is not int or held!=0:
            return False,'ground_jump_requires_observed_A_release'
    return True,''
