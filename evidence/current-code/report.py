#!/usr/bin/env python3
"""Validate blackout evidence and render measured outcomes and motion."""
import argparse
import csv
import json
from pathlib import Path
import statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from core import window_metrics


def read_csv(path):
    with path.open() as f:
        return [{k:float(v) for k,v in row.items()} for row in csv.DictReader(f)]


def validate(root,record):
    trial=root/record['trial']
    scans=read_csv(trial/'scans.csv')
    odom=read_csv(trial/'odom.csv')
    commands=read_csv(trial/'commands.csv')
    feedback=read_csv(trial/'feedback.csv')
    start=record['window_start_sim_s']
    assert record['injection_valid'] and start is not None
    assert len(scans)==record['scans_received']
    for row in scans:
        expected=not(record['blackout'] and start<=row['t']<start+2)
        assert bool(row['forwarded'])==expected, 'Wrong scan gate state'
    dropped=[r for r in scans if not r['forwarded']]
    assert len(dropped)==record['scans_dropped']
    inside=[r for r in scans if start<=r['t']<start+2]
    after=[r for r in scans if r['t']>=start+2 and r['forwarded']]
    before=[r for r in scans if r['t']<start and r['forwarded']]
    assert len(inside)>=5 and before and after, 'Missing blackout/resumption evidence'
    assert not record['blackout'] or len(dropped)==len(inside)
    assert after[0]['t']-(start+2)<0.5, 'Scan delivery resumed too late'
    assert inside[0]['t']-start<0.5 and start+2-inside[-1]['t']<0.5
    assert all(b['t']-a['t']<0.5 for a,b in zip(inside,inside[1:])), 'Upstream sensor stalled'
    assert all(-0.02<=r['t']-r['acquisition']<0.5 for r in scans), 'Unexpected sensor age'
    metrics=window_metrics(odom,commands,start,2,record['observation_end_sim_s'])
    assert metrics==record['metrics'], 'Metric mismatch'
    assert metrics['window_odom_samples']>=10 and metrics['window_odom_max_gap_s']<=0.15
    assert metrics['pre_window_speed_mps']>=0.04, 'Robot not moving before window'
    assert feedback and int(max(r['recoveries'] for r in feedback))==record['recoveries']
    return scans,odom,commands


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('evidence',type=Path)
    args=parser.parse_args()
    root=args.evidence
    records=json.loads((root/'results.json').read_text())
    protocol=json.loads((root/'PROTOCOL.json').read_text())
    assert len(records)==2*protocol['repeats'], 'Incomplete planned series'
    telemetry={r['trial']:validate(root,r) for r in records}
    colors={False:'#197c9c',True:'#d66532'}
    labels={False:'Normal scans',True:'2-second blackout'}
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11})
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for r in records:
        m=r['metrics']; x=r['pair']+(.09 if r['blackout'] else -.09)
        axes[0].scatter(x,r['elapsed_sim_s'],color=colors[r['blackout']],s=70,
                        marker='o' if r['outcome']=='succeeded' else 'x')
        label=f'{r["elapsed_sim_s"]:.1f}s' if r['outcome']=='succeeded' else f'Failed\n{r["elapsed_sim_s"]:.1f}s'
        axes[0].annotate(label,(x,r['elapsed_sim_s']),xytext=(0,8),textcoords='offset points',ha='center',fontsize=9)
        if m['stop_latency_s'] is not None:
            axes[1].scatter(x,m['stop_latency_s'],color=colors[r['blackout']],s=70)
        else:
            axes[1].annotate('No sustained\nstop in window',(x,0.1),ha='center',fontsize=8,color=colors[r['blackout']])
    for enabled in (False,True):
        axes[0].plot([],[], 'o',color=colors[enabled],label=labels[enabled])
    axes[0].plot([],[], 'x',color='#444444',label='Failed task (goal not reached)')
    axes[0].set_ylabel('Goal submission to termination (sim seconds)')
    axes[0].set_ylim(0,max(r['elapsed_sim_s'] for r in records)*1.14)
    axes[0].legend(frameon=False,fontsize=9)
    axes[1].set_ylabel('Latency to sustained odometry stop (sim seconds)')
    axes[1].set_ylim(0,2.2)
    for ax in axes:
        ax.set_xlabel('Pair (matched Gazebo seed; other randomness uncontrolled)')
        ax.set_xticks(range(1,protocol['repeats']+1)); ax.grid(alpha=.2)
        ax.set_xlim(.5,protocol['repeats']+.5)
    fig.suptitle('Robot Failure Lab 02 · A two-second laser-scan blackout\nMeasured Gazebo/Nav2 results · exploratory simulation')
    fig.savefig(root/'comparison.png',dpi=170);plt.close(fig)
    # Predeclared first pair; no selection for dramatic effect.
    fig,axes=plt.subplots(2,1,figsize=(11,5.5),gridspec_kw={'height_ratios':[3,1.3]},layout='constrained',sharex=True)
    for r in [r for r in records if r['pair']==1]:
        scans,odom,commands=telemetry[r['trial']]; start=r['window_start_sim_s']; color=colors[r['blackout']]
        axes[0].plot([o['t']-start for o in odom],[o['speed'] for o in odom],color=color,label=labels[r['blackout']])
        if r['blackout']:
            axes[0].plot([c['t']-start for c in commands],[c['speed'] for c in commands],color=color,ls=':',label='Blackout: velocity command')
        y=0 if not r['blackout'] else 1
        axes[1].scatter([s['t']-start for s in scans if s['forwarded']],
                        [y for s in scans if s['forwarded']],color=color,s=8,label=labels[r['blackout']]+' delivered')
        if r['blackout']:
            axes[1].scatter([s['t']-start for s in scans if not s['forwarded']],
                            [y for s in scans if not s['forwarded']],color='black',marker='x',s=20,label='Dropped scans')
    for ax in axes:
        ax.axvspan(0,2,color='#f3c5a6',alpha=.4);ax.grid(alpha=.2);ax.set_xlim(-1,6)
    axes[0].set_ylabel('Translation speed (m/s)');axes[0].legend(frameon=False,fontsize=9)
    axes[1].set_yticks([0,1],['Normal','Blackout']);axes[1].set_xlabel('Simulated seconds from each run\'s window trigger')
    axes[1].legend(frameon=False,fontsize=8,loc='upper right')
    fig.suptitle('First pair · Scan delivery and simulated motion\nShaded interval: observation window; only blackout run loses scans')
    fig.savefig(root/'motion-and-scans.png',dpi=170);plt.close(fig)
    fmt=lambda v:'—' if v is None else f'{v:.3f}'
    lines=['# Robot Failure Lab 02: What happens during a two-second scan blackout?','',
           'Measured Gazebo/Nav2 simulation. Standalone runner; no Vektor integration or physical validation.','',
           '| Pair | Condition | Outcome | Task time (sim s) | Dropped scans | Stop latency (s) | Resume after window (s) | Recoveries |',
           '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in records:
        m=r['metrics']
        lines.append(f'| {r["pair"]} | {labels[r["blackout"]]} | {r["outcome"]} | {r["elapsed_sim_s"]:.3f} | {r["scans_dropped"]} | {fmt(m["stop_latency_s"])} | {fmt(m["resume_after_window_s"])} | {r["recoveries"]} |')
    lines+=['','## Observations','']
    for enabled in (False,True):
        group=[r for r in records if r['blackout']==enabled]; successes=[r for r in group if r['outcome']=='succeeded']
        stops=[r for r in group if r['metrics']['stop_latency_s'] is not None]
        lines.append(f'- {labels[enabled]}: {len(successes)}/{len(group)} reached the goal; {len(stops)}/{len(group)} showed a sustained odometry stop during the observation window.'+
                     (f' Median successful task time: {statistics.median(r["elapsed_sim_s"] for r in successes):.3f} simulated seconds.' if successes else ''))
    lines+=['','## Method and limits','',
       '- Fresh simulator and Nav2 per trial; original Lab 01 map, start (-2,-0.5), goal (1,0.5), yaw 0. Three pairs by default; alternating order.',
       '- After at least 3 simulated seconds and sustained translation >=0.05 m/s for 0.3 seconds, mark a two-second window. Control passes all scans. Blackout discards newly received scans; no buffering or replay; original acquisition timestamps retained.',
       '- Live graph verifies AMCL, local/global costmaps and collision monitor subscribe to the relay. Odometry and other sensors remain available. This models a scan transport outage, not complete robot blindness.',
       f'- Installed collision monitor source_timeout: {protocol["collision_monitor_source_timeout_s"]} seconds, unchanged between conditions. Both arms wait 1.5 simulated seconds after Nav2 readiness before goal submission.',
       '- A stop requires odometry translation <=0.01 m/s and absolute yaw rate <=0.03 rad/s for >=0.3 s, with sample gaps <=0.15 s. Reported latency is the start of that confirmed interval. Resumption is >=0.05 m/s for >=0.3 s after window end, only when a stop was measured. A dash means no qualifying event, not a zero latency.',
       '- Velocity commands are observed separately; odometry is simulated motion feedback, not independent physical ground truth. No new obstacle, collision metric or safety certification is included.',
       '- Gazebo seeds 101,102,103 are matched per pair. AMCL randomness, host scheduling and exact trajectory/trigger position are not controlled. This does not establish a causal completion-time effect or general reliability.',
       '- Timeouts/failures are outcomes, not successful completion times. When a task terminates early, passive telemetry continues until at least four seconds after the blackout; no new goal is sent. A stopped robot after task abort is not proof that navigation will resume automatically. Infrastructure errors are retained separately. Original Lab 01 delay uncertainty remains unresolved.',
       '- Evidence validation checks every scan against the planned gate, upstream scans during the blackout, prompt delivery afterward, odometry continuity and recalculated metrics.',
       '- sources/, PROTOCOL.json, params.yaml, packages.txt and per-trial CSVs/logs preserve provenance. Publication has not occurred.','',
       '![All trial outcomes](comparison.png)','', '![First pair motion and scan delivery](motion-and-scans.png)','']
    (root/'REPORT.md').write_text('\n'.join(lines))
    print(f'Validated {len(records)} trials and rendered REPORT.md, comparison.png, motion-and-scans.png')


if __name__=='__main__':
    main()
