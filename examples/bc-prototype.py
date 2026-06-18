"""
AMR-HUB: Behavioural Cloning prototype with (state, action) sweep.

Pipeline:
    1. Load real RTLS-style CSV (one HCW for now).
    2. Resample event log to a fixed 15-minute grid (Option A):
         - Forward-fill zone (HCW stays where they were).
         - Sparse event marker: forward-fill ONLY sustained events
           (workstation, attend_patient, occupy_content);
           door_access fires for one grid point then decays to "none".
    3. Split into shifts on long gaps.
    4. Markov bootstrap on zone sequences to generate synthetic training data
       (Laplace-smoothed P(next_zone | curr_zone, time_bucket)).
    5. Train one BC model per (state_variant, action_variant) combination.
    6. Evaluate every model on held-out REAL data:
         - top-1 / top-k accuracy
         - TV distance on zone-frequency and event-frequency distributions
           between policy rollouts and held-out real.
    7. Produce a comparison table and an Occam recommendation:
         smallest state where rollouts pass the distributional threshold
         AND where the next bigger state gives < ELBOW_THRESHOLD top-1 gain.

Run:
    python bc_prototype.py --csv path/to/your.csv
    python bc_prototype.py --csv path/to/your.csv --mode single
    python bc_prototype.py --csv path/to/your.csv --out-csv results.csv
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import jax
import jax.numpy as jnp
import numpy as np
import optax
from flax import linen as nn
from flax.training import train_state


# ============================================================
# Constants
# ============================================================

N_TIME_BUCKETS = 4
STEP_MINUTES = 15
SHIFT_GAP_HOURS = 8

SUSTAINED_EVENTS = {"workstation", "attend_patient"}
TRANSIENT_EVENTS = {"door_access"}
TERMINAL_EVENTS = {"occupy_content"}
EVENT_NONE = "none"

# Occam thresholds — tune as needed.
ELBOW_THRESHOLD = 0.02  # < 2% top-1 gain → not worth the extra feature
TV_THRESHOLD_ZONES = 0.20
TV_THRESHOLD_EVENTS = 0.20

DWELL_BINS = [1, 2, 4, 8, 16]


# ============================================================
# 1. CSV loader + resampling
# ============================================================


def parse_csv(path: str) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            r["timestamp"] = datetime.fromisoformat(r["timestamp"])
            r["hcw_id"] = int(r["hcw_id"])
            r["zone"] = r["location"].split(":")[-1].strip()
            rows.append(r)
    rows.sort(key=lambda r: (r["hcw_id"], r["timestamp"]))
    return rows


def split_into_shifts(
    events: list[dict], gap_hours: int = SHIFT_GAP_HOURS
) -> list[list[dict]]:
    """
    Split a single HCW's events into shifts. A shift boundary occurs when:
      - the gap to the next event exceeds `gap_hours`, OR
      - the current event is a TERMINAL event (occupy_content).
    Terminal events are kept as the FINAL row of their shift.
    """
    if not events:
        return []
    shifts = [[events[0]]]
    for prev, curr in zip(events, events[1:]):
        gap_too_long = (curr["timestamp"] - prev["timestamp"]) > timedelta(
            hours=gap_hours
        )
        prev_was_terminal = prev["event_type"] in TERMINAL_EVENTS
        if gap_too_long or prev_was_terminal:
            shifts.append([curr])
        else:
            shifts[-1].append(curr)
    return shifts


def time_bucket_of(hr: int) -> int:
    if hr < 6:
        return 0
    if hr < 12:
        return 1
    if hr < 18:
        return 2
    return 3


def resample_shift(shift: list[dict], step_minutes: int = STEP_MINUTES) -> list[dict]:
    """
    Resample one shift to a fixed time grid.
    Returns list of {time, zone, event_type, time_bucket}.
    """
    if not shift:
        return []
    start = shift[0]["timestamp"]
    end = shift[-1]["timestamp"]
    step = timedelta(minutes=step_minutes)

    out = []
    t = start
    event_idx = 0
    curr_zone = shift[0]["zone"]
    e0 = shift[0]["event_type"]
    curr_event = e0 if e0 in SUSTAINED_EVENTS else EVENT_NONE

    while t <= end:
        # Apply all events that have occurred up to t.
        while event_idx + 1 < len(shift) and shift[event_idx + 1]["timestamp"] <= t:
            event_idx += 1
            e = shift[event_idx]
            curr_zone = e["zone"]
            if e["event_type"] in SUSTAINED_EVENTS:
                curr_event = e["event_type"]
            elif e["event_type"] in TRANSIENT_EVENTS:
                curr_event = e["event_type"]  # one-step marker

        out.append(
            {
                "time": t,
                "zone": curr_zone,
                "event_type": curr_event,
                "time_bucket": time_bucket_of(t.hour),
            }
        )

        if curr_event in TRANSIENT_EVENTS:
            curr_event = EVENT_NONE
        t += step

    return out


def load_real_data(csv_path: str, hcw_id: int | None = None) -> list[list[dict]]:
    rows = parse_csv(csv_path)
    if hcw_id is not None:
        rows = [r for r in rows if r["hcw_id"] == hcw_id]
    if not rows:
        raise ValueError(f"No rows for hcw_id={hcw_id}")

    by_hcw: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_hcw[r["hcw_id"]].append(r)

    shifts = []
    for events in by_hcw.values():
        for s in split_into_shifts(events):
            resampled = resample_shift(s)
            if len(resampled) >= 4:
                shifts.append(resampled)
    return shifts


# ============================================================
# 2. Vocab
# ============================================================


@dataclasses.dataclass
class Vocab:
    zones: list[str]
    events: list[str]
    zone_to_idx: dict[str, int]
    event_to_idx: dict[str, int]

    @property
    def n_zones(self) -> int:
        return len(self.zones)

    @property
    def n_events(self) -> int:
        return len(self.events)


def build_vocab(shifts: list[list[dict]]) -> Vocab:
    zs, es = set(), set()
    for s in shifts:
        for gp in s:
            zs.add(gp["zone"])
            es.add(gp["event_type"])
    zones = sorted(zs)
    events = sorted(es)
    return Vocab(
        zones,
        events,
        {z: i for i, z in enumerate(zones)},
        {e: i for i, e in enumerate(events)},
    )


# ============================================================
# 3. Markov bootstrap + event marginals
# ============================================================


def fit_markov(shifts, vocab: Vocab, alpha: float = 0.5) -> np.ndarray:
    n_z = vocab.n_zones
    counts = np.full((N_TIME_BUCKETS, n_z, n_z), alpha, dtype=np.float64)
    for shift in shifts:
        for gp1, gp2 in zip(shift[:-1], shift[1:]):
            z = vocab.zone_to_idx[gp1["zone"]]
            zn = vocab.zone_to_idx[gp2["zone"]]
            counts[gp1["time_bucket"], z, zn] += 1.0
    return counts / counts.sum(axis=-1, keepdims=True)


def event_dist_per_zone(shifts, vocab: Vocab, alpha: float = 0.5) -> np.ndarray:
    """
    P(event_type | zone) from real shifts.
    Terminal events get zero probability mass — they should never appear
    in synthetic mid-shift data (synthetic shifts have no real "end").
    """
    n_z, n_e = vocab.n_zones, vocab.n_events
    counts = np.full((n_z, n_e), alpha, dtype=np.float64)
    for shift in shifts:
        for gp in shift:
            if gp["event_type"] in TERMINAL_EVENTS:
                continue
            counts[
                vocab.zone_to_idx[gp["zone"]], vocab.event_to_idx[gp["event_type"]]
            ] += 1.0
    # Zero out any terminal event rows entirely (in case alpha smoothing
    # gave them mass).
    for e_name in TERMINAL_EVENTS:
        if e_name in vocab.event_to_idx:
            counts[:, vocab.event_to_idx[e_name]] = 0.0
    # Renormalise; if a zone now has all-zero row (very rare), uniform fallback.
    row_sums = counts.sum(axis=-1, keepdims=True)
    row_sums = np.where(row_sums == 0, 1.0, row_sums)
    return counts / row_sums


def sample_synthetic_shift(T, P_event, length, vocab, rng, start_zone, start_hour):
    out = []
    z = start_zone
    t0 = datetime(2024, 1, 1, start_hour, 0, 0)
    for step in range(length):
        t = t0 + step * timedelta(minutes=STEP_MINUTES)
        tb = time_bucket_of(t.hour)
        e_idx = int(rng.choice(vocab.n_events, p=P_event[z]))
        out.append(
            {
                "time": t,
                "zone": vocab.zones[z],
                "event_type": vocab.events[e_idx],
                "time_bucket": tb,
            }
        )
        z = int(rng.choice(vocab.n_zones, p=T[tb, z]))
    return out


def build_synthetic_dataset(real_shifts, vocab, n_trajectories=200, length=80, seed=1):
    T = fit_markov(real_shifts, vocab)
    P_event = event_dist_per_zone(real_shifts, vocab)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_trajectories):
        start = int(rng.integers(vocab.n_zones))
        start_hour = int(rng.choice([6, 7, 8, 14, 22]))
        out.append(
            sample_synthetic_shift(T, P_event, length, vocab, rng, start, start_hour)
        )
    return out


# ============================================================
# 4. State / Action variants
# ============================================================

STATE_VARIANTS = {
    "S1_zone": ["curr_zone"],
    "S2_zone_time": ["curr_zone", "time_bucket"],
    "S3_zone_time_prev": ["curr_zone", "time_bucket", "prev_zone"],
    "S4_full_event": ["curr_zone", "time_bucket", "prev_zone", "curr_event"],
    "S5_full_duration": [
        "curr_zone",
        "time_bucket",
        "prev_zone",
        "curr_event",
        "dwell_bin",
    ],
}

ACTION_VARIANTS = {
    "A1_next_zone": "next_zone",
    "A2_next_event": "next_event",
    "A3_joint": "joint",
}


def dwell_bin_index(steps_in_zone: int) -> int:
    for i, b in enumerate(DWELL_BINS):
        if steps_in_zone <= b:
            return i
    return len(DWELL_BINS)


def feature_vocab_size(name: str, vocab: Vocab) -> int:
    if name == "curr_zone":
        return vocab.n_zones
    if name == "time_bucket":
        return N_TIME_BUCKETS
    if name == "prev_zone":
        return vocab.n_zones + 1
    if name == "curr_event":
        return vocab.n_events
    if name == "dwell_bin":
        return len(DWELL_BINS) + 1
    raise ValueError(name)


def action_vocab_size(kind: str, vocab: Vocab) -> int:
    if kind == "next_zone":
        return vocab.n_zones
    if kind == "next_event":
        return vocab.n_events
    if kind == "joint":
        return vocab.n_zones * vocab.n_events
    raise ValueError(kind)


def encode_action(kind, nz, ne, vocab):
    if kind == "next_zone":
        return nz
    if kind == "next_event":
        return ne
    if kind == "joint":
        return nz * vocab.n_events + ne
    raise ValueError(kind)


def shifts_to_sa(shifts, feature_names, action_kind, vocab: Vocab):
    """
    Build (X, y) for one (state, action) combination.
    Skips transitions where the NEXT event is terminal (occupy_content):
    the policy is not asked to predict shift end, only mid-shift decisions.
    """
    X_rows, y_rows = [], []
    for shift in shifts:
        prev_z = vocab.n_zones
        dwell = 1
        for i in range(len(shift) - 1):
            gp = shift[i]
            gpn = shift[i + 1]

            # Skip if the next event is terminal — not a learnable decision.
            if gpn["event_type"] in TERMINAL_EVENTS:
                continue

            cz = vocab.zone_to_idx[gp["zone"]]
            tb = gp["time_bucket"]
            ce = vocab.event_to_idx[gp["event_type"]]
            db = dwell_bin_index(dwell)

            row = []
            for f in feature_names:
                if f == "curr_zone":
                    row.append(cz)
                elif f == "time_bucket":
                    row.append(tb)
                elif f == "prev_zone":
                    row.append(prev_z)
                elif f == "curr_event":
                    row.append(ce)
                elif f == "dwell_bin":
                    row.append(db)
            X_rows.append(row)

            nz = vocab.zone_to_idx[gpn["zone"]]
            ne = vocab.event_to_idx[gpn["event_type"]]
            y_rows.append(encode_action(action_kind, nz, ne, vocab))

            if gpn["zone"] == gp["zone"]:
                dwell += 1
            else:
                dwell = 1
                prev_z = cz
    return np.array(X_rows, dtype=np.int32), np.array(y_rows, dtype=np.int32)


# ============================================================
# 5. Flax policy
# ============================================================


class BCPolicy(nn.Module):
    feature_vocab_sizes: tuple
    n_actions: int
    embed_dim: int = 16
    hidden_dim: int = 64

    @nn.compact
    def __call__(self, x):
        pieces = []
        for i, vsize in enumerate(self.feature_vocab_sizes):
            pieces.append(nn.Embed(vsize, self.embed_dim, name=f"embed_{i}")(x[:, i]))
        h = jnp.concatenate(pieces, axis=-1)
        h = nn.relu(nn.Dense(self.hidden_dim)(h))
        h = nn.relu(nn.Dense(self.hidden_dim)(h))
        return nn.Dense(self.n_actions)(h)


def count_params(params) -> int:
    return int(sum(p.size for p in jax.tree.leaves(params)))


@dataclasses.dataclass
class TrainConfig:
    batch_size: int = 256
    n_epochs: int = 30
    learning_rate: float = 3e-3
    seed: int = 42


def make_train_state(model, n_features, rng, config: TrainConfig):
    params = model.init(rng, jnp.zeros((1, n_features), dtype=jnp.int32))["params"]
    return train_state.TrainState.create(
        apply_fn=model.apply, params=params, tx=optax.adam(config.learning_rate)
    )


def make_train_eval_steps(n_actions: int):
    @jax.jit
    def train_step(state, bx, by):
        def loss_fn(params):
            logits = state.apply_fn({"params": params}, bx)
            oh = jax.nn.one_hot(by, n_actions)
            return optax.softmax_cross_entropy(logits, oh).mean(), logits

        (loss, logits), grads = jax.value_and_grad(loss_fn, has_aux=True)(state.params)
        state = state.apply_gradients(grads=grads)
        acc = (jnp.argmax(logits, axis=-1) == by).mean()
        return state, loss, acc

    @jax.jit
    def eval_step(state, x, y):
        logits = state.apply_fn({"params": state.params}, x)
        top1 = (jnp.argmax(logits, axis=-1) == y).mean()
        k = min(3, n_actions)
        topk_idx = jnp.argsort(logits, axis=-1)[:, -k:]
        topk = jnp.any(topk_idx == y[:, None], axis=-1).mean()
        return top1, topk

    return train_step, eval_step


def iterate_batches(x, y, batch_size, rng):
    n = x.shape[0]
    idx = rng.permutation(n)
    for start in range(0, n, batch_size):
        sl = idx[start : start + batch_size]
        yield x[sl], y[sl]


# ============================================================
# 6. Rollout (bookkeeping, not simulation)
# ============================================================


def policy_rollout(
    state, feature_names, action_kind, length, real_seed_shift, vocab: Vocab, rng
):
    if not real_seed_shift:
        return []
    gp0 = real_seed_shift[0]
    cz = vocab.zone_to_idx[gp0["zone"]]
    tb = gp0["time_bucket"]
    ce = vocab.event_to_idx[gp0["event_type"]]
    prev_z = vocab.n_zones
    dwell = 1

    traj = [dict(gp0)]
    for step in range(1, length):
        row = []
        for f in feature_names:
            if f == "curr_zone":
                row.append(cz)
            elif f == "time_bucket":
                row.append(tb)
            elif f == "prev_zone":
                row.append(prev_z)
            elif f == "curr_event":
                row.append(ce)
            elif f == "dwell_bin":
                row.append(dwell_bin_index(dwell))
        x = jnp.array([row], dtype=jnp.int32)
        logits = state.apply_fn({"params": state.params}, x)
        probs = np.array(jax.nn.softmax(logits)[0])
        a = int(rng.choice(len(probs), p=probs))

        if action_kind == "next_zone":
            nz, ne = a, ce
        elif action_kind == "next_event":
            nz, ne = cz, a
        else:
            nz = a // vocab.n_events
            ne = a % vocab.n_events

        if nz == cz:
            dwell += 1
        else:
            dwell = 1
            prev_z = cz
        cz, ce = nz, ne
        tb = min(int((step / length) * N_TIME_BUCKETS), N_TIME_BUCKETS - 1)
        traj.append(
            {
                "time": None,
                "zone": vocab.zones[cz],
                "event_type": vocab.events[ce],
                "time_bucket": tb,
            }
        )
    return traj


def freq(items, universe):
    c = Counter(items)
    arr = np.array([c.get(u, 0) for u in universe], dtype=np.float64)
    s = arr.sum()
    return arr / s if s else arr


def total_variation(p, q):
    return 0.5 * float(np.abs(p - q).sum())


# ============================================================
# 7. Sweep runner
# ============================================================


@dataclasses.dataclass
class SweepResult:
    state_name: str
    action_name: str
    n_features: int
    n_params: int
    top1: float
    topk: float
    tv_zones: float
    tv_events: float

    def passes(self):
        return (
            self.tv_zones <= TV_THRESHOLD_ZONES
            and self.tv_events <= TV_THRESHOLD_EVENTS
        )


def run_one(
    state_name,
    action_name,
    feature_names,
    action_kind,
    train_shifts,
    eval_shifts,
    synthetic,
    vocab,
    cfg: TrainConfig,
):
    X_syn, y_syn = shifts_to_sa(synthetic, feature_names, action_kind, vocab)
    X_real, y_real = shifts_to_sa(train_shifts, feature_names, action_kind, vocab)
    X_train = np.concatenate([X_syn, X_real]) if len(X_real) else X_syn
    y_train = np.concatenate([y_syn, y_real]) if len(y_real) else y_syn

    X_eval, y_eval = shifts_to_sa(eval_shifts, feature_names, action_kind, vocab)
    if len(X_eval) == 0:
        raise ValueError(f"No eval pairs for {state_name}/{action_name}")

    feat_sizes = tuple(feature_vocab_size(f, vocab) for f in feature_names)
    n_actions = action_vocab_size(action_kind, vocab)
    model = BCPolicy(feature_vocab_sizes=feat_sizes, n_actions=n_actions)
    rng_key = jax.random.PRNGKey(cfg.seed)
    state = make_train_state(model, len(feature_names), rng_key, cfg)
    n_params = count_params(state.params)

    train_step, eval_step = make_train_eval_steps(n_actions)
    np_rng = np.random.default_rng(cfg.seed)
    for _ in range(cfg.n_epochs):
        for bx, by in iterate_batches(X_train, y_train, cfg.batch_size, np_rng):
            state, _, _ = train_step(state, jnp.array(bx), jnp.array(by))

    top1, topk = eval_step(state, jnp.array(X_eval), jnp.array(y_eval))
    top1, topk = float(top1), float(topk)

    rollout = policy_rollout(
        state,
        feature_names,
        action_kind,
        length=len(eval_shifts[0]),
        real_seed_shift=eval_shifts[0],
        vocab=vocab,
        rng=np_rng,
    )
    real_z = [
        gp["zone"]
        for s in eval_shifts
        for gp in s
        if gp["event_type"] not in TERMINAL_EVENTS
    ]
    real_e = [
        gp["event_type"]
        for s in eval_shifts
        for gp in s
        if gp["event_type"] not in TERMINAL_EVENTS
    ]
    pred_z = [gp["zone"] for gp in rollout if gp["event_type"] not in TERMINAL_EVENTS]
    pred_e = [
        gp["event_type"] for gp in rollout if gp["event_type"] not in TERMINAL_EVENTS
    ]
    tv_z = total_variation(freq(real_z, vocab.zones), freq(pred_z, vocab.zones))
    tv_e = total_variation(freq(real_e, vocab.events), freq(pred_e, vocab.events))

    return SweepResult(
        state_name, action_name, len(feature_names), n_params, top1, topk, tv_z, tv_e
    ), rollout


def occam_recommendation(state_results: list[SweepResult]) -> str:
    state_results = sorted(state_results, key=lambda r: r.n_features)
    passing = [r for r in state_results if r.passes()]
    pick_tv = passing[0].state_name if passing else None

    pick_elbow = None
    for i in range(len(state_results) - 1):
        gain = state_results[i + 1].top1 - state_results[i].top1
        if gain < ELBOW_THRESHOLD:
            pick_elbow = state_results[i].state_name
            break
    if pick_elbow is None:
        pick_elbow = state_results[-1].state_name

    msg = ["\nOCCAM RECOMMENDATION", "-" * 60]
    msg.append(
        f"Distributional filter (TV ≤ {TV_THRESHOLD_ZONES}/{TV_THRESHOLD_EVENTS}):"
    )
    msg.append(f"  → smallest passing variant: {pick_tv or 'NONE PASSED'}")
    msg.append(f"Elbow filter (top-1 gain < {ELBOW_THRESHOLD:.2f}):")
    msg.append(f"  → plateau variant: {pick_elbow}")

    if pick_tv and pick_tv == pick_elbow:
        msg.append(f"\nBoth filters agree → recommend {pick_tv}.")
    elif pick_tv and pick_elbow:
        msg.append(f"\nFilters disagree: TV says {pick_tv}, elbow says {pick_elbow}.")
        msg.append("This is a modelling judgment, not an automatic answer —")
        msg.append("inspect the table and decide based on which gap is acceptable.")
    else:
        msg.append("\nNo variant passed the distributional check.")
        msg.append("Possible causes: too little real data, or a feature is missing.")
    return "\n".join(msg)


def print_table(results: list[SweepResult]):
    print(
        f"\n{'State':<22}{'Action':<18}{'#feat':>6}{'#params':>10}"
        f"{'top1':>8}{'top3':>8}{'TV_zone':>10}{'TV_evt':>10}{'pass':>6}"
    )
    print("-" * 98)
    for r in results:
        print(
            f"{r.state_name:<22}{r.action_name:<18}{r.n_features:>6}"
            f"{r.n_params:>10}{r.top1:>8.3f}{r.topk:>8.3f}"
            f"{r.tv_zones:>10.3f}{r.tv_events:>10.3f}"
            f"{('  ✓' if r.passes() else '  ✗'):>6}"
        )


def save_csv(results, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "state",
                "action",
                "n_features",
                "n_params",
                "top1",
                "top3",
                "tv_zones",
                "tv_events",
                "pass",
            ]
        )
        for r in results:
            w.writerow(
                [
                    r.state_name,
                    r.action_name,
                    r.n_features,
                    r.n_params,
                    f"{r.top1:.4f}",
                    f"{r.topk:.4f}",
                    f"{r.tv_zones:.4f}",
                    f"{r.tv_events:.4f}",
                    "1" if r.passes() else "0",
                ]
            )


# ============================================================
# Data-artefact saving (for inspection / showing in meetings)
# ============================================================


def save_shifts_csv(shifts, path, source_label):
    """
    Save a list of resampled shifts to one flat CSV. Columns:
    source, shift_idx, step_idx, time, zone, event_type, time_bucket.
    """
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "source",
                "shift_idx",
                "step_idx",
                "time",
                "zone",
                "event_type",
                "time_bucket",
            ]
        )
        for si, shift in enumerate(shifts):
            for step, gp in enumerate(shift):
                t = gp["time"].isoformat() if gp.get("time") is not None else ""
                w.writerow(
                    [
                        source_label,
                        si,
                        step,
                        t,
                        gp["zone"],
                        gp["event_type"],
                        gp["time_bucket"],
                    ]
                )


def save_markov_csv(T, vocab: Vocab, path):
    """
    Save the Markov transition table P(next_zone | curr_zone, time_bucket)
    as a long-format CSV for easy inspection.
    """
    tb_names = ["0_night", "1_morning", "2_afternoon", "3_evening"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_bucket", "curr_zone", "next_zone", "probability"])
        for tb in range(N_TIME_BUCKETS):
            for z in range(vocab.n_zones):
                for zn in range(vocab.n_zones):
                    w.writerow(
                        [
                            tb_names[tb],
                            vocab.zones[z],
                            vocab.zones[zn],
                            f"{T[tb, z, zn]:.4f}",
                        ]
                    )


def save_event_dist_csv(P_event, vocab: Vocab, path):
    """Save P(event_type | zone) as a long-format CSV."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zone", "event_type", "probability"])
        for z in range(vocab.n_zones):
            for e in range(vocab.n_events):
                w.writerow([vocab.zones[z], vocab.events[e], f"{P_event[z, e]:.4f}"])


def save_rollouts_csv(rollouts: dict, path):
    """
    Save a dict of {variant_name: rollout_trajectory} to one CSV.
    Columns: variant, step_idx, zone, event_type, time_bucket.
    """
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "step_idx", "zone", "event_type", "time_bucket"])
        for variant, rollout in rollouts.items():
            for step, gp in enumerate(rollout):
                w.writerow(
                    [variant, step, gp["zone"], gp["event_type"], gp["time_bucket"]]
                )


# ============================================================
# 8. Modes
# ============================================================


def split_train_eval(real_shifts):
    if len(real_shifts) >= 2:
        n_eval = max(1, len(real_shifts) // 5)
        return real_shifts[:-n_eval], real_shifts[-n_eval:]
    s = real_shifts[0]
    split = int(0.8 * len(s))
    return [s[:split]], [s[split:]]


def run_sweep(real_shifts, vocab, out_csv, data_dir=None):
    train_shifts, eval_shifts = split_train_eval(real_shifts)
    print(f"Shifts: {len(train_shifts)} train, {len(eval_shifts)} eval")
    print(
        f"Total grid points: "
        f"{sum(len(s) for s in train_shifts)} train, "
        f"{sum(len(s) for s in eval_shifts)} eval"
    )
    print(f"Vocab: {vocab.n_zones} zones {vocab.zones}")
    print(f"       {vocab.n_events} events {vocab.events}")

    synthetic = build_synthetic_dataset(
        train_shifts, vocab, n_trajectories=200, length=80, seed=1
    )
    print(f"Synthetic: {len(synthetic)} shifts × {len(synthetic[0])} steps")

    # Save the upstream data artefacts.
    if data_dir:
        import os

        os.makedirs(data_dir, exist_ok=True)
        save_shifts_csv(real_shifts, f"{data_dir}/resampled_real.csv", "real")
        save_shifts_csv(
            train_shifts, f"{data_dir}/resampled_real_train.csv", "real_train"
        )
        save_shifts_csv(eval_shifts, f"{data_dir}/resampled_real_eval.csv", "real_eval")
        save_shifts_csv(synthetic, f"{data_dir}/synthetic.csv", "synthetic")
        save_markov_csv(
            fit_markov(train_shifts, vocab), vocab, f"{data_dir}/markov_transitions.csv"
        )
        save_event_dist_csv(
            event_dist_per_zone(train_shifts, vocab),
            vocab,
            f"{data_dir}/event_dist_per_zone.csv",
        )
        print(f"Saved data artefacts → {data_dir}/")

    cfg = TrainConfig()
    rollouts: dict[str, list[dict]] = {}

    # Include the real held-out shift as a baseline for visual comparison.
    if eval_shifts:
        rollouts["REAL_heldout"] = eval_shifts[0]

    print("\n" + "=" * 70)
    print("PHASE 1 — STATE SWEEP (action = next_event)")
    print("=" * 70)
    state_results = []
    for sname, fnames in STATE_VARIANTS.items():
        print(f"  {sname:<22} ...", end=" ", flush=True)
        r, rollout = run_one(
            sname,
            "A2_next_event",
            fnames,
            "next_event",
            train_shifts,
            eval_shifts,
            synthetic,
            vocab,
            cfg,
        )
        state_results.append(r)
        rollouts[f"{sname}__A2_next_event"] = rollout
        print(
            f"top1={r.top1:.3f}  TVz={r.tv_zones:.3f}  TVe={r.tv_events:.3f}"
            f"  {'pass' if r.passes() else 'fail'}"
        )
    print_table(state_results)
    print(occam_recommendation(state_results))

    print("\n" + "=" * 70)
    print("PHASE 2 — ACTION SWEEP (state = best from Phase 1)")
    print("=" * 70)
    passing = [r for r in state_results if r.passes()]
    if passing:
        best_state = min(passing, key=lambda r: r.n_features).state_name
    else:
        best_state = state_results[-1].state_name
    print(f"Best state from Phase 1: {best_state}")
    best_fnames = STATE_VARIANTS[best_state]

    action_results = []
    for aname, akind in ACTION_VARIANTS.items():
        print(f"  {aname:<18} ...", end=" ", flush=True)
        r, rollout = run_one(
            best_state,
            aname,
            best_fnames,
            akind,
            train_shifts,
            eval_shifts,
            synthetic,
            vocab,
            cfg,
        )
        action_results.append(r)
        rollouts[f"{best_state}__{aname}"] = rollout
        print(
            f"top1={r.top1:.3f}  TVz={r.tv_zones:.3f}  TVe={r.tv_events:.3f}"
            f"  {'pass' if r.passes() else 'fail'}"
        )
    print_table(action_results)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Recommended state: {best_state}  →  features: {best_fnames}")
    best_action = max(action_results, key=lambda r: r.top1).action_name
    print(f"Most learnable action under that state: {best_action}")
    print("\nNote: 'most learnable' ≠ 'best for IRL'. For IRL prefer next_event")
    print("or joint — event prediction is the more informative target and the")
    print("one the reward function will care about.")

    if out_csv:
        save_csv(state_results + action_results, out_csv)
        print(f"\nResults written to: {out_csv}")

    if data_dir:
        save_rollouts_csv(rollouts, f"{data_dir}/rollouts.csv")
        print(f"Rollouts written to: {data_dir}/rollouts.csv")


def run_single(real_shifts, vocab):
    train_shifts, eval_shifts = split_train_eval(real_shifts)
    synthetic = build_synthetic_dataset(
        train_shifts, vocab, n_trajectories=200, length=80, seed=1
    )
    cfg = TrainConfig()
    r, _ = run_one(
        "S3_zone_time_prev",
        "A2_next_event",
        STATE_VARIANTS["S3_zone_time_prev"],
        "next_event",
        train_shifts,
        eval_shifts,
        synthetic,
        vocab,
        cfg,
    )
    print_table([r])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--hcw", type=int, default=1)
    p.add_argument("--mode", choices=["sweep", "single"], default="sweep")
    p.add_argument("--out-csv", default=None)
    p.add_argument(
        "--save-data",
        default=None,
        help="Directory to save resampled real, synthetic, "
        "Markov tables, and rollouts as CSVs",
    )
    args = p.parse_args()

    real_shifts = load_real_data(args.csv, hcw_id=args.hcw)
    vocab = build_vocab(real_shifts)

    if args.mode == "sweep":
        run_sweep(real_shifts, vocab, args.out_csv, data_dir=args.save_data)
    else:
        run_single(real_shifts, vocab)


if __name__ == "__main__":
    main()
