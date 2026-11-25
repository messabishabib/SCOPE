# Multi-Asset Energy-Storage Dispatch Model

This document is the mathematical contract for the first energy module. Code names match the formulation names so that future modifications can be reviewed equation by equation.

## Scope and assumptions

- A portfolio of pumped-hydro, battery, or generic storage assets connected to the same system balance.
- Perfect forecasts over a finite horizon.
- Constant interval duration `Δt` in hours.
- Linear charging and discharging efficiencies.
- Charging and discharging are mutually exclusive.
- Grid export price cannot exceed grid import price in this version.
- Every asset has independent energy bounds, power limits, efficiencies, variable costs, initial state, and terminal requirement.
- The deterministic model has no natural inflow; asset-specific scenario inflows are represented in the stochastic model and simulation.
- Reserves and ramping are future extensions.

## Sets

- `A`: storage assets.
- `T = {0, ..., H-1}`: dispatch periods.
- `T⁺ = {0, ..., H}`: storage-state boundaries.

All physical storage variables and constraints below are applied for every `a ∈ A`. The system energy balance uses the sum of charging and discharging across the portfolio; state transitions, bounds, efficiencies, costs, and terminal requirements remain asset-specific.

## Input parameters

| Mathematical name | Code field | Unit | Meaning |
|---|---|---|---|
| `D_t` | `demand_mwh[t]` | MWh | Energy demand during period `t` |
| `R_t` | `renewable_generation_mwh[t]` | MWh | Available renewable energy |
| `πᶦ_t` | `grid_import_price_per_mwh[t]` | currency/MWh | Import price |
| `πᵉ_t` | `grid_export_price_per_mwh[t]` | currency/MWh | Export revenue rate |
| `Ē` | `energy_capacity_mwh` | MWh | Maximum stored energy |
| `E̲` | `minimum_energy_mwh` | MWh | Minimum stored energy |
| `E₀` | `initial_energy_mwh` | MWh | Initial stored energy |
| `Eᴴ_min` | `terminal_energy_minimum_mwh` | MWh | Required final energy |
| `P̄ᶜ`, `P̄ᵈ` | maximum charge/discharge power | MW | Pump and turbine limits |
| `ηᶜ`, `ηᵈ` | charge/discharge efficiency | ratio | Conversion efficiencies |

## Decision variables

| Mathematical name | Pyomo name | Unit |
|---|---|---|
| `Pᶜ_t` | `charge_power_mw[t]` | MW |
| `Pᵈ_t` | `discharge_power_mw[t]` | MW |
| `E_t` | `stored_energy_mwh[t]` | MWh |
| `Gᶦ_t` | `grid_import_mwh[t]` | MWh |
| `Gᵉ_t` | `grid_export_mwh[t]` | MWh |
| `U_t` | `unserved_energy_mwh[t]` | MWh |
| `C_t` | `renewable_curtailment_mwh[t]` | MWh |
| `z_t` | `is_charging[t]` | binary |

## Objective

Minimize total system cost:

```text
Σt [πᶦ_t Gᶦ_t - πᵉ_t Gᵉ_t
    + cᶜ Pᶜ_t Δt + cᵈ Pᵈ_t Δt
    + cᵘ U_t]
- vᴴ E_H
```

Every term is a named Pyomo `Expression` in `optimization/objective.py` and is returned separately in the API result.

## Constraints

### Energy balance

For every period `t`:

```text
R_t - C_t + Gᶦ_t + Pᵈ_t Δt + U_t
= D_t + Pᶜ_t Δt + Gᵉ_t
```

Implemented as `model.energy_balance`.

### Storage transition

```text
E_{t+1} = E_t + ηᶜ Pᶜ_t Δt - Pᵈ_t Δt / ηᵈ
```

Implemented as `model.storage_transition`, with `model.initial_storage` fixing `E₀`.

### Storage limits

```text
E̲ ≤ E_t ≤ Ē
```

Implemented as `model.storage_minimum` and `model.storage_maximum`.

### Pump and turbine limits

```text
Pᶜ_t ≤ P̄ᶜ z_t
Pᵈ_t ≤ P̄ᵈ (1-z_t)
```

Implemented as `model.charge_power_limit` and `model.discharge_power_limit`. The binary variable prevents simultaneous pumping and generation.

### Terminal requirement

```text
E_H ≥ Eᴴ_min
```

Implemented as `model.terminal_storage_requirement`. This prevents the finite-horizon optimizer from creating an unrealistic benefit by emptying storage at the end.

### Renewable curtailment

```text
0 ≤ C_t ≤ R_t
```

Implemented as `model.renewable_curtailment_limit`.

## Solution validation

`optimization/validation.py` independently recomputes energy balances, storage transitions, simultaneous operation, and terminal compliance from the returned values. A result is exposed as validated only when all residuals are within tolerance.

## Scenario-based extension

The stochastic model is implemented separately under `optimization/stochastic/`. It introduces a scenario set `Ω`, scenario probabilities `pω`, and scenario-indexed dispatch and storage variables.

The objective minimizes probability-weighted system cost:

```text
min Σω pω Costω
```

Demand, renewable production, prices, and natural inflows may differ by scenario. The physical charging and discharging actions in the configured commitment window are made before uncertainty is revealed:

```text
Pᶜ_{ω,t} = Pᶜ_{ω₀,t}
Pᵈ_{ω,t} = Pᵈ_{ω₀,t}       for t in the commitment window
z_{ω,t}  = z_{ω₀,t}
```

These equations are imposed separately for every storage asset and implemented as `model.nonanticipativity`. Grid balancing and decisions after the commitment window are scenario-dependent recourse decisions. The model is therefore one stochastic extensive-form optimization, not a collection of independently optimized scenarios.

## Rolling-horizon execution

At a new decision epoch, the API accepts the current absolute period, observed stored energy, and look-ahead length. It then:

1. Replaces the original initial storage with the observed state.
2. Slices every forecast and scenario series to the remaining look-ahead window.
3. Solves the deterministic or stochastic model.
4. Returns the shared immediate pump/turbine action.

Only the immediate action is intended for implementation. The optimizer should be called again after the next state and forecasts become available.

## Closed-loop simulation

The simulation is an evaluator around the optimization models; it is not an additional optimization formulation. For each policy and period it executes this loop:

```text
observed state -> optimize the look-ahead -> retain the first action
-> reveal demand, renewable output, price, and inflow
-> apply physical limits -> balance with the grid -> update stored energy
```

Both deterministic and stochastic policies are evaluated on the same selected realized scenario. This is essential for a fair comparison.

### Physical state transition during simulation

For realized inflow `I_t` and spill `S_t`:

```text
E_{t+1} = E_t + eta_c P^c_t Delta-t - P^d_t Delta-t / eta_d + I_t - S_t
```

If an unforeseen inflow would exceed storage capacity, the excess is recorded as spill. A proposed discharge is clipped if executing it would violate minimum storage. The trace keeps both the proposed and applied actions so this adjustment is visible.

### Realized cost

Each period records:

```text
import price * grid import - export price * grid export
+ variable charge cost + variable discharge cost
```

Remaining stored energy is valued at the simulation boundary. This prevents a policy from appearing artificially cheap simply because it empties the reservoir before the evaluation ends. Because the current grid connection is unlimited, simulation v1 does not shed load; a grid-capacity or outage model is required before unserved-energy reliability comparisons are meaningful.

