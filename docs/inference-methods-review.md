# Backward Inference Methods for Agent-Based Models

A technical guide to parameter and policy inference methods for simulation models.

---

## 1. Overview

Agent-based models typically run **forward** — producing emergent behavior from parameters in simulation. **Backward inference** inverts this process: given observed behavior (e.g., patient trajectories, infection patterns), what parameters or policies generated it?

This is challenging because:

- ABMs are often **likelihood-free** (no closed-form probability of observations given parameters)
- Models are **stochastic** (same parameters → different outcomes)
- Parameter spaces are **high-dimensional**
- Forward simulations are **computationally expensive**

### Two Main Inference Goals

| Goal                | Question                                                 | Possible Methods               |
| ------------------- | -------------------------------------------------------- | ------------------------------ |
| Parameter Inference | "What epidemiological parameters explain this outbreak?" | ABC, SMC, MCMC, MOEA           |
| Policy Inference    | "What decision rules do agents follow?"                  | Inverse RL, Imitation Learning |

---

## 2. Parameter Inference Methods

### 2.1 ABC (Approximate Bayesian Computation)

A likelihood-free inference method that bypasses the need for an explicit likelihood function by comparing simulated data to observed data through summary statistics [1, 2].

**How it works:**

1. Sample parameters from prior distribution
2. Run forward simulation with sampled parameters
3. Compute summary statistics of simulated output
4. Accept parameters if statistics are "close enough" to observed data
5. Accepted samples approximate the posterior distribution

**When to use:**
When you cannot write down P(data|parameters) but can simulate from the model.

**Limitations:**

- Choice of summary statistics is critical (information loss)
- Computationally expensive (many rejected samples)
- "Close enough" threshold affects accuracy

**Available in:** OpenMOLE (`IslandABC()`), pyABC, ELFI

---

### 2.2 ABC-SMC (Sequential Monte Carlo ABC)

An extension of ABC that iteratively refines the posterior through a sequence of distributions with decreasing tolerance thresholds [3, 4].

**How it works:**

1. Start with loose acceptance threshold, get initial posterior approximation
2. Use accepted particles to propose new parameters (with perturbation kernel)
3. Tighten threshold, filter particles
4. Repeat until convergence

**Advantages over vanilla ABC:**

- More efficient sampling (guided by previous iterations)
- Better posterior approximation
- Automatic threshold scheduling

**Available in:** pyABC, ELFI, OpenMOLE

---

### 2.3 MCMC (Markov Chain Monte Carlo)

Classical Bayesian inference via random walks in parameter space, constructing a Markov chain whose stationary distribution is the target posterior [5].

**Common variants:**

- **Metropolis-Hastings:** Accept/reject proposals based on likelihood ratio
- **Hamiltonian Monte Carlo (HMC):** Uses gradient information for efficient exploration
- **NUTS:** No-U-Turn Sampler, adaptive HMC [6]

**Integration with ABMs:**
MCMC sampler calls the simulation as a black-box likelihood evaluator. For likelihood-free models, combine with pseudo-marginal methods or synthetic likelihood.

**Example workflow:**

```python
for each MCMC iteration:
    propose new parameters θ'
    run simulation with θ'
    compute (pseudo-)likelihood
    accept/reject based on MH ratio
```

**Limitations:**

- Requires many forward simulations
- Can struggle with multimodal posteriors
- Mixing can be slow in high dimensions

**Available in:** PyMC, Stan, emcee, NumPyro

---

### 2.4 MOEA (Multi-Objective Evolutionary Algorithm)

Optimization framework that evolves a population of candidate solutions to find Pareto-optimal parameter sets across multiple objectives [7].

**How it works:**

1. Initialize population of parameter sets
2. Evaluate fitness on multiple objectives (e.g., match infection rate AND match movement patterns)
3. Select, crossover, mutate to create next generation
4. Maintain Pareto front of non-dominated solutions
5. Repeat until convergence

**Common algorithms:**

- **NSGA-II:** Non-dominated Sorting Genetic Algorithm [7]
- **NSGA-III:** Better for many objectives (>3) [8]
- **MOEA/D:** Decomposition-based approach

**When to use:**

- Multiple calibration targets that may conflict
- Want to understand trade-offs between objectives
- Exploring diverse parameter regimes

**Example objectives for hospital simulation:**

- Minimize distance to observed trajectory distributions
- Minimize distance to observed infection counts
- Maximize model parsimony

**Available in:** OpenMOLE (genetic algorithms plugin), DEAP (Python), pymoo, jMetal

---

## 3. Simulation-Based Inference (Modern Approaches)

### 3.1 sbi (Simulation-Based Inference Library)

**Repository:** <https://github.com/sbi-dev/sbi>

PyTorch-based library implementing neural network-powered likelihood-free inference. Trains neural networks to approximate posterior, likelihood, or likelihood ratio [9, 10].

**Key methods:**

| Method | Approximates     | Approach                 |
| ------ | ---------------- | ------------------------ |
| SNPE   | Posterior        | Neural density estimator |
| SNLE   | Likelihood       | Train network, then MCMC |
| SNRE   | Likelihood Ratio | Binary classifier        |

**Workflow:**

1. Define prior over parameters
2. Generate (parameter, simulation) pairs
3. Train neural network on pairs
4. Network provides amortized inference (fast posterior for new observations)

**Advantages:**

- **Amortized:** Once trained, instant inference for new data
- **Flexible:** Handles complex, high-dimensional posteriors
- **Efficient:** Fewer simulations than ABC for same accuracy

**Integration with ABMs:**

```python
from sbi import utils, inference

prior = utils.BoxUniform(low=torch.tensor([0.0, 0.0]),
                          high=torch.tensor([1.0, 1.0]))

# Your ABM as a callable
def simulator(params):
    return run_gama_simulation(params)  # Returns summary statistics

inference = inference.SNPE(prior)
density_estimator = inference.append_simulations(theta, x).train()
posterior = inference.build_posterior(density_estimator)

# Sample from posterior given observation
samples = posterior.sample((10000,), x=observed_data)
```

**Best for:** When you'll do inference repeatedly on similar problems (training cost amortized).

---

### 3.2 ELFI (Engine for Likelihood-Free Inference)

**Repository:** <https://github.com/elfi-dev/elfi>

Python framework providing a unified interface to multiple likelihood-free inference algorithms with a focus on modularity and visualization [11].

**Algorithms available:**

- Rejection ABC
- SMC-ABC
- BOLFI (Bayesian Optimization for Likelihood-Free Inference)
- ROMC (Robust Optimization Monte Carlo)

**Key feature — BOLFI:**
Uses Gaussian Process surrogate to model the discrepancy function, enabling efficient exploration with far fewer simulations than standard ABC.

**Workflow:**

```python
import elfi

# Define generative model as a graph
elfi.Prior('uniform', 0, 1, name='param1')
elfi.Simulator(my_abm_simulator, model['param1'], name='sim')
elfi.Summary(compute_statistics, model['sim'], name='stats')
elfi.Distance('euclidean', model['stats'], name='dist')

# Run inference
rej = elfi.Rejection(model['dist'], batch_size=100)
result = rej.sample(1000, threshold=0.1)
```

**Best for:** Prototyping and comparing different ABC variants; GP-accelerated inference with BOLFI.

---

### 3.3 pyABC

**Repository:** <https://github.com/ICB-DCM/pyABC>

Scalable, distributed ABC-SMC implementation with excellent parallelization support [12].

**Key features:**

- **Distributed computing:** Redis-based, scales to clusters
- **Adaptive schemes:** Automatic epsilon scheduling, adaptive population sizes
- **Model selection:** Compare competing model structures, not just parameters
- **Visualization:** Built-in plotting for diagnostics

**Workflow:**

```python
import pyabc

prior = pyabc.Distribution(
    param1=pyabc.RV("uniform", 0, 1),
    param2=pyabc.RV("uniform", 0, 10)
)

def distance(sim_data, obs_data):
    return np.abs(sim_data["stat"] - obs_data["stat"])

abc = pyabc.ABCSMC(my_abm_model, prior, distance)
abc.new("sqlite:///results.db", observed_data)
history = abc.run(max_nr_populations=10)
```

**Model selection example:**
Compare SEIR vs SIR vs SEIRS models for infection dynamics.

**Best for:** Production ABC-SMC with cluster parallelization; Bayesian model comparison.

---

## 4. Policy Inference (Inverse RL & Imitation Learning)

### 4.1 Inverse Reinforcement Learning (IRL)

Given observed agent trajectories, infer the reward function that explains the behavior. Assumes agents are (approximately) optimal with respect to some unknown reward [13].

**Core idea:**
Instead of asking "what parameters?" ask "what objectives are agents optimizing?"

**Classic algorithms:**

- **Maximum Entropy IRL:** Find reward that makes observed trajectories most probable [14]
- **Bayesian IRL:** Posterior over reward functions [15]
- **GAIL (Generative Adversarial Imitation Learning):** Discriminator distinguishes expert vs. policy trajectories [16]

**Application to hospital simulation:**

- Learn staff movement rewards (minimize walking? prioritize certain rooms?)
- Learn patient waiting behavior policies
- Infer implicit infection avoidance behaviors

**Using ABM as environment:**

```python
# Wrap GAMA/Repast as Gym environment
class HospitalEnv(gym.Env):
    def step(self, action):
        return gama_simulation.step(action)

# Run IRL
from imitation.algorithms import GAIL
trainer = GAIL(env=HospitalEnv(), demonstrations=observed_trajectories)
reward_net = trainer.train()
```

**Available in:** imitation (Python), CrowdNav, stable-baselines3 + custom

---

### 4.2 Behavioral Cloning

Supervised learning approach — directly learn state→action mapping from demonstrations without inferring rewards.

**When to prefer over IRL:**

- Simpler to implement
- Works when reward structure isn't needed
- Sufficient expert data available

**Limitations:**
Compounding errors (doesn't learn to recover from mistakes).

---

## 5. Integration Pattern

```text
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   GAMA      │─────▶│  Export     │─────▶│  sbi/pyABC  │
│ (simulation)│      │ trajectories│      │ (inference) │
└─────────────┘      └─────────────┘      └─────────────┘
```

- Use GAMA for spatial modeling and forward simulation
- Export trajectories to Python for modern backward inference methods
- Good balance of spatial fidelity and inference flexibility

---

## References

### Foundational Papers

[1] Beaumont, M.A., Zhang, W., & Balding, D.J. (2002). Approximate Bayesian computation in population genetics. _Genetics_, 162(4), 2025-2035.

[2] Sunnåker, M., et al. (2013). Approximate Bayesian Computation. _PLOS Computational Biology_, 9(1), e1002803.

[3] Toni, T., Welch, D., Strelkowa, N., Ipsen, A., & Stumpf, M.P.H. (2009). Approximate Bayesian computation scheme for parameter inference and model selection in dynamical systems. _Journal of the Royal Society Interface_, 6(31), 187-202.

[4] Del Moral, P., Doucet, A., & Jasra, A. (2012). An adaptive sequential Monte Carlo method for approximate Bayesian computation. _Statistics and Computing_, 22(5), 1009-1020.

[5] Metropolis, N., Rosenbluth, A.W., Rosenbluth, M.N., Teller, A.H., & Teller, E. (1953). Equation of state calculations by fast computing machines. _The Journal of Chemical Physics_, 21(6), 1087-1092.

[6] Hoffman, M.D. & Gelman, A. (2014). The No-U-Turn Sampler: Adaptively setting path lengths in Hamiltonian Monte Carlo. _Journal of Machine Learning Research_, 15(1), 1593-1623.

[7] Deb, K., Pratap, A., Agarwal, S., & Meyarivan, T. (2002). A fast and elitist multiobjective genetic algorithm: NSGA-II. _IEEE Transactions on Evolutionary Computation_, 6(2), 182-197.

[8] Deb, K. & Jain, H. (2014). An evolutionary many-objective optimization algorithm using reference-point-based nondominated sorting approach, part I. _IEEE Transactions on Evolutionary Computation_, 18(4), 577-601.

[9] Cranmer, K., Brehmer, J., & Louppe, G. (2020). The frontier of simulation-based inference. _Proceedings of the National Academy of Sciences_, 117(48), 30055-30062.

[10] Tejero-Cantero, A., et al. (2020). sbi: A toolkit for simulation-based inference. _Journal of Open Source Software_, 5(52), 2505.

[11] Lintusaari, J., et al. (2018). ELFI: Engine for likelihood-free inference. _Journal of Machine Learning Research_, 19(1), 742-747.

[12] Klinger, E., Rickert, D., & Hasenauer, J. (2018). pyABC: distributed, likelihood-free inference. _Bioinformatics_, 34(20), 3591-3593.

[13] Ng, A.Y. & Russell, S.J. (2000). Algorithms for inverse reinforcement learning. _Proceedings of the 17th International Conference on Machine Learning (ICML)_, 663-670.

[14] Ziebart, B.D., Maas, A.L., Bagnell, J.A., & Dey, A.K. (2008). Maximum entropy inverse reinforcement learning. _Proceedings of the 23rd AAAI Conference on Artificial Intelligence_, 1433-1438.

[15] Ramachandran, D. & Amir, E. (2007). Bayesian inverse reinforcement learning. _Proceedings of the 20th International Joint Conference on Artificial Intelligence (IJCAI)_, 2586-2591.

[16] Ho, J. & Ermon, S. (2016). Generative adversarial imitation learning. _Advances in Neural Information Processing Systems_, 29, 4565-4573.

### Software Documentation

- sbi: <https://sbi-dev.github.io/sbi/>
- ELFI: <https://elfi.readthedocs.io/>
- pyABC: <https://pyabc.readthedocs.io/>
- pymoo: <https://pymoo.org/>
- imitation: <https://imitation.readthedocs.io/>

---

_Last updated: January 2025_
_Project: AMR-HUB Hospital Movement & Infection Dynamics Simulation_
