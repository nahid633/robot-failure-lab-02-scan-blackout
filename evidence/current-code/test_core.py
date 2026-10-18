import unittest
from core import ScanGate, sustained, window_metrics


class GateTests(unittest.TestCase):
    def test_half_open_blackout_and_immediate_resume(self):
        gate = ScanGate(True)
        self.assertTrue(gate.forward(9))
        gate.arm(10)
        self.assertTrue(gate.forward(9.999))
        self.assertFalse(gate.forward(10))
        self.assertFalse(gate.forward(11.999))
        self.assertTrue(gate.forward(12))
        with self.assertRaises(RuntimeError):
            gate.arm(20)

    def test_control_never_drops(self):
        gate = ScanGate(False)
        gate.arm(10)
        self.assertTrue(all(gate.forward(t) for t in (0,10,11,12,20)))

    def test_sparse_samples_cannot_prove_sustained_stop(self):
        self.assertIsNone(sustained([{'t': 0}, {'t': 1}], lambda r: True, 0, 2))

    def test_rotation_is_not_a_stop(self):
        rows = [dict(t=i/10, speed=0, w=0.2, x=0, y=0) for i in range(21)]
        metrics = window_metrics(rows, rows, 0, 2, 2)
        self.assertIsNone(metrics['stop_latency_s'])

    def test_stop_and_resume_are_measured_from_distinct_window_edges(self):
        rows=[]
        for i in range(101):
            t=i/20
            speed=0.0 if 1<=t<3 else 0.2
            rows.append(dict(t=t,speed=speed,w=0,x=0,y=0))
        metrics=window_metrics(rows,rows,0.5,2,5)
        self.assertAlmostEqual(metrics['stop_latency_s'],0.5)
        self.assertAlmostEqual(metrics['resume_after_window_s'],0.5)

    def test_no_resume_is_not_zero_latency(self):
        rows=[dict(t=i/20,speed=0,w=0,x=0,y=0) for i in range(101)]
        self.assertIsNone(window_metrics(rows,rows,0,2,5)['resume_after_window_s'])


if __name__ == '__main__':
    unittest.main()
