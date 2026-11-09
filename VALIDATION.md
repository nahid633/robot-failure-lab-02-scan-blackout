# Publication checks

Checked on 2026-11-09: all imported file hashes match the preserved local archive; Python source parses; root documentation links resolve; files meet GitHub size limits.

Existing tests / measurement checks:

```text
test_control_never_drops (test_core.GateTests.test_control_never_drops) ... ok
test_half_open_blackout_and_immediate_resume (test_core.GateTests.test_half_open_blackout_and_immediate_resume) ... ok
test_no_resume_is_not_zero_latency (test_core.GateTests.test_no_resume_is_not_zero_latency) ... ok
test_rotation_is_not_a_stop (test_core.GateTests.test_rotation_is_not_a_stop) ... ok
test_sparse_samples_cannot_prove_sustained_stop (test_core.GateTests.test_sparse_samples_cannot_prove_sustained_stop) ... ok
test_stop_and_resume_are_measured_from_distinct_window_edges (test_core.GateTests.test_stop_and_resume_are_measured_from_distinct_window_edges) ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.001s

OK
```

No new navigation experiment was run. This is not a clean-machine reproduction test.
