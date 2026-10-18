"""Pure blackout gate and telemetry measurements (no ROS imports)."""
import math


class ScanGate:
    def __init__(self, enabled, duration=2.0):
        self.enabled = enabled
        self.duration = duration
        self.start = None

    def arm(self, now):
        if self.start is not None:
            raise RuntimeError('Blackout already armed')
        self.start = now

    def forward(self, now):
        return not (self.enabled and self.start is not None
                    and self.start <= now < self.start + self.duration)


def sustained(rows, predicate, after, before, duration=0.3, max_gap=0.15):
    """First interval start confirmed by >=duration of closely sampled data."""
    start = previous = None
    for row in rows:
        t = row['t']
        if t < after or t > before:
            continue
        if previous is not None and t - previous > max_gap:
            start = None
        if predicate(row):
            start = t if start is None else start
            if t - start >= duration - 1e-8:
                return start
        else:
            start = None
        previous = t
    return None


def window_metrics(odom, commands, start, duration, task_end):
    end = start + duration
    stopped = lambda r: r['speed'] <= 0.01 and abs(r['w']) <= 0.03
    moving = lambda r: r['speed'] >= 0.05
    stop = sustained(odom, stopped, start, end)
    command_stop = sustained(commands, stopped, start, end)
    resume = sustained(odom, moving, end, task_end) if stop is not None else None
    before = [r for r in odom if start - 0.3 <= r['t'] < start]
    during = [r for r in odom if start <= r['t'] <= end]
    path = sum(math.hypot(b['x'] - a['x'], b['y'] - a['y'])
               for a, b in zip(during, during[1:]))
    return dict(stop_latency_s=None if stop is None else stop-start,
                zero_command_latency_s=None if command_stop is None else command_stop-start,
                resume_after_window_s=None if resume is None else resume-end,
                pre_window_speed_mps=sum(r['speed'] for r in before)/len(before) if before else None,
                window_path_m=path, window_odom_samples=len(during),
                window_odom_max_gap_s=max((b['t']-a['t'] for a,b in zip(during,during[1:])), default=None))
