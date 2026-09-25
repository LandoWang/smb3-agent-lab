# Session format 2.0

One Session is one attempt. Game frame, monotonic wall time and UTC retain their
separate meanings. Model waits do not advance simulation. Recorded frames are
post-step; bootstrap is explicitly not a model decision.

New records/fields:
- plan.installed: stages, intent_queue, queue_revisions and effective cadence.
- intent.stage_verified: ordered stage ID, actual frame and Profile evidence.
- candidates.offered: permission_source=profile_only_NOT_brain_plan; full recipes.
- decision.selected: action_label and intent_progress at decision time.
- execution.started: full action including segments and discard-tail policy.
- execution.segment_started / execution.segment_guard_failed: observed guards.
- frame.executed: action_frame_offset, segment_index, segment_frame_offset.
- execution.completed: executed_segments, discarded_remaining_frames, queue
  progress; buttons=null for multi-phase recipes rather than a misleading
  single constant input. Exact buttons remain on every frame and segment.

Normal controller calls, singleton contract executions, scripted fixtures and
Profile bootstrap remain separate provenance categories. A sole offered action
is never reported as a model choice. No candidate can be removed by brain text.

One JSONL journal is authoritative; timeline/HTML are derivatives. Hashes and
causal checks cover inputs, calls, plans, offers, recipes and executed phases.
Bundles are private debugging artifacts, not certified public/PII-free releases.
