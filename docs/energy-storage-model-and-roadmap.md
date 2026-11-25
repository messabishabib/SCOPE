---
title: "Energy Storage Optimization Model and Scientific Development Roadmap"
subtitle: "Current Formulation, Validation Framework, and Upgrade Path"
author: "SCOPE Decision Support Platform"
date: "2026-11-25"
date-format: "D MMMM YYYY"
---

**Model baseline:** multi-asset stochastic dispatch with optimized inflow spillage, 25 November 2026
**Audience:** developers, model reviewers, energy-system analysts, and future contributors  
**Purpose:** define the implemented mathematical model, explain how it is solved and validated, and establish a controlled path toward a multistage dynamic model.

## Abstract

The SCOPE energy module coordinates multiple storage assets connected to a common electricity balance. Each asset has independent energy and power limits, efficiencies, operating costs, initial energy, and terminal requirements. The module supports a deterministic mixed-integer linear program and a finite-scenario stochastic extensive-form model. It also implements receding-horizon execution: the model is solved repeatedly from observed storage states, only the first action is applied, and the portfolio is reoptimized when new information becomes available.

The present system is therefore a stochastic model-predictive controller, but it is not yet a full multistage stochastic dynamic program. In the stochastic formulation, physical actions are shared across scenarios only during a configurable commitment window; after that window, each scenario has independent recourse with knowledge of its complete trajectory. This approximation is computationally practical and produces implementable immediate decisions, but it does not represent gradual information revelation over a long horizon.

The recommended development path is incremental. The first priority is to complete the operational physics and uncertainty diagnostics of the existing model. The second is to introduce a genuine scenario tree with history-based nonanticipativity. The third is to investigate a hybrid architecture in which stochastic dual dynamic programming supplies long-term storage values and the existing mixed-integer controller handles detailed short-term operation.

## Model scope

The model represents a portfolio of storage assets behind one common system balance. An asset may represent pumped hydro, a battery, or another technology that can consume electrical energy when charging and supply electrical energy when discharging.

The current scope includes:

- multiple independently constrained storage assets;
- deterministic and finite-scenario stochastic dispatch;
- hourly or other constant-duration time intervals;
- grid imports and exports;
- renewable generation and curtailment;
- unserved energy with a penalty;
- asset-specific natural inflows in stochastic studies;
- asset- and scenario-specific optimized inflow spillage with an explicit penalty;
- rolling-horizon reoptimization from observed asset states;
- closed-loop comparison of deterministic and stochastic policies;
- independent post-solve validation of the principal physical equations.

All assets are currently connected to the same unconstrained electrical bus. The model does not yet determine nodal flows, congestion, losses, or locational prices. It is a portfolio dispatch model rather than a transmission-network model.

## Mathematical notation

### Sets and indices

| Symbol | Meaning |
|---|---|
| $a \in \mathcal A$ | Storage asset |
| $t \in \mathcal T=\{0,\ldots,H-1\}$ | Dispatch interval |
| $t \in \mathcal T^+=\{0,\ldots,H\}$ | Storage-state boundary |
| $\omega \in \Omega$ | Uncertainty scenario |

### Principal parameters

| Symbol | Meaning | Unit |
|---|---|---|
| $D_{\omega,t}$ | Demand | MWh |
| $R_{\omega,t}$ | Available renewable energy | MWh |
| $\pi^{in}_{\omega,t}$ | Grid import price | currency/MWh |
| $\pi^{out}_{\omega,t}$ | Grid export price | currency/MWh |
| $I_{\omega,a,t}$ | Natural inflow to storage asset | MWh |
| $\Delta t$ | Interval duration | h |
| $\underline E_a,\overline E_a$ | Minimum and maximum stored energy | MWh |
| $E^{0}_a$ | Initial stored energy | MWh |
| $E^{term}_a$ | Minimum terminal stored energy | MWh |
| $\overline P^{ch}_a,\overline P^{dis}_a$ | Charge and discharge power limits | MW |
| $\eta^{ch}_a,\eta^{dis}_a$ | Charge and discharge efficiencies | ratio |
| $c^{ch}_a,c^{dis}_a$ | Variable storage operating costs | currency/MWh |
| $c^U$ | Unserved-energy penalty | currency/MWh |
| $c^S$ | Inflow-spillage penalty | currency/MWh |
| $v^E$ | Terminal value of stored energy | currency/MWh |
| $p_\omega$ | Normalized scenario probability | ratio |

The implemented terminal value $v^E$ is common to all assets. Asset-specific terminal values are a planned refinement because different technologies and reservoirs can have materially different opportunity values.

### Decision variables

| Symbol | Meaning | Domain |
|---|---|---|
| $P^{ch}_{\omega,a,t}$ | Charging power | nonnegative continuous |
| $P^{dis}_{\omega,a,t}$ | Discharging power | nonnegative continuous |
| $E_{\omega,a,t}$ | Stored energy | nonnegative continuous |
| $z_{\omega,a,t}$ | Charging-mode indicator | binary |
| $G^{in}_{\omega,t}$ | Grid imports | nonnegative continuous |
| $G^{out}_{\omega,t}$ | Grid exports | nonnegative continuous |
| $U_{\omega,t}$ | Unserved energy | nonnegative continuous |
| $C_{\omega,t}$ | Renewable curtailment | nonnegative continuous |
| $S_{\omega,a,t}$ | Spilled natural inflow | nonnegative continuous |

The deterministic model is obtained by removing the scenario index.

## Deterministic portfolio formulation

### Objective function

The deterministic problem minimizes net system cost over the look-ahead horizon:

$$
\min \sum_{t\in\mathcal T}
\left[
\pi^{in}_tG^{in}_t
-\pi^{out}_tG^{out}_t
+c^U U_t
+\sum_{a\in\mathcal A}
\left(c^{ch}_aP^{ch}_{a,t}+c^{dis}_aP^{dis}_{a,t}\right)\Delta t
\right]
-v^E\sum_{a\in\mathcal A}E_{a,H}.
$$

The terminal-value term discourages artificial depletion at the end of a finite look-ahead window. Hard terminal minimums provide an additional feasibility requirement. These mechanisms have different meanings: a terminal minimum is a constraint, whereas terminal value represents the opportunity cost of energy remaining after the modeled horizon.

### System energy balance

All storage assets participate in one balance:

$$
R_t-C_t+G^{in}_t+U_t
+\Delta t\sum_{a\in\mathcal A}P^{dis}_{a,t}
=D_t+G^{out}_t
+\Delta t\sum_{a\in\mathcal A}P^{ch}_{a,t}.
$$

The common balance couples the assets economically. The solver can assign a short, high-power event to a battery while preserving a reservoir for a longer event. Assets are not optimized separately because separate solutions would ignore their competition for low-price charging energy and high-value discharge opportunities.

### Asset state transition

For each asset and interval:

$$
E_{a,t+1}=E_{a,t}
+\eta^{ch}_aP^{ch}_{a,t}\Delta t
-\frac{P^{dis}_{a,t}\Delta t}{\eta^{dis}_a}.
$$

The deterministic optimizer currently has no natural-inflow term. Natural inflow is represented in the stochastic formulation and during closed-loop simulation.

### Operating limits

Each asset obeys:

$$
\underline E_a\le E_{a,t}\le\overline E_a,
$$

$$
P^{ch}_{a,t}\le\overline P^{ch}_a z_{a,t},
$$

$$
P^{dis}_{a,t}\le\overline P^{dis}_a(1-z_{a,t}),
$$

$$
E_{a,H}\ge E^{term}_a.
$$

The binary variable prevents a single asset from charging and discharging simultaneously. Different assets may legitimately operate in opposite directions in the same interval. Such portfolio behavior may arise from different terminal requirements, efficiencies, operating costs, inflows, or power limits.

Renewable curtailment is bounded by available renewable energy:

$$
0\le C_t\le R_t.
$$

Grid imports and exports are currently unbounded above. Input validation requires the export price not to exceed the import price in the base data, which suppresses direct buy-and-resell arbitrage under the current price construction.

## Stochastic extensive-form formulation

### Scenario construction

Each scenario supplies complete time series for demand, renewable production, prices, and natural inflows. Demand, renewable production, and prices are produced by multiplying the corresponding base series by scenario-specific multipliers. Natural inflows can be specified separately for each storage asset. A legacy inflow series is assigned to the first asset when asset-specific data are absent; unspecified inflows for other assets are zero.

Provided scenario weights are normalized to sum to one. If a complete positive set of weights is not supplied, scenarios receive equal probabilities.

### Expected-cost objective

The stochastic model minimizes probability-weighted cost:

$$
\min \sum_{\omega\in\Omega}p_\omega Q_\omega,
$$

where $Q_\omega$ contains the same cost components as the deterministic objective, evaluated using scenario-specific decisions and data, plus the spillage cost

$$
c^S\sum_{a\in\mathcal A}\sum_{t\in\mathcal T}S_{\omega,a,t}.
$$

### Natural inflow and optimized spillage

For every scenario, asset, and interval, the stochastic storage transition is

$$
E_{\omega,a,t+1}=E_{\omega,a,t}
+\eta^{ch}_aP^{ch}_{\omega,a,t}\Delta t
-\frac{P^{dis}_{\omega,a,t}\Delta t}{\eta^{dis}_a}
+I_{\omega,a,t}-S_{\omega,a,t},
$$

with

$$
0\le S_{\omega,a,t}\le I_{\omega,a,t}.
$$

Spillage is scenario-dependent recourse: it is chosen after the corresponding inflow realization and is not constrained by the charge/discharge nonanticipativity window. The upper bound prevents the model from discarding previously stored energy under the label of spill. A configurable nonnegative penalty, `spill_penalty_per_mwh`, discourages avoidable spill and makes its economic effect explicit. Its default value is small (0.01 currency/MWh), so it primarily breaks ties without overstating the cost of unavoidable overflow.

The energy module currently optimizes expected cost only. It does not yet expose conditional value at risk, expected-shortfall constraints, or worst-case energy objectives analogous to the risk modes in the capacity-planning module.

### Nonanticipativity

Let $K$ be the configured commitment-window length. For every asset, pair of scenarios, and committed interval:

$$
P^{ch}_{\omega,a,t}=P^{ch}_{\omega',a,t},
\qquad
P^{dis}_{\omega,a,t}=P^{dis}_{\omega',a,t},
\qquad
z_{\omega,a,t}=z_{\omega',a,t},
\quad t<K.
$$

These equations ensure that near-term physical actions do not depend on information that has not yet been observed. After the commitment window, each scenario has independent recourse.

This structure should be interpreted carefully. It is an extensive-form model with a common near-term decision and scenario-dependent continuation. It is not a general multistage scenario tree. Once the commitment window ends, the mathematical formulation allows a scenario's decisions to use its entire remaining trajectory. Gradual information revelation is instead approximated operationally by resolving the model at the next real-time step.

## Rolling-horizon controller

The execution service turns the finite-horizon optimizer into a feedback controller. At operating time $\tau$, the observed state is the vector

$$
S_\tau=(E_{1,\tau},E_{2,\tau},\ldots,E_{|\mathcal A|,\tau}).
$$

The controller performs the following sequence:

1. Read the current stored energy of every asset.
2. Slice forecasts and scenarios to the configured look-ahead window.
3. Replace each asset's initial state with its observed state.
4. Solve the deterministic or stochastic portfolio MILP.
5. Retain only the first charge and discharge decision for each asset.
6. Observe realized demand, renewable production, prices, and inflows.
7. Apply physical limits, update each asset state, and record any adjustment or spill.
8. Advance one interval and repeat.

An intermediate window does not impose the original end-of-study terminal minimum prematurely. The preparation service replaces it with the asset's physical minimum until the rolling window reaches the end of the complete study.

This process is model-predictive control. It creates feedback because every new optimization depends on the realized state, but it does not precompute a policy for every possible future state. The theoretical foundation and terminology follow the standard MPC framework described by Rawlings, Mayne, and Diehl.

## Closed-loop simulation

Closed-loop simulation evaluates deterministic and stochastic policies on the same realized scenario. At each interval, both policies receive their own resulting storage state but face identical realized demand, renewable production, prices, and inflows. This common-realization design prevents differences in exogenous conditions from being mistaken for differences in policy quality.

The simulation layer distinguishes proposed and applied actions. A discharge is clipped when it would violate the asset's minimum energy. Energy above maximum capacity after an inflow is recorded as spill. Grid imports and exports then close the system balance. Because grid exchange is unlimited in the current simulation, load is not shed during realized execution; meaningful reliability comparisons require grid-capacity or outage constraints.

The optimizer and simulator use the same physical convention: realized natural inflow may be spilled, spill cannot exceed that interval's inflow, and spilled energy incurs the configured penalty. The optimizer chooses scenario-specific spill jointly with dispatch; the simulator records unavoidable overflow after applying the planned action. This alignment prevents artificial infeasibility when inflow exceeds available storage capacity and keeps policy cost comparisons consistent.

## Computational solution

The formulation is built with Pyomo and solved by HiGHS. Binary charging-mode variables make the deterministic and stochastic formulations mixed-integer linear programs.

For $A$ assets, $T$ intervals, and $W$ scenarios, the principal asset-indexed variable and constraint counts grow approximately in proportion to $A T$ in deterministic mode and $W A T$ in stochastic mode. Increasing the number of scenarios and the commitment window also adds nonanticipativity equations. The formulation therefore scales linearly in raw index count, although branch-and-bound effort for binary decisions can grow nonlinearly.

The solve sequence is:

```text
Validated project data
        ↓
Pyomo sets, variables, objective, and constraints
        ↓
HiGHS presolve and MILP branch-and-bound
        ↓
Termination classification
        ↓
Business-facing portfolio and per-asset results
        ↓
Independent residual validation
```

The result extractor reports both portfolio aggregates and asset-specific dispatch. Aggregate charge and discharge values are sums across assets; aggregate stored energy is the sum of asset states. Decisions should be audited at asset level whenever physical feasibility or technology behavior matters.

## Validation and reproducibility

The implementation independently recomputes:

- the system energy-balance residual;
- every asset's storage-transition residual;
- simultaneous charge and discharge for each asset;
- terminal-requirement margins;
- stochastic nonanticipativity residuals.
- spill upper-bound violations and spill-inclusive storage-transition residuals.

A result is marked validated only when the measured residuals fall within tolerance. Solver optimality and equation validation answer different questions: solver status describes the optimization algorithm's termination, while residual validation checks whether the interpreted solution respects the modeled physics.

Every asynchronous run stores a complete project and request snapshot. This makes the numerical input to a historical run reproducible even if the project is edited later. Reproducibility still depends on recording software and solver versions when studies are used for formal comparison; version metadata is a recommended addition.

The automated test suite covers single-asset compatibility, multi-asset deterministic dispatch, stochastic nonanticipativity, asset-specific inflows, exact wet/dry spill accounting, spill-cost consistency in closed-loop simulation, rolling state replacement, closed-loop state continuity, background API execution, and result validation.

## Current assumptions and limitations

The following assumptions define the interpretation of present results:

1. **Single electrical bus.** Storage location and transmission congestion are absent.
2. **Unlimited grid connection.** Imports and exports have no capacity or availability limit.
3. **Perfect deterministic forecasts.** Deterministic runs know the selected base trajectory over the look-ahead window.
4. **Finite exogenous scenarios.** The stochastic model does not estimate or generate probability distributions.
5. **Two-stage-style recourse.** Scenario information is not revealed through a general multistage tree.
6. **Expected-cost risk preference.** Tail risk and robust objectives are absent from the energy module.
7. **No degradation or cycling limits.** Battery aging, cycle budgets, and state-dependent efficiency are absent.
8. **No self-discharge, ramping, or minimum operating duration.** Power can change freely between intervals within its static limit.
9. **No reserves or ancillary services.** Storage earns value only through the modeled energy balance and terminal energy.
10. **Common terminal energy value.** Technology-specific and state-dependent opportunity values are absent.
11. **Constant interval duration.** One $\Delta t$ applies throughout a study.

These are model boundaries, not implementation details. A study conclusion should not rely on a phenomenon that the formulation does not represent.

## Development roadmap

### Phase 1 operational completeness

The first phase should improve the current MILP without changing its fundamental control architecture.

1. **Completed 25 November 2026:** add an asset-specific stochastic spill variable, spill penalty, residual validation, scenario/asset reporting, simulation cost alignment, UI interpretation, and analytical regression tests.
2. Add grid import and export capacities, availability profiles, and outage scenarios.
3. Add asset-specific terminal energy values and document how they are calibrated.
4. Add self-discharge, charge and discharge availability, and optional ramp limits.
5. Add battery degradation costs, throughput accounting, and cycle constraints where relevant.
6. Add optional reserve products and headroom constraints.
7. Add energy risk modes such as conditional value at risk and worst-case scenario cost.
8. Record application, solver, formulation, and data-schema versions in each run snapshot.

Completion criteria should include equations in this document, schema validation, result fields, independent residual checks, deterministic and stochastic unit tests, API tests, and a reproducible numerical example for every new physical mechanism.

### Phase 2 multistage scenario tree

A true multistage extensive form should represent a filtration of information. Scenarios that share the same observed history must share decisions at the corresponding node. If $h_t(\omega)$ denotes the information history of scenario $\omega$ through stage $t$, then

$$
h_t(\omega)=h_t(\omega')
\Longrightarrow
u_{\omega,t}=u_{\omega',t}.
$$

Implementation requires explicit scenario-tree nodes, parent-child relationships, conditional probabilities, node-indexed decisions, and history-based nonanticipativity. A small tree should be introduced first and compared against the current commitment-window approximation. Tree reduction or recombination will be necessary for longer horizons.

### Phase 3 dynamic value functions

A full stochastic dynamic program uses the Bellman recursion

$$
V_t(S_t,X_t)=\min_{u_t\in\mathcal U(S_t,X_t)}
\left\{c_t(S_t,X_t,u_t)
+\mathbb E\left[V_{t+1}(S_{t+1},X_{t+1})\mid S_t,X_t\right]\right\},
$$

where $S_t$ is the vector of asset energy states and $X_t$ contains observable exogenous information. Direct state discretization becomes impractical as the number of assets grows because the number of joint states increases exponentially.

Stochastic dual dynamic programming avoids explicit state-grid enumeration by approximating convex future-cost functions with piecewise-linear cuts:

$$
\widehat V_t(S_t)=\max_{k\in\mathcal K_t}
\left\{\alpha_{t,k}+\sum_{a\in\mathcal A}\beta_{t,k,a}E_{a,t}\right\}.
$$

The coefficients $\beta_{t,k,a}$ provide state- and stage-dependent marginal storage values. This approach was introduced for multistage energy planning by Pereira and Pinto and remains particularly relevant to multi-reservoir systems.

Standard SDDP relies on convex stage problems. The current binary charging-mode variables violate that condition. Before implementation, the project should evaluate three alternatives:

- remove the binaries when price ordering, positive losses, and operating costs are sufficient to rule out simultaneous operation;
- use a method designed for integer multistage decisions, with explicit computational benchmarks;
- adopt a hybrid design in which SDDP calculates long-term continuation values and the current short-term MILP retains detailed binary operation.

The hybrid design is the recommended research direction. It preserves auditable short-term constraints while replacing a fixed terminal value with a learned, asset-specific approximation of future opportunity cost.

### Phase 4 network and market representation

When asset location becomes decision-relevant, the common balance should be replaced by nodal balances. The extended model would require buses, transmission links, directional capacity, losses or a linearized power-flow representation, nodal demand and renewable generation, and storage-to-bus assignments. Grid outages and congestion could then affect each asset differently.

This phase should follow, rather than precede, basic grid-capacity limits and calibrated uncertainty. Network detail adds little value if the underlying operational and stochastic assumptions remain incomplete.

## Upgrade decision framework

Every proposed extension should answer five questions before implementation:

| Question | Required evidence |
|---|---|
| What decision will change? | A named operational or planning decision exposed by the API |
| What physical or economic mechanism is missing? | An equation, constraint, cost term, or information structure |
| What data are required? | Units, time resolution, validation rules, and uncertainty source |
| How will correctness be tested? | Analytical case, residual check, regression test, and acceptance tolerance |
| What is the computational impact? | Variable and constraint growth, solve-time benchmark, and fallback behavior |

An extension should not be considered complete when it only changes the optimizer. It must also update schemas, rolling-horizon state handling, simulation, result extraction, diagnostics, tests, user-interface interpretation, and this model reference.

## Document maintenance protocol

This file is the scientific contract for the energy module. Any change to the formulation or information structure should update it in the same change set as the code.

For each upgrade:

1. Update the baseline date and model scope.
2. Add or revise the governing equation.
3. State the new assumption and its units.
4. Identify deterministic, stochastic, rolling-horizon, and simulation effects.
5. Add validation logic and tests.
6. Record the change in the evolution table below.

| Date | Model version | Change | Validation evidence |
|---|---|---|---|
| 2026-11-24 | Multi-asset baseline | Replaced the single storage asset with a portfolio indexed by asset; added per-asset state, limits, costs, inflows, rolling state, simulation trace, and scenario commitments | Backend test suite and frontend production build |
| 2026-11-25 | Optimized spillage | Added bounded scenario- and asset-indexed spillage to the stochastic state transition and objective; aligned result extraction, simulation costs, UI reporting, and diagnostics | Analytical wet/dry regression tests, full backend suite, frontend production build, regenerated PDF |

## Implementation map

| Concern | Implementation |
|---|---|
| Data contract and result schemas | [`backend/app/modules/energy_storage/schemas.py`](../backend/app/modules/energy_storage/schemas.py) |
| Deterministic model composition | [`backend/app/modules/energy_storage/optimization/model.py`](../backend/app/modules/energy_storage/optimization/model.py) |
| Deterministic objective | [`backend/app/modules/energy_storage/optimization/objective.py`](../backend/app/modules/energy_storage/optimization/objective.py) |
| Deterministic constraints | [`backend/app/modules/energy_storage/optimization/constraints/`](../backend/app/modules/energy_storage/optimization/constraints/) |
| Stochastic model composition | [`backend/app/modules/energy_storage/optimization/stochastic/model.py`](../backend/app/modules/energy_storage/optimization/stochastic/model.py) |
| Stochastic constraints and nonanticipativity | [`backend/app/modules/energy_storage/optimization/stochastic/constraints.py`](../backend/app/modules/energy_storage/optimization/stochastic/constraints.py) |
| Rolling-horizon preparation | [`backend/app/modules/energy_storage/services/runs.py`](../backend/app/modules/energy_storage/services/runs.py) |
| Closed-loop simulation | [`backend/app/modules/energy_storage/services/simulation.py`](../backend/app/modules/energy_storage/services/simulation.py) |
| Mathematical contract summary | [`backend/app/modules/energy_storage/MODEL.md`](../backend/app/modules/energy_storage/MODEL.md) |
| Regression tests | [`backend/tests/energy_storage/test_energy_storage.py`](../backend/tests/energy_storage/test_energy_storage.py) |

## Scientific references

1. J. B. Rawlings, D. Q. Mayne, and M. M. Diehl, *Model Predictive Control: Theory, Computation, and Design*, 2nd ed., Nob Hill Publishing, 2020. [Author-maintained publication page](https://sites.engineering.ucsb.edu/~jbraw/mpc/index.html).
2. M. V. F. Pereira and L. M. V. G. Pinto, “Multi-stage stochastic optimization applied to energy planning,” *Mathematical Programming*, vol. 52, pp. 359–375, 1991. [https://doi.org/10.1007/BF01582895](https://doi.org/10.1007/BF01582895).
3. A. B. Philpott and Z. Guan, “On the convergence of stochastic dual dynamic programming and related methods,” *Operations Research Letters*, vol. 36, no. 4, pp. 450–455, 2008. [https://doi.org/10.1016/j.orl.2008.01.013](https://doi.org/10.1016/j.orl.2008.01.013).
4. C. Füllner and S. Rebennack, “Stochastic Dual Dynamic Programming and Its Variants: A Review,” *SIAM Review*, vol. 67, no. 3, pp. 415–539, 2025. [https://doi.org/10.1137/23M1575093](https://doi.org/10.1137/23M1575093).
