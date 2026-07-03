"""
AMR-HUB: Behavioural-cloning prototype, rebuilt against the real DuckDB schema.

WHAT CHANGED FROM THE CSV PROTOTYPE
-----------------------------------
The original prototype assumed a flat CSV with a single `zone` column and four
event types (workstation, attend_patient, door_access, occupy_content). The
actual data is relational and different in four load-bearing ways:

1. No `zone`. Location = SourceKey, and SourceKey lives in a DIFFERENT key space
   per InteractionTypeClass:
       Door Message -> Ref.Door        (13 keys)
       Roster       -> Ref.Roster      (2 keys)
       Workstation  -> Ref.Workstation (36 keys)
       Flowsheet    -> 168 keys (likely a location/department; NOT the 119
                       FlowsheetTemplates, which are keyed by InteractionTypeKey)
   We therefore resolve location per-class and NAMESPACE it ("door:...",
   "ws:...", "fs:...") so keys from different classes never collide.

2. Shifts are explicit. Roster Start / Roster End paired by LinkKey define the
   shift window. LinkKey is populated ONLY for roster events. So we window
   activity by rostered intervals instead of the old occupy_content / 8h-gap
   heuristic. TERMINAL_EVENTS and split_into_shifts are gone.

3. No scarcity. ~2.8M events across ~3,609 staff. The Markov *bootstrap* is
   retired as a data generator; Markov survives as a first-class BASELINE model.

4. New features: Role/Staff Group (Ref.Staff), fine activity (32 InteractionType
   values), and the patient-infection link (PatientDurableKey -> PatientInfection).

WHAT THIS SCRIPT DOES
---------------------
    load  -> build one namespaced touchpoint sequence per (staff, shift)
    battery -> quantify learnability WITHOUT committing to IRL:
                 - sequence entropy + conditional entropy H(next | state)
                 - process-style variant statistics (how many distinct paths)
                 - Markov baseline: held-out top-1 / top-k / perplexity
                 - optional BC: held-out top-1 / top-k
    sweep -> the Occam state-variant comparison, now over real features.

The battery is the part that answers "is this learnable / too noisy". It runs
with numpy + duckdb alone. BC (Flax/optax) is optional and guarded.

Run:
    python bc_prototype.py --db amr.duckdb battery
    python bc_prototype.py --db amr.duckdb battery --order 2
    python bc_prototype.py --db amr.duckdb sweep --bc
"""

from __future__ import annotations

import argparse
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import duckdb
import numpy as np

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

N_TIME_BUCKETS = 4  # 0-6, 6-12, 12-18, 18-24
KEEP_UNROSTERED = False  # events outside any rostered interval
MIN_SHIFT_EVENTS = 3  # shifts shorter than this are dropped
TOPK = 3

# Class prefixes used to namespace locations across key spaces.
CLASS_PREFIX = {
    "Door Message": "door",
    "Workstation": "ws",
    "Flowsheet": "fs",
    "Roster": "roster",
}

# Which ref table each class's SourceKey resolves against. Flowsheet is left
# unresolved by default (see note 1) and falls back to the raw key; set
# FLOWSHEET_SOURCE_TABLE once a join test confirms where 168 keys point.
SOURCE_REF = {
    "Door Message": ("Ref.Door", "DoorKey", "DoorName"),
    "Workstation": ("Ref.Workstation", "WorkstationKey", "WorkstationName"),
    "Roster": ("Ref.Roster", "RosterKey", "RosterName"),
}
FLOWSHEET_SOURCE_TABLE = None  # e.g. ("Ref.Department", "DepartmentKey", "RoomName")


# ------------------------------------------------------------------
# 1. Load: relational -> namespaced touchpoint sequences
# ------------------------------------------------------------------


@dataclass
class Step:
    ts: float  # epoch seconds
    location: str  # namespaced, e.g. "ws:WOW-3"
    iclass: str  # InteractionTypeClass
    itype: str  # InteractionType (fine)
    role: str
    patient: str | None
    time_bucket: int


@dataclass
class Shift:
    staff: str
    link_key: int
    steps: list[Step] = field(default_factory=list)


def _load_ref_map(con, table, key_col, name_col) -> dict[int, str]:
    rows = con.execute(f"select {key_col}, {name_col} from {table}").fetchall()
    return {int(k): str(v) for k, v in rows if k is not None}


def load_shifts(con) -> list[Shift]:
    """Build per-(staff, shift) namespaced touchpoint sequences from DuckDB."""
    # Resolve the class-specific location maps once.
    loc_maps: dict[str, dict[int, str]] = {}
    for iclass, (tbl, kcol, ncol) in SOURCE_REF.items():
        loc_maps[iclass] = _load_ref_map(con, tbl, kcol, ncol)
    if FLOWSHEET_SOURCE_TABLE:
        tbl, kcol, ncol = FLOWSHEET_SOURCE_TABLE
        loc_maps["Flowsheet"] = _load_ref_map(con, tbl, kcol, ncol)

    def resolve(iclass: str, source_key) -> str:
        prefix = CLASS_PREFIX.get(iclass, "x")
        if source_key is None:
            return f"{prefix}:na"
        name = loc_maps.get(iclass, {}).get(int(source_key))
        return f"{prefix}:{name if name is not None else source_key}"

    # One ordered stream per staff member, with everything resolved in SQL
    # except location (done in Python because it is class-conditional).
    q = """
    select
        e.MasterIndexId          as staff,
        epoch(e.EventDateTime)   as ts,
        e.SourceKey              as source_key,
        e.LinkKey                as link_key,
        e.PatientDurableKey      as patient,
        it.InteractionType       as itype,
        it.InteractionTypeClass  as iclass,
        coalesce(s.Role, 'unknown')       as role
    from Data.StaffLocationEvent e
    join Ref.InteractionType it
      on e.InteractionTypeKey = it.InteractionTypeKey
    left join Ref.Staff s
      on s.MasterIndexId = e.MasterIndexId
    order by e.MasterIndexId, e.EventDateTime
    """
    rows = con.execute(q).fetchall()

    # (a) collect rostered intervals per staff from Roster Start/End by LinkKey
    starts: dict[tuple[str, int], float] = {}
    ends: dict[tuple[str, int], float] = {}
    for staff, ts, sk, link_key, patient, itype, iclass, role in rows:
        if iclass != "Roster" or link_key is None:
            continue
        key = (staff, int(link_key))
        if itype == "Roster Start":
            starts[key] = float(ts)
        elif itype == "Roster End":
            ends[key] = float(ts)

    intervals: dict[str, list[tuple[float, float, int]]] = defaultdict(list)
    for key, t0 in starts.items():
        t1 = ends.get(key)
        if t1 is None or t1 <= t0:
            continue  # unmatched or non-monotonic pair -> skip (report separately)
        staff, link_key = key
        intervals[staff].append((t0, t1, link_key))
    for staff in intervals:
        intervals[staff].sort()

    def which_shift(staff: str, ts: float) -> int | None:
        for t0, t1, link_key in intervals.get(
            staff, ()
        ):  # linear; fine for a prototype
            if t0 <= ts <= t1:
                return link_key
        return None

    # (b) assign each activity event to its containing shift
    shifts: dict[tuple[str, int], Shift] = {}
    for staff, ts, sk, link_key, patient, itype, iclass, role in rows:
        if iclass == "Roster":
            continue
        ts = float(ts)
        shift_id = which_shift(staff, ts)
        if shift_id is None:
            if not KEEP_UNROSTERED:
                continue
            shift_id = -1
        skey = (staff, shift_id)
        if skey not in shifts:
            shifts[skey] = Shift(staff=staff, link_key=shift_id)
        tb = min(N_TIME_BUCKETS - 1, int(((ts % 86400) / 86400) * N_TIME_BUCKETS))
        shifts[skey].steps.append(
            Step(
                ts=ts,
                location=resolve(iclass, sk),
                iclass=iclass,
                itype=itype,
                role=str(role),
                patient=(str(patient) if patient is not None else None),
                time_bucket=tb,
            )
        )

    out = [shift for shift in shifts.values() if len(shift.steps) >= MIN_SHIFT_EVENTS]
    for shift in out:
        shift.steps.sort(key=lambda s: s.ts)
    return out


# ------------------------------------------------------------------
# 2. State / action variants (what BC and Markov condition on)
# ------------------------------------------------------------------
# Action target = next location by default (the movement question). Swap to
# "iclass" or "itype" to ask "what do they do next" instead.

STATE_VARIANTS = {
    "S1_loc": lambda s, prev: (s.location,),
    "S2_loc_time": lambda s, prev: (s.location, s.time_bucket),
    "S3_loc_time_role": lambda s, prev: (s.location, s.time_bucket, s.role),
    "S4_loc_time_role_class": lambda s, prev: (
        s.location,
        s.time_bucket,
        s.role,
        s.iclass,
    ),
    "S5_bigram": lambda s, prev: (
        s.location,
        s.time_bucket,
        s.role,
        (prev.location if prev else "<s>"),
    ),
}
ACTION_KEYS = {
    "next_loc": lambda s: s.location,
    "next_class": lambda s: s.iclass,
    "next_itype": lambda s: s.itype,
}


def build_pairs(shifts, state_fn, action_key):
    """Return list of (state_tuple, action_str) across all shifts."""
    pairs = []
    for sh in shifts:
        prev = None
        for cur, nxt in zip(sh.steps, sh.steps[1:]):
            pairs.append((state_fn(cur, prev), action_key(nxt)))
            prev = cur
    return pairs


def split_pairs(pairs, frac=0.8, seed=0):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(pairs))
    cut = int(len(pairs) * frac)
    tr = [pairs[i] for i in idx[:cut]]
    te = [pairs[i] for i in idx[cut:]]
    return tr, te


# ------------------------------------------------------------------
# 3. Learnability battery
# ------------------------------------------------------------------


def conditional_entropy(pairs) -> tuple[float, float]:
    """H(action) and H(action | state), in bits. Gap = mutual information."""
    a_counts = Counter(a for _, a in pairs)
    n = sum(a_counts.values())
    H_a = -sum((c / n) * math.log2(c / n) for c in a_counts.values())

    by_state: defaultdict[tuple, Counter[str]] = defaultdict(Counter)
    for s, a in pairs:
        by_state[s][a] += 1
    H_a_given_s = 0.0
    for s, ctr in by_state.items():
        m = sum(ctr.values())
        h = -sum((c / m) * math.log2(c / m) for c in ctr.values())
        H_a_given_s += (m / n) * h
    return H_a, H_a_given_s


def variant_stats(shifts, action_key) -> dict:
    """Process-mining-style: how many distinct action paths, how concentrated."""
    paths = Counter(tuple(action_key(s) for s in sh.steps) for sh in shifts)
    total = sum(paths.values())
    top = paths.most_common(1)[0][1] if paths else 0
    return {
        "n_shifts": len(shifts),
        "distinct_paths": len(paths),
        "top_path_share": round(top / total, 3) if total else 0.0,
        "singletons": sum(1 for c in paths.values() if c == 1),
    }


class MarkovModel:
    """Order-k categorical model P(action | last-k actions), Laplace-smoothed.

    This is a first-class interpretable baseline (a transition table). Its
    held-out top-k and perplexity are the primary learnability numbers.
    """

    def __init__(self, order=1, alpha=0.5):
        self.order = order
        self.alpha = alpha
        self.table: dict[tuple, Counter] = defaultdict(Counter)
        self.vocab: set = set()

    def fit(self, seq_pairs):
        # seq_pairs: list of (context_tuple, action). We only use the last-k
        # actions from context, which we encode as the state tuple here.
        for ctx, a in seq_pairs:
            self.table[ctx][a] += 1
            self.vocab.add(a)

    def _dist(self, ctx) -> dict:
        ctr = self.table.get(ctx, Counter())
        V = max(1, len(self.vocab))
        denom = sum(ctr.values()) + self.alpha * V
        return {a: (ctr.get(a, 0) + self.alpha) / denom for a in self.vocab}

    def evaluate(self, seq_pairs, topk=TOPK):
        top1 = topk_hit = 0
        ll = 0.0
        for ctx, a in seq_pairs:
            dist = self._dist(ctx)
            ranked = sorted(dist, key=dist.get, reverse=True)
            if ranked and ranked[0] == a:
                top1 += 1
            if a in ranked[:topk]:
                topk_hit += 1
            p = dist.get(a, self.alpha / max(1, len(self.vocab)))
            ll += math.log2(max(p, 1e-12))
        n = max(1, len(seq_pairs))
        return {
            "top1": round(top1 / n, 3),
            f"top{topk}": round(topk_hit / n, 3),
            "perplexity": round(2 ** (-ll / n), 2),
        }


def run_battery(shifts, action_name="next_loc", order=1):
    action_key = ACTION_KEYS[action_name]
    print(f"\n=== Learnability battery (action = {action_name}) ===")
    print("variants:", variant_stats(shifts, action_key))

    # Markov context = last `order` actions.
    seq = []
    for sh in shifts:
        acts = [action_key(s) for s in sh.steps]
        for i in range(order, len(acts)):
            ctx = tuple(acts[i - order : i])
            seq.append((ctx, acts[i]))
    tr, te = split_pairs(seq)
    m = MarkovModel(order=order)
    m.fit(tr)
    print(f"markov(order={order}) held-out:", m.evaluate(te))

    # Information-theoretic ceiling using the richest state variant.
    pairs = build_pairs(shifts, STATE_VARIANTS["S5_bigram"], action_key)
    H_a, H_ags = conditional_entropy(pairs)
    print(
        f"entropy: H(a)={H_a:.2f} bits  H(a|state)={H_ags:.2f} bits  "
        f"info gain={H_a - H_ags:.2f} bits"
    )
    print(
        "reading: large info gain + low perplexity => structure IRL can use; "
        "H(a|state) near H(a) => little conditional signal (noisy)."
    )


# ------------------------------------------------------------------
# 3b. BC rule-out: grouped split + baselines + decision rule
# ------------------------------------------------------------------
# A rule-out is only trustworthy if (a) train and test never share a shift
# (otherwise within-shift autocorrelation leaks and inflates top-1), and
# (b) BC is measured as LIFT over baselines on the SAME held-out set. On
# categorical state the empirical conditional P(a|state) is BC's ceiling; a
# neural net can only help by generalising to state combos unseen in train.


def grouped_split(shifts, frac=0.8, seed=0):
    """Split by SHIFT, not by pair. All pairs from a shift stay on one side."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(shifts))
    cut = int(len(shifts) * frac)
    return [shifts[i] for i in idx[:cut]], [shifts[i] for i in idx[cut:]]


def _topk_eval(predict, test_pairs, topk=TOPK):
    """predict: state_tuple -> ranked list of actions (best first)."""
    top1 = topk_hit = 0
    for s, a in test_pairs:
        ranked = predict(s)
        if ranked and ranked[0] == a:
            top1 += 1
        if a in ranked[:topk]:
            topk_hit += 1
    n = max(1, len(test_pairs))
    return round(top1 / n, 3), round(topk_hit / n, 3)


def run_ruleout(shifts, action_name="next_loc", use_bc=True):
    action_key = ACTION_KEYS[action_name]
    tr_shifts, te_shifts = grouped_split(shifts)
    print(f"\n=== BC rule-out (action = {action_name}) ===")
    print(f"grouped split: {len(tr_shifts)} train shifts, {len(te_shifts)} test shifts")

    # --- baseline 1: majority class (ignores state entirely) ---
    tr_actions = [action_key(s) for sh in tr_shifts for s in sh.steps]
    marginal_rank = [a for a, _ in Counter(tr_actions).most_common()]
    test_min = build_pairs(te_shifts, STATE_VARIANTS["S1_loc"], action_key)
    maj_top1, maj_topk = _topk_eval(lambda s: marginal_rank, test_min)
    print(f"{'majority-class':22s} top1={maj_top1:.3f} top{TOPK}={maj_topk:.3f}")

    # --- baseline 2: order-1 Markov P(next | current location) ---
    markov_table = defaultdict(Counter)
    for sh in tr_shifts:
        acts = [action_key(s) for s in sh.steps]
        for prev, nxt in zip(acts, acts[1:]):
            markov_table[(prev,)][nxt] += 1

    def markov_pred(_state, _cache={}):
        # state for S1 is (location,), which equals the current action symbol
        ctx = (_state[0],)
        ctr = markov_table.get(ctx)
        return [a for a, _ in ctr.most_common()] if ctr else marginal_rank

    mk_top1, mk_topk = _topk_eval(markov_pred, test_min)
    print(f"{'markov(prev-loc)':22s} top1={mk_top1:.3f} top{TOPK}={mk_topk:.3f}")

    # --- count-based BC (the ceiling for each categorical state variant) ---
    print("\ncount-based BC  P(a|state)  (unseen state -> backoff to majority):")
    count_scores = {}
    unseen_frac = {}
    for name, state_fn in STATE_VARIANTS.items():
        table = defaultdict(Counter)
        for s, a in build_pairs(tr_shifts, state_fn, action_key):
            table[s][a] += 1
        test_pairs = build_pairs(te_shifts, state_fn, action_key)
        n_unseen = sum(1 for s, _ in test_pairs if s not in table)
        unseen_frac[name] = round(n_unseen / max(1, len(test_pairs)), 3)

        def pred(s, _t=table):
            ctr = _t.get(s)
            return [a for a, _ in ctr.most_common()] if ctr else marginal_rank

        t1, tk = _topk_eval(pred, test_pairs)
        count_scores[name] = t1
        print(
            f"  {name:26s} top1={t1:.3f} top{TOPK}={tk:.3f}  "
            f"(unseen states: {unseen_frac[name]:.0%})"
        )

    # --- optional neural BC on richest state (only helps via generalisation) ---
    nn_top1 = None
    if use_bc:
        try:
            nn_top1 = _run_bc_grouped(tr_shifts, te_shifts, action_key)
            print(f"\nneural BC (S5, embeddings) top1={nn_top1:.3f}")
        except ImportError:
            print("\n[bc] flax/optax not installed; skipping neural BC.")

    # --- decision ---
    best_count = max(count_scores.values())
    best_state = max(count_scores, key=count_scores.get)
    lift_over_markov = best_count - mk_top1
    lift_over_majority = best_count - maj_top1
    print("\n--- verdict ---")
    print(f"best count-BC state: {best_state}  top1={best_count:.3f}")
    print(
        f"lift over majority: {lift_over_majority:+.3f}   "
        f"lift over markov: {lift_over_markov:+.3f}"
    )
    if lift_over_majority < 0.03:
        print(
            "RULE OUT: BC barely beats predicting the single most common action. "
            "State carries almost no signal for this target -> IRL over these "
            "features will not work either. Try a different action target, or "
            "fall to process mining / empirical-distribution ABM."
        )
    elif lift_over_markov < 0.02:
        print(
            "PARTIAL: BC beats majority but not order-1 Markov. There IS "
            "sequential structure, but the extra features (time/role/bigram) "
            "add nothing over 'where they just were'. IRL over those features "
            "is not justified; a Markov/empirical model is the honest ceiling."
        )
    else:
        if nn_top1 is not None and nn_top1 - best_count > 0.02:
            print(
                "KEEP: neural BC beats the count table -> many test state combos "
                "are unseen in train (state is sparse); embeddings generalise. "
                "BC works; carry this state into IRL."
            )
        else:
            print(
                "KEEP: BC beats both baselines and the count table is the ceiling "
                "(state is dense enough). Representation carries signal -> "
                "proceed to IRL. A count/Markov policy is a strong Mesa baseline."
            )


def _run_bc_grouped(tr_shifts, te_shifts, action_key):
    """Neural BC with a grouped split (no shift shared across train/test)."""
    import jax
    import jax.numpy as jnp
    import optax
    from flax import linen as nn

    tr = build_pairs(tr_shifts, STATE_VARIANTS["S5_bigram"], action_key)
    te = build_pairs(te_shifts, STATE_VARIANTS["S5_bigram"], action_key)
    n_fields = len(tr[0][0])
    # Build vocab from TRAIN only; map unseen test values to a reserved index.
    vocabs = []
    for f in range(n_fields):
        vals = sorted({p[0][f] for p in tr}, key=str)
        vocabs.append({v: i for i, v in enumerate(vals)})  # unseen -> len(vocab)
    a_vals = sorted({a for _, a in tr}, key=str)
    a_vocab = {v: i for i, v in enumerate(a_vals)}

    def enc_x(pairs):
        return np.array(
            [
                [vocabs[f].get(p[0][f], len(vocabs[f])) for f in range(n_fields)]
                for p in pairs
            ]
        )

    Xtr, Xte = enc_x(tr), enc_x(te)
    ytr = np.array([a_vocab[a] for _, a in tr])
    # test actions unseen in train are unpredictable by construction -> keep,
    # they simply count as misses (honest for a rule-out).
    yte = np.array([a_vocab.get(a, -1) for _, a in te])

    class BC(nn.Module):
        sizes: tuple
        n_out: int

        @nn.compact
        def __call__(self, x):
            embs = [
                nn.Embed(self.sizes[f] + 1, 8)(x[:, f]) for f in range(len(self.sizes))
            ]
            h = jnp.concatenate(embs, axis=-1)
            h = nn.relu(nn.Dense(64)(h))
            return nn.Dense(self.n_out)(h)

    model = BC(tuple(len(v) for v in vocabs), len(a_vocab))
    params = model.init(jax.random.PRNGKey(0), jnp.array(Xtr[:2]))
    opt = optax.adam(1e-2)
    opt_state = opt.init(params)

    def loss_fn(p, xb, yb):
        logits = model.apply(p, xb)
        return optax.softmax_cross_entropy_with_integer_labels(logits, yb).mean()

    @jax.jit
    def step(p, os, xb, yb):
        loss_value, grads = jax.value_and_grad(loss_fn)(p, xb, yb)
        updates, os = opt.update(grads, os)
        return optax.apply_updates(p, updates), os, loss_value

    Xtrj, ytrj = jnp.array(Xtr), jnp.array(ytr)
    for _ in range(300):
        params, opt_state, _ = step(params, opt_state, Xtrj, ytrj)
    pred = np.array(model.apply(params, jnp.array(Xte)).argmax(-1))
    return float((pred == yte).mean())


# ------------------------------------------------------------------
# 4. Occam state-variant sweep (Markov as the fast learner)
# ------------------------------------------------------------------


def run_sweep(shifts, action_name="next_loc", use_bc=False):
    action_key = ACTION_KEYS[action_name]
    print(f"\n=== State-variant sweep (action = {action_name}) ===")
    print(f"{'variant':28s} {'top1':>6s} {'top3':>6s}")
    prev_top1 = None
    for name, state_fn in STATE_VARIANTS.items():
        pairs = build_pairs(shifts, state_fn, action_key)
        tr, te = split_pairs(pairs)
        # Reuse MarkovModel as a generic P(a|state) lookup over the full state.
        m = MarkovModel(order=0)
        m.fit(tr)
        r = m.evaluate(te)
        gain = "" if prev_top1 is None else f"  ({r['top1'] - prev_top1:+.3f})"
        print(f"{name:28s} {r['top1']:6.3f} {r[f'top{TOPK}']:6.3f}{gain}")
        prev_top1 = r["top1"]
    if use_bc:
        try:
            _run_bc(shifts, action_key)
        except ImportError:
            print("\n[bc] flax/optax not installed; skipping neural BC.")


def _run_bc(shifts, action_key):
    """Optional Flax MLP BC over the richest state. Guarded import."""
    import jax
    import jax.numpy as jnp
    import optax
    from flax import linen as nn

    pairs = build_pairs(shifts, STATE_VARIANTS["S5_bigram"], action_key)
    # Encode each categorical field with its own vocab.
    n_fields = len(pairs[0][0])
    vocabs = [
        {v: i for i, v in enumerate({p[0][f] for p in pairs})} for f in range(n_fields)
    ]
    a_vocab = {v: i for i, v in enumerate({a for _, a in pairs})}
    X = np.array([[vocabs[f][p[0][f]] for f in range(n_fields)] for p in pairs])
    y = np.array([a_vocab[a] for _, a in pairs])
    tr, te = split_pairs(list(range(len(y))))
    tr, te = np.array(tr), np.array(te)

    class BC(nn.Module):
        sizes: tuple
        n_out: int

        @nn.compact
        def __call__(self, x):
            embs = [nn.Embed(self.sizes[f], 8)(x[:, f]) for f in range(len(self.sizes))]
            h = jnp.concatenate(embs, axis=-1)
            h = nn.relu(nn.Dense(64)(h))
            return nn.Dense(self.n_out)(h)

    model = BC(tuple(len(v) for v in vocabs), len(a_vocab))
    key = jax.random.PRNGKey(0)
    params = model.init(key, jnp.array(X[:2]))
    opt = optax.adam(1e-2)
    opt_state = opt.init(params)

    def loss_fn(p, xb, yb):
        logits = model.apply(p, xb)
        return optax.softmax_cross_entropy_with_integer_labels(logits, yb).mean()

    @jax.jit
    def step(p, os, xb, yb):
        loss_value, grads = jax.value_and_grad(loss_fn)(p, xb, yb)
        updates, os = opt.update(grads, os)
        return optax.apply_updates(p, updates), os, loss_value

    Xtr, ytr = jnp.array(X[tr]), jnp.array(y[tr])
    for _ in range(300):
        params, opt_state, _ = step(params, opt_state, Xtr, ytr)
    logits = model.apply(params, jnp.array(X[te]))
    pred = np.array(logits.argmax(-1))
    top1 = float((pred == y[te]).mean())
    print(f"\n[bc] S5_bigram held-out top1 = {top1:.3f}")


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to the DuckDB file")
    ap.add_argument("cmd", choices=["battery", "sweep", "ruleout"])
    ap.add_argument("--action", default="next_loc", choices=list(ACTION_KEYS))
    ap.add_argument("--order", type=int, default=1)
    ap.add_argument("--bc", action="store_true")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    shifts = load_shifts(con)
    print(
        f"loaded {len(shifts)} shifts, "
        f"{sum(len(s.steps) for s in shifts)} touchpoints, "
        f"{len({s.staff for s in shifts})} staff"
    )

    if args.cmd == "battery":
        run_battery(shifts, args.action, order=args.order)
    elif args.cmd == "ruleout":
        run_ruleout(shifts, args.action, use_bc=args.bc)
    else:
        run_sweep(shifts, args.action, use_bc=args.bc)


if __name__ == "__main__":
    main()
