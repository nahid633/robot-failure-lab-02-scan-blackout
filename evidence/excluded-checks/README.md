# Excluded checks and infrastructure attempt

These are retained in full and are not part of the six planned measurement trials.

- smoke-01: one normal success and one blackout task failure. Recorder stopped
  with the task, so blackout/resumption observation was incomplete. Retained as
  a measurement-development check, not evidence of full-window behavior.
- smoke-02: one normal success and one blackout task failure after the recorder
  was corrected to observe through at least four seconds after the window.
  Both scan/motion evidence records passed validation.
- main-attempt-01: startup hung in behavior_server configuration; bt_navigator
  was unconfigured. Stopped before goal submission or blackout. No task outcome.
  Added a 60-wall-second readiness deadline; restarted the planned batch in a
  fresh evidence directory/domain. No task or sensor configuration was tuned.
- The main archive's pair-2-normal/ directory retains another startup timeout
  without READY.json, result.json, goal or blackout. Its successful startup retry
  is pair-2-normal-attempt-2/. Earlier completed task outcomes were not rerun.
  The root continuation-*.py/.json records the runner revision, its hash and the
  completed trials at continuation. Frozen measurement-worker hashes still match.

Source snapshots accompany each attempt, so the revisions remain inspectable.
