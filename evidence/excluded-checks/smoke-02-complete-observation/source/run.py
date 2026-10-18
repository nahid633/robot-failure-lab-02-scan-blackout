#!/usr/bin/env python3
"""Fresh-process paired trials; refuses to overwrite evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import yaml
from ament_index_python.packages import get_package_share_directory


def stop(process):
    # Clean up the entire group we created, even if its leader already exited.
    try:
        os.killpg(process.pid,signal.SIGINT)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--timeout',type=float,default=90)
    parser.add_argument('--domain',type=int,default=188)
    args=parser.parse_args()
    if args.repeats < 1 or not 1 <= args.domain <= 220 or args.timeout <= 5:
        parser.error('Positive repeats, domain 1..220, timeout >5 required')
    args.output.mkdir(parents=True,exist_ok=False)
    root=args.output.resolve()
    snapshot=root/'source'
    snapshot.mkdir()
    for p in Path(__file__).resolve().parent.glob('*.py'):
        shutil.copy2(p,snapshot/p.name)
    bringup=Path(get_package_share_directory('nav2_bringup'))
    upstream=bringup/'launch/tb3_simulation_launch.py'
    launch=upstream.read_text()
    needle="cmd=['gz', 'sim', '-r', '-s', world_sdf]"
    if launch.count(needle)!=1:
        raise RuntimeError('Installed launch differs: review seed patch before running')
    shutil.copy2(upstream,snapshot/'upstream_tb3_simulation_launch.txt')
    (snapshot/'seeded_simulation_launch.py').write_text(launch.replace(needle,
        "cmd=['gz', 'sim', '--seed', os.environ['RFL_GZ_SEED'], '-r', '-s', world_sdf]"))
    config=yaml.safe_load((bringup/'params/nav2_params.yaml').read_text())
    def route(value):
        if isinstance(value,dict):
            return {k:('/failure_lab/scan' if k in ('topic','scan_topic') and v in ('scan','/scan')
                       else route(v)) for k,v in value.items()}
        if isinstance(value,list):
            return [route(v) for v in value]
        return value
    (root/'params.yaml').write_text(yaml.safe_dump(route(config),sort_keys=False))
    for name in ('tb3_sandbox.pgm','tb3_sandbox.yaml'):
        shutil.copy2(bringup/'maps'/name,root/name)
    versions=subprocess.run(['dpkg-query','-W','ros-jazzy-nav2-*','ros-jazzy-ros-gz-*','gz-*'],text=True,capture_output=True)
    (root/'packages.txt').write_text(versions.stdout+versions.stderr)
    plan=dict(experiment='Robot Failure Lab 02',repeats=args.repeats,
              trigger='>=3 sim seconds since goal submission, translating >=0.05 m/s for >=0.3 s, fresh odometry',
              change='Drop newly received scans for [trigger, trigger+2s); no buffering or replay. Control forwards all scans.',
              motion_stop='Odom speed <=0.01 m/s and |yaw rate| <=0.03 rad/s for >=0.3s; samples <=0.15s apart',
              motion_resume='After a measured stop, odom translation >=0.05 m/s for >=0.3s after window ends',
              task_timeout_sim_s=args.timeout,
              seeds='Gazebo seed 101+repeat_index, matched within each pair; AMCL and scheduling NOT controlled. Not deterministic pairs.',
              order='Normal then blackout for odd pairs; blackout then normal for even pairs',
              collision_monitor_source_timeout_s=config['collision_monitor']['ros__parameters']['source_timeout'],
              scope='Exploratory static simulation. No collision/obstacle-appearance metric, physical validation, or Vektor integration.',
              command=sys.argv,python=sys.version,platform=os.uname().release,
              source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.iterdir()})
    (root/'PROTOCOL.json').write_text(json.dumps(plan,indent=2)+'\n')
    records=[]
    for repeat in range(1,args.repeats+1):
        for blackout in ([0,1] if repeat%2 else [1,0]):
            name=f'pair-{repeat}-'+('blackout' if blackout else 'normal')
            trial=root/name
            trial.mkdir()
            env=dict(os.environ,ROS_DOMAIN_ID=str(args.domain),ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
                     GZ_PARTITION=f'rfl02-{os.getpid()}-{name}',LIBGL_ALWAYS_SOFTWARE='1',RFL_GZ_SEED=str(100+repeat))
            env.pop('ROS_LOCALHOST_ONLY',None)
            command=['ros2','launch',str(snapshot/'seeded_simulation_launch.py'),
                     'headless:=True','use_rviz:=False','use_composition:=False',f'params_file:={root / "params.yaml"}']
            (trial/'launch-command.json').write_text(json.dumps(dict(command=command,gazebo_seed=100+repeat,domain=args.domain),indent=2))
            print(f'Starting {name}',flush=True)
            sim=worker=None
            try:
                with (trial/'simulation.log').open('w') as sl,(trial/'trial.log').open('w') as tl:
                    sim=subprocess.Popen(command,env=env,stdout=sl,stderr=subprocess.STDOUT,start_new_session=True)
                    time.sleep(8)
                    worker=subprocess.Popen([sys.executable,str(snapshot/'trial.py'),'--blackout',str(blackout),
                                             '--output',str(trial),'--timeout',str(args.timeout)],
                                            env=env,stdout=tl,stderr=subprocess.STDOUT,start_new_session=True)
                    worker.wait(timeout=args.timeout*3+100)
                    if worker.returncode or not (trial/'result.json').exists():
                        raise RuntimeError(f'Infrastructure error in {name}; inspect retained logs')
            except Exception as error:
                (trial/'INFRASTRUCTURE_ERROR.txt').write_text(repr(error)+'\n')
                raise
            finally:
                if worker is not None:
                    stop(worker)
                if sim is not None:
                    stop(sim)
            record=json.loads((trial/'result.json').read_text())
            record.update(trial=name,pair=repeat,gazebo_seed=100+repeat)
            records.append(record)
            (root/'results.json').write_text(json.dumps(records,indent=2)+'\n')
            print(f'{name}: {record["outcome"]}, {record["elapsed_sim_s"]:.2f}s, metrics={record["metrics"]}',flush=True)
            if not record['injection_valid']:
                raise RuntimeError(f'Incomplete observation window: {name}; retained, not a valid injection trial')


if __name__=='__main__':
    main()
