#!/usr/bin/env python3
"""One fresh-process trial of a two-second scan blackout."""
import argparse
import csv
import json
import math
from pathlib import Path
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from core import ScanGate, window_metrics


class Observer(Node):
    def __init__(self, enabled):
        super().__init__('failure_lab_02_observer')
        self.set_parameters([Parameter('use_sim_time', value=True)])
        self.lock = threading.RLock()
        self.gate = ScanGate(enabled)
        self.scans, self.odom, self.commands = [], [], []
        self.thread_error = None
        self.publisher = self.create_publisher(LaserScan, '/failure_lab/scan', qos_profile_sensor_data)
        self.create_subscription(LaserScan, '/scan', self.scan, qos_profile_sensor_data)
        self.create_subscription(Odometry, '/odom', self.motion, qos_profile_sensor_data)
        self.create_subscription(Twist, '/cmd_vel', self.command, qos_profile_sensor_data)

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def scan(self, msg):
        with self.lock:
            now = self.now()
            forwarded = self.gate.forward(now)
            if forwarded:
                self.publisher.publish(msg)  # No queue, timestamp rewrite or later replay.
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
            self.scans.append(dict(t=now, acquisition=stamp, forwarded=int(forwarded)))

    def motion(self, msg):
        with self.lock:
            p, v = msg.pose.pose.position, msg.twist.twist
            self.odom.append(dict(t=self.now(), speed=math.hypot(v.linear.x,v.linear.y),
                                  w=v.angular.z, x=p.x, y=p.y))

    def command(self, msg):
        with self.lock:
            self.commands.append(dict(t=self.now(), speed=math.hypot(msg.linear.x,msg.linear.y), w=msg.angular.z))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--blackout', type=int, choices=(0,1), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=90)
    args = parser.parse_args()
    rclpy.init()
    observer = Observer(bool(args.blackout))
    executor = SingleThreadedExecutor()
    executor.add_node(observer)
    def spin():
        try:
            executor.spin()
        except Exception as error:
            observer.thread_error = repr(error)
    thread = threading.Thread(target=spin, daemon=True)
    thread.start()
    nav = BasicNavigator()
    nav.set_parameters([Parameter('use_sim_time', value=True)])
    def pose(x,y):
        p=PoseStamped()
        p.header.frame_id='map'
        p.header.stamp=nav.get_clock().now().to_msg()
        p.pose.position.x, p.pose.position.y=x,y
        p.pose.orientation.w=1.0
        return p
    nav.setInitialPose(pose(-2.0,-0.5))
    nav.waitUntilNav2Active()
    settle=observer.now()
    while observer.now()-settle < 1.5:
        rclpy.spin_once(nav, timeout_sec=0.05)
    graph={topic:[dict(node=s.node_name, namespace=s.node_namespace) for s in observer.get_subscriptions_info_by_topic(topic)]
           for topic in ('/scan','/failure_lab/scan')}
    required={'amcl','local_costmap','global_costmap','collision_monitor'}
    actual={s['node'] for s in graph['/failure_lab/scan']}
    if not required.issubset(actual):
        raise RuntimeError(f'Scan routing not verified: {graph}')
    start, wall=observer.now(),time.monotonic()
    accepted=bool(nav.goToPose(pose(1.0,0.5)))
    feedback_rows=[]
    moving_since=None
    timed_out=False
    while accepted and not nav.isTaskComplete():
        now=observer.now()
        if observer.thread_error:
            raise RuntimeError(observer.thread_error)
        with observer.lock:
            last=observer.odom[-1] if observer.odom else None
            if last and now-last['t'] <= 0.15 and last['speed'] >= 0.05:
                moving_since=now if moving_since is None else moving_since
            else:
                moving_since=None
            if (observer.gate.start is None and now-start >= 3.0
                    and moving_since is not None and now-moving_since >= 0.3):
                observer.gate.arm(now)
                print(f'Observation window starts at task +{now-start:.3f}s', flush=True)
        feedback=nav.getFeedback()
        if feedback:
            p=feedback.current_pose.pose.position
            feedback_rows.append(dict(t=now,x=p.x,y=p.y,recoveries=int(feedback.number_of_recoveries)))
        if now-start >= args.timeout or time.monotonic()-wall >= args.timeout*3:
            timed_out=True
            nav.cancelTask()
            break
    end=observer.now()
    result=nav.getResult() if accepted else TaskResult.FAILED
    # Freeze telemetry before serializing; task_end is the action termination time.
    executor.shutdown()
    thread.join(timeout=3)
    if observer.thread_error:
        raise RuntimeError(observer.thread_error)
    window=observer.gate.start
    scans=[r for r in observer.scans if start <= r['t'] <= end]
    odom=[r for r in observer.odom if start <= r['t'] <= end]
    commands=[r for r in observer.commands if start <= r['t'] <= end]
    def write_csv(name, rows, fields):
        with (args.output/name).open('w', newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    write_csv('scans.csv',scans,['t','acquisition','forwarded'])
    write_csv('odom.csv',odom,['t','speed','w','x','y'])
    write_csv('commands.csv',commands,['t','speed','w'])
    write_csv('feedback.csv',feedback_rows,['t','x','y','recoveries'])
    metrics=window_metrics(odom,commands,window,2.0,end) if window is not None else {}
    record=dict(blackout=bool(args.blackout),duration_s=2.0,start_sim_s=start,end_sim_s=end,
                window_start_sim_s=window,window_start_task_s=None if window is None else window-start,
                outcome='timeout' if timed_out else ('succeeded' if result==TaskResult.SUCCEEDED else 'failed'),
                elapsed_sim_s=end-start,elapsed_wall_s=time.monotonic()-wall,
                scans_received=len(scans),scans_dropped=sum(1-r['forwarded'] for r in scans),
                recoveries=max((r['recoveries'] for r in feedback_rows),default=None),
                graph=graph,metrics=metrics,
                injection_valid=window is not None and end >= window+2.0)
    (args.output/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)
    nav.destroy_node()
    observer.destroy_node()
    rclpy.shutdown()


if __name__=='__main__':
    main()
