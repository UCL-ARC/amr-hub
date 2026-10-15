"""
markov_analyzer.py.

Phase 2: Runs statistical tests on clean trajectories to determine IRL
feasibility.
"""

from __future__ import annotations

import argparse
import itertools
import math
import pickle
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path

import numpy as np

# Import the data structures from our Wrangler script so we know the pickle format.
from data_wrangler import Shift, Step

StateFn = Callable[[Step, "Step | None"], tuple]
ActionFn = Callable[[Step], str]

# ====================================================================
# State and Action Config
# ====================================================================

# ---------------------------------------------------------------------
FATIGUE_BUCKET_THRESHOLDS_MINUTES = (120, 240, 360)


def _fatigue_bucket(minutes_into_shift: float) -> int:
    return sum(1 for t in FATIGUE_BUCKET_THRESHOLDS_MINUTES if minutes_into_shift >= t)


STATE_VARIANTS: dict[str, StateFn] = {
    "S1_loc": lambda s, _p: (s.location,),
    "S2_loc_time": lambda s, _p: (s.location, s.time_bucket),
    "S3_loc_time_role": lambda s, _p: (s.location, s.time_bucket, s.role),
    "S4_loc_time_role_class": lambda s, _p: (
        s.location,
        s.time_bucket,
        s.role,
        s.interaction_class,
    ),
    "S5_prev_loc": lambda s, p: (
        s.location,
        s.time_bucket,
        s.role,
        (p.location if p else "<s>"),
    ),
    "S6_prev_loc_unit": lambda s, p: (
        s.location,
        s.time_bucket,
        s.role,
        (p.location if p else "<s>"),
        s.unit,
    ),
    "S7_prev_loc_occupancy_fatigue": lambda s, p: (
        s.location,
        s.time_bucket,
        s.role,
        (p.location if p else "<s>"),
        s.occupancy,
        _fatigue_bucket(s.minutes_into_shift),
    ),
}

ACTION_KEYS: dict[str, ActionFn] = {
    "next_loc": lambda s: s.location,
    "next_class": lambda s: s.interaction_class,
    "next_itype": lambda s: s.interaction_type,
}
# ---------------------------------------------------------------------

# ====================================================================

# ====================================================================
# Statistical Models
# ====================================================================


# ---------------------------------------------------------------------
class MarkovModel:
    """Order-k Laplace-smoothed Markov model over (context, action) pairs."""

    def __init__(self, order: int = 1, alpha: float = 0.5) -> None:
        """Store the model order and Laplace-smoothing strength."""
        self.order, self.alpha = order, alpha
        self.table: defaultdict[tuple, Counter] = defaultdict(Counter)
        self.vocab: set[str] = set()

    def fit(self, context_action_pairs: list[tuple[tuple, str]]) -> None:
        """Accumulate action counts per context from training pairs."""
        for context, action in context_action_pairs:
            self.table[context][action] += 1
            self.vocab.add(action)

    def evaluate(
        self, context_action_pairs: list[tuple[tuple, str]], shortlist_size: int = 3
    ) -> dict[str, float]:
        """Score accuracy / shortlist_accuracy / perplexity on test-set pairs."""
        correct = shortlist_hit = log_likelihood = 0.0
        n = max(1, len(context_action_pairs))
        v_size = max(1, len(self.vocab))

        for context, action in context_action_pairs:
            counts = self.table.get(context, Counter())
            denom = sum(counts.values()) + self.alpha * v_size
            dist = {a: (counts.get(a, 0) + self.alpha) / denom for a in self.vocab}

            ranked = sorted(dist, key=dist.__getitem__, reverse=True)
            if ranked and ranked[0] == action:
                correct += 1
            if action in ranked[:shortlist_size]:
                shortlist_hit += 1

            prob = dist.get(action, self.alpha / v_size)
            log_likelihood += math.log2(max(prob, 1e-12))

        return {
            "accuracy": round(correct / n, 3),
            "shortlist_accuracy": round(shortlist_hit / n, 3),
            "perplexity": round(2 ** (-log_likelihood / n), 2),
        }


# ---------------------------------------------------------------------

# ====================================================================


# ====================================================================
# Data Formatting
# ====================================================================


# ---------------------------------------------------------------------
def build_state_action_pairs(
    shifts: list[Shift], state_fn: StateFn, action_key: ActionFn
) -> list[tuple[tuple, str]]:
    """Turn each shift's step sequence into (state, next-action) pairs."""
    pairs = []
    for shift in shifts:
        prev = None
        for current, next_step in itertools.pairwise(shift.steps):
            pairs.append((state_fn(current, prev), action_key(next_step)))
            prev = current
    return pairs


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def split_shifts_by_group(
    shifts: list[Shift], frac: float = 0.8, seed: int = 0
) -> tuple[list[Shift], list[Shift]]:
    """Randomly split whole shifts into train/test groups (no cross-shift leakage)."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(shifts))
    cut = int(len(shifts) * frac)
    return [shifts[i] for i in idx[:cut]], [shifts[i] for i in idx[cut:]]


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def random_split_pairs(
    pairs: list[tuple], frac: float = 0.8, seed: int = 0
) -> tuple[list[tuple], list[tuple]]:
    """Randomly split (state, action) pairs into train/test sets."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(pairs))
    cut = int(len(pairs) * frac)
    return [pairs[i] for i in idx[:cut]], [pairs[i] for i in idx[cut:]]


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def _evaluate_predictions(
    predict: Callable[[tuple], list[str]],
    test_pairs: list[tuple],
    shortlist_size: int = 3,
) -> tuple[float, float]:
    correct = shortlist_hit = 0
    for state, action in test_pairs:
        ranked = predict(state)
        if ranked and ranked[0] == action:
            correct += 1
        if action in ranked[:shortlist_size]:
            shortlist_hit += 1
    n = max(1, len(test_pairs))
    return round(correct / n, 3), round(shortlist_hit / n, 3)


# ---------------------------------------------------------------------

# ====================================================================

# ====================================================================
# Analysis Routines
# ====================================================================


# ---------------------------------------------------------------------
def run_learnability_stats(
    shifts: list[Shift], action_key: ActionFn, order: int = 1
) -> None:
    """Print path-diversity stats, an order-k Markov baseline, and info gain."""
    print("\n=== Learnability Stats ===")  # noqa: T201

    # process-mining-style: how many distinct action paths, how concentrated
    paths = Counter(tuple(action_key(s) for s in shift.steps) for shift in shifts)
    total = sum(paths.values())
    top = paths.most_common(1)[0][1] if paths else 0
    print(  # noqa: T201
        f"paths: n_shifts={len(shifts)} distinct_paths={len(paths)} "
        f"top_path_share={round(top / total, 3) if total else 0.0} "
        f"singletons={sum(1 for c in paths.values() if c == 1)}"
    )

    # order-k Markov baseline: context = the last `order` actions taken
    context_action_pairs: list[tuple[tuple[str, ...], str]] = []
    for shift in shifts:
        actions = [action_key(s) for s in shift.steps]
        context_action_pairs.extend(
            (tuple(actions[i - order : i]), actions[i])
            for i in range(order, len(actions))
        )
    train_pairs, test_pairs = random_split_pairs(context_action_pairs)
    markov_model = MarkovModel(order=order)
    markov_model.fit(train_pairs)
    print(  # noqa: T201
        f"markov(order={order}) test-set: {markov_model.evaluate(test_pairs)}"
    )

    pairs = build_state_action_pairs(shifts, STATE_VARIANTS["S5_prev_loc"], action_key)

    action_counts = Counter(a for _, a in pairs)
    n = sum(action_counts.values())
    h_a = -sum((c / n) * math.log2(c / n) for c in action_counts.values())

    h_a_given_s = 0.0
    state_counts: defaultdict[tuple, Counter] = defaultdict(Counter)
    for s, a in pairs:
        state_counts[s][a] += 1
    for counts in state_counts.values():
        m = sum(counts.values())
        h_a_given_s += (m / n) * -sum(
            (c / m) * math.log2(c / m) for c in counts.values()
        )

    print(  # noqa: T201
        f"Entropy: H(Action) = {h_a:.2f} bits | "
        f"H(Action|State) = {h_a_given_s:.2f} bits"
    )
    print(f"Information Gain = {h_a - h_a_given_s:.2f} bits")  # noqa: T201
    print(  # noqa: T201
        "-> Reading: High Info Gain = Structure IRL can use. "
        "Low Info Gain = Pure Noise."
    )


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def run_irl_feasibility(shifts: list[Shift], action_key: ActionFn) -> None:
    """Compare count-based state variants against majority/Markov baselines."""
    train_shifts, test_shifts = split_shifts_by_group(shifts)
    print(  # noqa: T201
        f"\n=== IRL Feasibility Check ({len(train_shifts)} Train, "
        f"{len(test_shifts)} Test) ==="
    )

    # baseline 1: majority class (ignores state entirely)
    train_actions = [action_key(step) for s in train_shifts for step in s.steps]
    marginal_rank = [a for a, _ in Counter(train_actions).most_common()]
    test_pairs_minimal = build_state_action_pairs(
        test_shifts, STATE_VARIANTS["S1_loc"], action_key
    )
    majority_acc, majority_shortlist = _evaluate_predictions(
        lambda _s: marginal_rank, test_pairs_minimal
    )
    print(  # noqa: T201
        f"{'majority-class':22s} accuracy={majority_acc:.3f} "
        f"shortlist_accuracy={majority_shortlist:.3f}"
    )

    # baseline 2: order-1 Markov P(next | prev action)
    markov_table: defaultdict[tuple, Counter] = defaultdict(Counter)
    for shift in train_shifts:
        actions = [action_key(step) for step in shift.steps]
        for prev_a, next_a in itertools.pairwise(actions):
            markov_table[(prev_a,)][next_a] += 1

    def markov_predict(state: tuple) -> list[str]:
        counts = markov_table.get((state[0],))
        return [a for a, _ in counts.most_common()] if counts else marginal_rank

    markov_acc, markov_shortlist = _evaluate_predictions(
        markov_predict, test_pairs_minimal
    )
    print(  # noqa: T201
        f"{'markov(prev-loc)':22s} accuracy={markov_acc:.3f} "
        f"shortlist_accuracy={markov_shortlist:.3f}"
    )

    # count-based model: the ceiling for each categorical state variant
    print(  # noqa: T201
        "\ncount-based P(a|state)  (unseen state -> backoff to majority):"
    )
    count_scores = {}
    for name, state_fn in STATE_VARIANTS.items():
        table: defaultdict[tuple, Counter] = defaultdict(Counter)
        for s, a in build_state_action_pairs(train_shifts, state_fn, action_key):
            table[s][a] += 1
        t_pairs = build_state_action_pairs(test_shifts, state_fn, action_key)

        def predict(state: tuple, _table: dict[tuple, Counter] = table) -> list[str]:
            counts = _table.get(state)
            return [a for a, _ in counts.most_common()] if counts else marginal_rank

        acc, shortlist = _evaluate_predictions(predict, t_pairs)
        count_scores[name] = acc
        print(  # noqa: T201
            f"  {name:30s} accuracy={acc:.3f} shortlist_accuracy={shortlist:.3f}"
        )

    best_acc = max(count_scores.values())
    best_state = max(count_scores, key=count_scores.__getitem__)
    lift_over_majority = best_acc - majority_acc
    lift_over_markov = best_acc - markov_acc
    print("\n!Result!")  # noqa: T201
    print(  # noqa: T201
        f"best count-based state: {best_state}  accuracy={best_acc:.3f}"
    )
    print(  # noqa: T201
        f"lift over majority: {lift_over_majority:+.3f}   "
        f"lift over markov: {lift_over_markov:+.3f}"
    )
    if lift_over_majority < 0.03:
        print(  # noqa: T201
            "UGLY: barely beats majority. State carries almost no signal, "
            "IRL will not work either."
        )
    elif lift_over_markov < 0.02:
        print(  # noqa: T201
            "BAD: beats majority but not order-1 Markov. "
            "A Markov/empirical model is the ceiling."
        )
    else:
        print(  # noqa: T201
            "UGLY: beats both baselines. Representation carries signal, "
            "proceed to IRL. :-)"
        )


# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
def run_compare_state_variants(shifts: list[Shift], action_key: ActionFn) -> None:
    """Sweep all varients and print each one's test-set accuracy."""
    print("\n=== State-Variant Sweep ===")  # noqa: T201
    print(f"{'variant':30s} {'accuracy':>8s} {'shortlist_accuracy':>19s}")  # noqa: T201
    prev_acc = None
    for name, state_fn in STATE_VARIANTS.items():
        pairs = build_state_action_pairs(shifts, state_fn, action_key)
        train_pairs, test_pairs = random_split_pairs(pairs)
        model = MarkovModel(order=0)
        model.fit(train_pairs)
        result = model.evaluate(test_pairs)
        gain = "" if prev_acc is None else f"  ({result['accuracy'] - prev_acc:+.3f})"
        print(  # noqa: T201
            f"{name:30s} {result['accuracy']:8.3f} "
            f"{result['shortlist_accuracy']:19.3f}{gain}"
        )
        prev_acc = result["accuracy"]


# ---------------------------------------------------------------------

# ====================================================================


# ====================================================================
# main
# ====================================================================
def main() -> None:
    """CLI entry point: learnability-stats / irl-feasibility / compare-variants."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data", default="trajectories.pkl", help="Clean data from Wrangler"
    )
    parser.add_argument(
        "cmd",
        choices=["learnability-stats", "irl-feasibility", "compare-state-variants"],
    )
    parser.add_argument("--action", default="next_loc", choices=list(ACTION_KEYS))
    parser.add_argument(
        "--order", type=int, default=1, help="Markov order (learnability-stats only)"
    )
    args = parser.parse_args()

    try:
        with Path(args.data).open("rb") as f:
            # Trusted local file produced by our own data_wrangler.py extract
            # step, not untrusted/external input.
            shifts = pickle.load(f)  # noqa: S301
    except FileNotFoundError:
        print(f"Error: {args.data}Run data_wrangler.py extract first.")  # noqa: T201
        return

    if args.cmd == "learnability-stats":
        run_learnability_stats(shifts, ACTION_KEYS[args.action], order=args.order)
    elif args.cmd == "irl-feasibility":
        run_irl_feasibility(shifts, ACTION_KEYS[args.action])
    elif args.cmd == "compare-state-variants":
        run_compare_state_variants(shifts, ACTION_KEYS[args.action])


if __name__ == "__main__":
    main()
# ====================================================================
