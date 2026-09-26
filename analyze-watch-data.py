#!/usr/bin/env python3
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else 'sensor-traces.csv')
if not path.exists():
    raise SystemExit(f'File not found: {path}')

sessions = defaultdict(list)
with path.open(newline='') as f:
    for row in csv.DictReader(f):
        sessions[(row['label'], row['session_id'])].append({
            't': float(row['elapsed_ms']),
            'x': float(row['x']),
            'y': float(row['y']),
            'z': float(row['z']),
        })


def normalize(v):
    length = math.sqrt(sum(c*c for c in v))
    if length < 1e-9:
        return None
    return tuple(c/length for c in v)


def avg_orientation(samples, tail_ms=800):
    if not samples:
        return None
    end = max(s['t'] for s in samples)
    tail = [s for s in samples if s['t'] >= end - tail_ms]
    if not tail:
        tail = samples
    return normalize((
        statistics.fmean(s['x'] for s in tail),
        statistics.fmean(s['y'] for s in tail),
        statistics.fmean(s['z'] for s in tail),
    ))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))

mouth = [avg_orientation(v) for (label, _), v in sessions.items() if label == 'mouth_raise']
mouth = [m for m in mouth if m]
if not mouth:
    raise SystemExit('No mouth_raise sessions found. Record them on the watch first.')

reference = normalize(tuple(statistics.fmean(m[i] for m in mouth) for i in range(3)))
print('Sessions:')
counts = defaultdict(int)
for label, _ in sessions:
    counts[label] += 1
for label in sorted(counts):
    print(f'  {label}: {counts[label]}')

print('\nReference mouth orientation:')
print('  x={:.4f} y={:.4f} z={:.4f}'.format(*reference))

by_label = defaultdict(list)
for (label, sid), samples in sessions.items():
    orientation = avg_orientation(samples)
    if orientation:
        by_label[label].append(dot(reference, orientation))

print('\nEnd-pose similarity to mouth reference (1.0 = identical):')
for label in sorted(by_label):
    vals = by_label[label]
    print(f'  {label:12s} min={min(vals):.4f} avg={statistics.fmean(vals):.4f} max={max(vals):.4f}')

mouth_vals = by_label.get('mouth_raise', [])
negative_vals = by_label.get('view_time', []) + by_label.get('normal_move', [])
if mouth_vals and negative_vals:
    low_mouth = min(mouth_vals)
    high_negative = max(negative_vals)
    if low_mouth > high_negative:
        suggested = max(0.90, min(0.995, (low_mouth + high_negative) / 2))
        print('\nGood orientation separation detected.')
        print(f'  Suggested similarityThreshold ≈ {suggested:.4f}')
    else:
        print('\nOrientation alone overlaps between mouth and non-mouth samples.')
        print('  Keep the movement/hold state machine and collect more samples before tuning.')
        print(f'  mouth minimum={low_mouth:.4f}, non-mouth maximum={high_negative:.4f}')
else:
    print('\nNeed mouth_raise plus view_time/normal_move sessions before suggesting a threshold.')
