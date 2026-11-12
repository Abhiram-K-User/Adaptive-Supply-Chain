"""
Stage D: Multi-Commodity Optimization & Three-Layer Verification Protocol.
Formulates corridor minimum-cost & risk-aware (Expected-Cost / CVaR) multi-commodity
network flow using Google OR-Tools as primary solver and SciPy HiGHS as independent
dual-solver verifier alongside L1, L2, and L3 verification gateways.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

import networkx as nx
import numpy as np
from ortools.linear_solver import pywraplp
from scipy.optimize import linprog

from asci.core.contracts import OperatorResult, PipelineConfig
from asci.core.registry import CanonicalEntityRegistry, EntityType, get_canonical_registry
from asci.core.state import (
    FlowAllocation,
    MitigationPlan,
    OperatorTraceItem,
    OperatorType,
    PipelineState,
    PipelineStatus,
    Scenario,
    VerificationCheck,
    VerificationReport,
    VerificationVerdict,
)
from asci.uskl.graph_store import CorridorGraphStore

_FLOW_SCALE = 10  # Legacy NetworkX 0.1 TEU integer precision
_LP_EPS = 1e-6
_UNMET_PENALTY_PER_TEU = 50000.0
_SCENARIO_SPILL_PENALTY_PER_TEU = 450.0
_PASS_THROUGH_INF_CAP = 10_000_000

_MULTI_COMMODITIES: tuple[tuple[str, float, float], ...] = (
    ("POWERTRAIN_CKD", 0.45, 1.15),
    ("EV_BATTERY_PACKS", 0.25, 1.10),
    ("BODY_CHASSIS_PARTS", 0.30, 1.00),
)
_SINGLE_COMMODITY: tuple[tuple[str, float, float], ...] = (
    ("CONTAINERISED_AUTO_PARTS", 1.00, 1.00),
)


@dataclass(frozen=True)
class _ActiveEdgeSpec:
    u: str
    v: str
    key: str
    cost: float
    cap: float
    mode: str


@dataclass(frozen=True)
class _CorridorLPInstance:
    ports: tuple[str, ...]
    plants: tuple[str, ...]
    all_nodes: tuple[str, ...]
    commodities: tuple[tuple[str, float], ...]  # (name, unmet_priority_weight)
    edges: tuple[_ActiveEdgeSpec, ...]
    in_edges_by_node: dict[str, tuple[int, ...]]
    out_edges_by_node: dict[str, tuple[int, ...]]
    node_caps: dict[str, float | None]
    node_mults: dict[str, float]
    plant_demands: dict[str, dict[str, float]]
    plant_totals: dict[str, float]
    plant_covers: dict[str, float]
    event_duration_days: float
    line_stop_penalty_per_day: float
    risk_mode: str
    scenarios: tuple[Scenario, ...]
    scenario_probs: tuple[float, ...]
    spill_nodes: tuple[str, ...]
    cvar_alpha: float
    cvar_weight: float

    @property
    def use_scenarios(self) -> bool:
        return self.risk_mode in ("EXPECTED_COST", "CVAR") and len(self.scenarios) > 0


@dataclass(frozen=True)
class _SolvedLPResult:
    solver_name: str
    feasible: bool
    objective_value: float
    edge_flows: dict[tuple[int, int], float]  # (edge_idx, comm_idx) -> float
    port_dispatches: dict[tuple[int, int], float]  # (port_idx, comm_idx) -> float
    plant_deliveries: dict[tuple[int, int], float]  # (plant_idx, comm_idx) -> float
    plant_unmet: dict[tuple[int, int], float]  # (plant_idx, comm_idx) -> float
    scenario_costs: tuple[float, ...]
    cvar_cost: float | None


class StageDOptimiserAndVerifier:
    """
    Stage D Operator: Multi-Commodity Corridor Optimizer & Layered Verifier (L1-L3).
    Primary solver: Google OR-Tools GLOP LP (supporting multi-commodity, line-stop
    penalties, Expected-Cost and CVaR tail-risk modes).
    Dual verifier: Independent SciPy HiGHS matrix LP solver validating feasibility
    and optimal objective agreement alongside L1/L2/L3 protocol checks.
    """

    def __init__(
        self,
        registry: CanonicalEntityRegistry | None = None,
        graph_store: CorridorGraphStore | None = None,
    ) -> None:
        self.registry = registry or get_canonical_registry()
        self.graph_store = graph_store or CorridorGraphStore.load_from_json(registry=self.registry)

    def _build_lp_instance(self, state: PipelineState, cfg: PipelineConfig) -> _CorridorLPInstance:
        """Build canonical deterministic optimization snapshot shared by OR-Tools and HiGHS."""
        event = state.event
        graph_ctx = state.graph_context
        assert event is not None and graph_ctx is not None

        ports = tuple(sorted(e.id for e in self.registry.get_by_type(EntityType.PORT)))
        plants = tuple(sorted(e.id for e in self.registry.get_by_type(EntityType.PLANT)))
        all_nodes = tuple(sorted(self.graph_store.get_all_nodes()))

        comm_spec = _MULTI_COMMODITIES if cfg.enable_multi_commodity else _SINGLE_COMMODITY
        commodities = tuple((name, weight) for name, _, weight in comm_spec)

        node_caps: dict[str, float | None] = {}
        node_mults: dict[str, float] = {}
        for nid in all_nodes:
            ent = self.registry.get(nid)
            node_caps[nid] = float(ent.capacity_teu_per_day) if ent.capacity_teu_per_day is not None else None
            node_mults[nid] = float(graph_ctx.node_capacity_multipliers.get(nid, 1.0))

        plant_demands: dict[str, dict[str, float]] = {}
        plant_totals: dict[str, float] = {}
        plant_covers: dict[str, float] = {}
        for pid in plants:
            ent = self.registry.get(pid)
            tot_dem = float(ent.daily_demand_teu or 500.0)
            plant_totals[pid] = tot_dem
            plant_covers[pid] = float(ent.days_of_cover or 4.0)
            dem_by_comm: dict[str, float] = {}
            accum = 0.0
            for idx, (c_name, c_share, _) in enumerate(comm_spec):
                if idx == len(comm_spec) - 1:
                    val = round(max(0.0, tot_dem - accum), 4)
                else:
                    val = round(tot_dem * c_share, 4)
                    accum += val
                dem_by_comm[c_name] = val
            plant_demands[pid] = dem_by_comm

        edges_list: list[_ActiveEdgeSpec] = []
        in_map: dict[str, list[int]] = defaultdict(list)
        out_map: dict[str, list[int]] = defaultdict(list)

        for u, v, key, attrs in sorted(
            self.graph_store.graph.edges(keys=True, data=True),
            key=lambda item: (item[0], item[1], str(item[2])),
        ):
            if not attrs.get("active", True):
                continue
            e_mult = float(graph_ctx.edge_capacity_multipliers.get(f"{u}->{v}", 1.0))
            raw_cap = float(attrs.get("capacity_teu_per_day", 1000.0))
            eff_cap = max(0.0, raw_cap * e_mult)
            if eff_cap <= _LP_EPS:
                continue
            cost = max(1.0, float(attrs.get("base_cost_per_teu", 100.0)))
            mode = str(attrs.get("mode", "ROAD")).upper()
            e_idx = len(edges_list)
            edges_list.append(_ActiveEdgeSpec(u=u, v=v, key=str(key), cost=cost, cap=eff_cap, mode=mode))
            in_map[v].append(e_idx)
            out_map[u].append(e_idx)

        in_edges_by_node = {nid: tuple(in_map.get(nid, ())) for nid in all_nodes}
        out_edges_by_node = {nid: tuple(out_map.get(nid, ())) for nid in all_nodes}

        scenarios = tuple(state.scenario_set)
        if scenarios:
            raw_probs = [max(1e-6, float(s.probability)) for s in scenarios]
            p_tot = sum(raw_probs) or 1.0
            scen_probs = tuple(p / p_tot for p in raw_probs)
            spill_set = {
                nid
                for s in scenarios
                for nid in s.capacity_multipliers
                if nid in node_caps and node_caps[nid] is not None
            }
            spill_nodes = tuple(sorted(spill_set))
        else:
            scen_probs = ()
            spill_nodes = ()

        return _CorridorLPInstance(
            ports=ports,
            plants=plants,
            all_nodes=all_nodes,
            commodities=commodities,
            edges=tuple(edges_list),
            in_edges_by_node=in_edges_by_node,
            out_edges_by_node=out_edges_by_node,
            node_caps=node_caps,
            node_mults=node_mults,
            plant_demands=plant_demands,
            plant_totals=plant_totals,
            plant_covers=plant_covers,
            event_duration_days=float(event.estimated_duration_days),
            line_stop_penalty_per_day=float(cfg.line_stop_penalty_per_day),
            risk_mode=str(cfg.risk_mode),
            scenarios=scenarios,
            scenario_probs=scen_probs,
            spill_nodes=spill_nodes,
            cvar_alpha=float(cfg.cvar_alpha),
            cvar_weight=float(cfg.cvar_weight),
        )

    def _compute_cvar_scalar(
        self,
        scen_costs: tuple[float, ...],
        scen_probs: tuple[float, ...],
        alpha: float,
    ) -> float:
        """Compute exact empirical Rockafellar-Uryasev CVaR_alpha for weighted discrete scenarios."""
        if not scen_costs:
            return 0.0
        candidates = sorted(set(scen_costs))
        best = float("inf")
        tail_denom = max(1e-6, 1.0 - alpha)
        for zeta in candidates:
            val = zeta + (1.0 / tail_denom) * sum(
                p * max(0.0, c - zeta) for p, c in zip(scen_probs, scen_costs, strict=True)
            )
            if val < best:
                best = val
        return best

    def _solve_with_ortools(self, inst: _CorridorLPInstance) -> _SolvedLPResult:
        """Solve corridor optimization LP using Google OR-Tools GLOP engine."""
        solver = pywraplp.Solver.CreateSolver("GLOP")
        if solver is None:
            raise RuntimeError("Failed to initialize Google OR-Tools GLOP linear solver.")

        inf = solver.infinity()
        k_count = len(inst.commodities)
        e_count = len(inst.edges)
        p_count = len(inst.ports)
        v_count = len(inst.plants)

        port_idx_map = {pid: idx for idx, pid in enumerate(inst.ports)}
        plant_idx_map = {vid: idx for idx, vid in enumerate(inst.plants)}
        port_set = set(inst.ports)
        plant_set = set(inst.plants)

        x = [[solver.NumVar(0.0, inf, f"x_{ei}_{ki}") for ki in range(k_count)] for ei in range(e_count)]
        s_disp = [[solver.NumVar(0.0, inf, f"s_{pi}_{ki}") for ki in range(k_count)] for pi in range(p_count)]
        d_deliv = [[solver.NumVar(0.0, inf, f"d_{vi}_{ki}") for ki in range(k_count)] for vi in range(v_count)]
        u_unmet = [[solver.NumVar(0.0, inf, f"u_{vi}_{ki}") for ki in range(k_count)] for vi in range(v_count)]

        # 1. Edge capacity constraints: sum_k x[e, k] <= edge.cap
        for ei, edge in enumerate(inst.edges):
            c_edge = solver.Constraint(-inf, edge.cap, f"edge_cap_{ei}")
            for ki in range(k_count):
                c_edge.SetCoefficient(x[ei][ki], 1.0)

        # 2. Node capacity & closed-plant passthrough constraints
        for nid in inst.all_nodes:
            cap = inst.node_caps[nid]
            mult = inst.node_mults[nid]
            out_e = inst.out_edges_by_node[nid]
            in_e = inst.in_edges_by_node[nid]

            if cap is not None:
                eff_cap = max(0.0, cap * mult)
                if nid in port_set:
                    if out_e:
                        c_port = solver.Constraint(-inf, eff_cap, f"node_out_cap_{nid}")
                        for ei in out_e:
                            for ki in range(k_count):
                                c_port.SetCoefficient(x[ei][ki], 1.0)
                    else:
                        c_port0 = solver.Constraint(-inf, eff_cap, f"port_disp_cap_{nid}")
                        pi = port_idx_map[nid]
                        for ki in range(k_count):
                            c_port0.SetCoefficient(s_disp[pi][ki], 1.0)
                else:
                    if in_e:
                        c_mid = solver.Constraint(-inf, eff_cap, f"node_in_cap_{nid}")
                        for ei in in_e:
                            for ki in range(k_count):
                                c_mid.SetCoefficient(x[ei][ki], 1.0)
            else:
                # Plants (capacity_teu_per_day=None)
                if mult <= 0.0:
                    if in_e:
                        c_in0 = solver.Constraint(0.0, 0.0, f"closed_in_{nid}")
                        for ei in in_e:
                            for ki in range(k_count):
                                c_in0.SetCoefficient(x[ei][ki], 1.0)
                    if out_e:
                        c_out0 = solver.Constraint(0.0, 0.0, f"closed_out_{nid}")
                        for ei in out_e:
                            for ki in range(k_count):
                                c_out0.SetCoefficient(x[ei][ki], 1.0)
                elif mult < 0.99 and out_e:
                    passthrough_cap = max(0.0, 5000.0 * mult)
                    c_pass = solver.Constraint(-inf, passthrough_cap, f"restricted_pass_{nid}")
                    for ei in out_e:
                        for ki in range(k_count):
                            c_pass.SetCoefficient(x[ei][ki], 1.0)

        # 3. Per-(node, commodity) flow conservation
        for nid in inst.all_nodes:
            in_e = inst.in_edges_by_node[nid]
            out_e = inst.out_edges_by_node[nid]
            for ki in range(k_count):
                c_bal = solver.Constraint(0.0, 0.0, f"bal_{nid}_{ki}")
                for ei in in_e:
                    c_bal.SetCoefficient(x[ei][ki], 1.0)
                for ei in out_e:
                    c_bal.SetCoefficient(x[ei][ki], -1.0)
                if nid in port_set:
                    c_bal.SetCoefficient(s_disp[port_idx_map[nid]][ki], 1.0)
                elif nid in plant_set:
                    c_bal.SetCoefficient(d_deliv[plant_idx_map[nid]][ki], -1.0)

        # 4. Plant per-commodity demand satisfaction: d[v, k] + u[v, k] == demand[v, k]
        for vi, pid in enumerate(inst.plants):
            for ki, (c_name, _) in enumerate(inst.commodities):
                dem = inst.plant_demands[pid][c_name]
                c_dem = solver.Constraint(dem, dem, f"dem_{pid}_{ki}")
                c_dem.SetCoefficient(d_deliv[vi][ki], 1.0)
                c_dem.SetCoefficient(u_unmet[vi][ki], 1.0)

        # 5. Deterministic vs Two-Stage Scenario Expected-Cost / CVaR Objective
        objective = solver.Objective()
        objective.SetMinimization()

        scen_cost_vars: list[pywraplp.Variable] = []
        if not inst.use_scenarios:
            for ei, edge in enumerate(inst.edges):
                for ki in range(k_count):
                    objective.SetCoefficient(x[ei][ki], edge.cost)
            for vi in range(v_count):
                for ki, (_, weight) in enumerate(inst.commodities):
                    objective.SetCoefficient(u_unmet[vi][ki], _UNMET_PENALTY_PER_TEU * weight)

            # Nominal line-stop penalty: l_v >= (duration / demand_v) * sum_k u[v, k] - cover_v
            if inst.line_stop_penalty_per_day > 0.0:
                l_vars = [solver.NumVar(0.0, inf, f"ls_det_{vi}") for vi in range(v_count)]
                for vi, pid in enumerate(inst.plants):
                    cover = inst.plant_covers[pid]
                    dem_tot = max(1.0, inst.plant_totals[pid])
                    # (duration / dem_tot) * sum_k u[vi, k] - l_v <= cover
                    c_ls = solver.Constraint(-inf, cover, f"ls_det_con_{vi}")
                    for ki in range(k_count):
                        c_ls.SetCoefficient(u_unmet[vi][ki], inst.event_duration_days / dem_tot)
                    c_ls.SetCoefficient(l_vars[vi], -1.0)
                    objective.SetCoefficient(l_vars[vi], inst.line_stop_penalty_per_day)
        else:
            s_count = len(inst.scenarios)
            n_spill = len(inst.spill_nodes)
            spill_vars = [
                [solver.NumVar(0.0, inf, f"spill_{si}_{ni}") for ni in range(n_spill)]
                for si in range(s_count)
            ]
            ls_scen_vars = [
                [solver.NumVar(0.0, inf, f"ls_{si}_{vi}") for vi in range(v_count)]
                for si in range(s_count)
            ]
            scen_cost_vars = [solver.NumVar(0.0, inf, f"scen_cost_{si}") for si in range(s_count)]

            for si, scen in enumerate(inst.scenarios):
                # Spill constraints for disrupted scenario nodes: sum_out(nid) - spill[s, nid] <= Cap * mult_s
                for ni, nid in enumerate(inst.spill_nodes):
                    cap_nid = float(inst.node_caps[nid] or 0.0)
                    mult_s = float(scen.capacity_multipliers.get(nid, inst.node_mults[nid]))
                    eff_scen_cap = max(0.0, cap_nid * mult_s)
                    out_e = inst.out_edges_by_node[nid]
                    c_sp = solver.Constraint(-inf, eff_scen_cap, f"scen_spill_{si}_{nid}")
                    for ei in out_e:
                        for ki in range(k_count):
                            c_sp.SetCoefficient(x[ei][ki], 1.0)
                    c_sp.SetCoefficient(spill_vars[si][ni], -1.0)

                # Scenario line-stop triggers: (duration_s / dem_tot) * sum_k u[v, k] - ls[s, v] <= cover
                for vi, pid in enumerate(inst.plants):
                    cover = inst.plant_covers[pid]
                    dem_tot = max(1.0, inst.plant_totals[pid])
                    c_ls_s = solver.Constraint(-inf, cover, f"scen_ls_{si}_{vi}")
                    for ki in range(k_count):
                        c_ls_s.SetCoefficient(u_unmet[vi][ki], float(scen.duration_days) / dem_tot)
                    c_ls_s.SetCoefficient(ls_scen_vars[si][vi], -1.0)

                # Scenario total cost identity:
                # scen_cost[s] - sum(cost*x) - sum(unmet*u) - sum(spill_pen*spill) - sum(ls_pen*ls) == 0
                c_sc = solver.Constraint(0.0, 0.0, f"scen_cost_eq_{si}")
                c_sc.SetCoefficient(scen_cost_vars[si], 1.0)
                for ei, edge in enumerate(inst.edges):
                    for ki in range(k_count):
                        c_sc.SetCoefficient(x[ei][ki], -edge.cost)
                for vi in range(v_count):
                    for ki, (_, weight) in enumerate(inst.commodities):
                        c_sc.SetCoefficient(u_unmet[vi][ki], -_UNMET_PENALTY_PER_TEU * weight)
                    if inst.line_stop_penalty_per_day > 0.0:
                        c_sc.SetCoefficient(ls_scen_vars[si][vi], -inst.line_stop_penalty_per_day)
                for ni in range(n_spill):
                    c_sc.SetCoefficient(spill_vars[si][ni], -_SCENARIO_SPILL_PENALTY_PER_TEU)

            if inst.risk_mode == "EXPECTED_COST":
                for si, prob_s in enumerate(inst.scenario_probs):
                    objective.SetCoefficient(scen_cost_vars[si], prob_s)
            else:
                # Rockafellar-Uryasev CVaR: (1 - w)*E[C_s] + w*(zeta + 1/(1-alpha) * sum p_s * eta_s)
                w = inst.cvar_weight
                tail_denom = max(1e-6, 1.0 - inst.cvar_alpha)
                zeta = solver.NumVar(0.0, inf, "cvar_zeta")
                etas = [solver.NumVar(0.0, inf, f"cvar_eta_{si}") for si in range(s_count)]

                objective.SetCoefficient(zeta, w)
                for si, prob_s in enumerate(inst.scenario_probs):
                    # scen_cost[s] - zeta - eta[s] <= 0
                    c_eta = solver.Constraint(-inf, 0.0, f"cvar_tail_{si}")
                    c_eta.SetCoefficient(scen_cost_vars[si], 1.0)
                    c_eta.SetCoefficient(zeta, -1.0)
                    c_eta.SetCoefficient(etas[si], -1.0)

                    objective.SetCoefficient(scen_cost_vars[si], (1.0 - w) * prob_s)
                    objective.SetCoefficient(etas[si], w * prob_s / tail_denom)

        status_code = solver.Solve()
        if status_code not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            return _SolvedLPResult(
                solver_name="OR_TOOLS",
                feasible=False,
                objective_value=float("inf"),
                edge_flows={},
                port_dispatches={},
                plant_deliveries={},
                plant_unmet={},
                scenario_costs=(),
                cvar_cost=None,
            )

        edge_flows: dict[tuple[int, int], float] = {}
        for ei in range(e_count):
            for ki in range(k_count):
                val = x[ei][ki].solution_value()
                if val > _LP_EPS:
                    edge_flows[(ei, ki)] = val

        port_dispatches: dict[tuple[int, int], float] = {}
        for pi in range(p_count):
            for ki in range(k_count):
                val = s_disp[pi][ki].solution_value()
                if val > _LP_EPS:
                    port_dispatches[(pi, ki)] = val

        plant_deliveries: dict[tuple[int, int], float] = {}
        plant_unmet: dict[tuple[int, int], float] = {}
        for vi in range(v_count):
            for ki in range(k_count):
                d_val = d_deliv[vi][ki].solution_value()
                u_val = u_unmet[vi][ki].solution_value()
                if d_val > _LP_EPS:
                    plant_deliveries[(vi, ki)] = d_val
                if u_val > _LP_EPS:
                    plant_unmet[(vi, ki)] = u_val

        scen_cost_vals = tuple(round(var.solution_value(), 4) for var in scen_cost_vars)
        cvar_val = (
            round(self._compute_cvar_scalar(scen_cost_vals, inst.scenario_probs, inst.cvar_alpha), 2)
            if inst.use_scenarios and scen_cost_vals
            else None
        )

        return _SolvedLPResult(
            solver_name="OR_TOOLS",
            feasible=True,
            objective_value=float(objective.Value()),
            edge_flows=edge_flows,
            port_dispatches=port_dispatches,
            plant_deliveries=plant_deliveries,
            plant_unmet=plant_unmet,
            scenario_costs=scen_cost_vals,
            cvar_cost=cvar_val,
        )

    def _solve_with_highs_dual(self, inst: _CorridorLPInstance) -> _SolvedLPResult:
        """
        Independent SciPy HiGHS matrix LP builder validating feasibility and exact
        optimal objective independently from Google OR-Tools.
        """
        k_count = len(inst.commodities)
        e_count = len(inst.edges)
        p_count = len(inst.ports)
        v_count = len(inst.plants)
        n_spill = len(inst.spill_nodes)
        s_count = len(inst.scenarios) if inst.use_scenarios else 0

        port_idx_map = {pid: idx for idx, pid in enumerate(inst.ports)}
        plant_idx_map = {vid: idx for idx, vid in enumerate(inst.plants)}
        port_set = set(inst.ports)
        plant_set = set(inst.plants)

        # Flat variable offsets
        off_x = 0
        off_s = off_x + e_count * k_count
        off_d = off_s + p_count * k_count
        off_u = off_d + v_count * k_count
        idx_cursor = off_u + v_count * k_count

        if not inst.use_scenarios:
            use_det_ls = inst.line_stop_penalty_per_day > 0.0
            off_ls_det = idx_cursor
            idx_cursor += v_count if use_det_ls else 0
            off_spill = off_ls_scen = off_sc = off_zeta = off_eta = idx_cursor
        else:
            use_det_ls = False
            off_ls_det = idx_cursor
            off_spill = idx_cursor
            idx_cursor += s_count * n_spill
            off_ls_scen = idx_cursor
            idx_cursor += s_count * v_count
            off_sc = idx_cursor
            idx_cursor += s_count
            off_zeta = idx_cursor
            if inst.risk_mode == "CVAR":
                idx_cursor += 1
                off_eta = idx_cursor
                idx_cursor += s_count
            else:
                off_eta = idx_cursor

        n_vars = idx_cursor

        def ix_x(ei: int, ki: int) -> int:
            return off_x + ei * k_count + ki

        def ix_s(pi: int, ki: int) -> int:
            return off_s + pi * k_count + ki

        def ix_d(vi: int, ki: int) -> int:
            return off_d + vi * k_count + ki

        def ix_u(vi: int, ki: int) -> int:
            return off_u + vi * k_count + ki

        def ix_spill(si: int, ni: int) -> int:
            return off_spill + si * n_spill + ni

        def ix_ls_scen(si: int, vi: int) -> int:
            return off_ls_scen + si * v_count + vi

        c_vec = np.zeros(n_vars, dtype=np.float64)
        ub_rows: list[tuple[dict[int, float], float]] = []
        eq_rows: list[tuple[dict[int, float], float]] = []

        # Edge capacity
        for ei, edge in enumerate(inst.edges):
            row = {ix_x(ei, ki): 1.0 for ki in range(k_count)}
            ub_rows.append((row, edge.cap))

        # Node capacity & closed plants
        for nid in inst.all_nodes:
            cap = inst.node_caps[nid]
            mult = inst.node_mults[nid]
            out_e = inst.out_edges_by_node[nid]
            in_e = inst.in_edges_by_node[nid]
            if cap is not None:
                eff_cap = max(0.0, cap * mult)
                if nid in port_set:
                    if out_e:
                        row = {ix_x(ei, ki): 1.0 for ei in out_e for ki in range(k_count)}
                        ub_rows.append((row, eff_cap))
                    else:
                        pi = port_idx_map[nid]
                        row = {ix_s(pi, ki): 1.0 for ki in range(k_count)}
                        ub_rows.append((row, eff_cap))
                elif in_e:
                    row = {ix_x(ei, ki): 1.0 for ei in in_e for ki in range(k_count)}
                    ub_rows.append((row, eff_cap))
            else:
                if mult <= 0.0:
                    if in_e:
                        row = {ix_x(ei, ki): 1.0 for ei in in_e for ki in range(k_count)}
                        eq_rows.append((row, 0.0))
                    if out_e:
                        row = {ix_x(ei, ki): 1.0 for ei in out_e for ki in range(k_count)}
                        eq_rows.append((row, 0.0))
                elif mult < 0.99 and out_e:
                    row = {ix_x(ei, ki): 1.0 for ei in out_e for ki in range(k_count)}
                    ub_rows.append((row, max(0.0, 5000.0 * mult)))

        # Per-(node, commodity) flow balance
        for nid in inst.all_nodes:
            in_e = inst.in_edges_by_node[nid]
            out_e = inst.out_edges_by_node[nid]
            for ki in range(k_count):
                row: dict[int, float] = {}
                for ei in in_e:
                    row[ix_x(ei, ki)] = row.get(ix_x(ei, ki), 0.0) + 1.0
                for ei in out_e:
                    row[ix_x(ei, ki)] = row.get(ix_x(ei, ki), 0.0) - 1.0
                if nid in port_set:
                    idx_var = ix_s(port_idx_map[nid], ki)
                    row[idx_var] = row.get(idx_var, 0.0) + 1.0
                elif nid in plant_set:
                    idx_var = ix_d(plant_idx_map[nid], ki)
                    row[idx_var] = row.get(idx_var, 0.0) - 1.0
                if row:
                    eq_rows.append((row, 0.0))

        # Demand satisfaction
        for vi, pid in enumerate(inst.plants):
            for ki, (c_name, _) in enumerate(inst.commodities):
                dem = inst.plant_demands[pid][c_name]
                eq_rows.append(({ix_d(vi, ki): 1.0, ix_u(vi, ki): 1.0}, dem))

        # Objective + scenarios
        if not inst.use_scenarios:
            for ei, edge in enumerate(inst.edges):
                for ki in range(k_count):
                    c_vec[ix_x(ei, ki)] = edge.cost
            for vi in range(v_count):
                for ki, (_, weight) in enumerate(inst.commodities):
                    c_vec[ix_u(vi, ki)] = _UNMET_PENALTY_PER_TEU * weight
            if use_det_ls:
                for vi, pid in enumerate(inst.plants):
                    dem_tot = max(1.0, inst.plant_totals[pid])
                    row_ls = {ix_u(vi, ki): inst.event_duration_days / dem_tot for ki in range(k_count)}
                    row_ls[off_ls_det + vi] = -1.0
                    ub_rows.append((row_ls, inst.plant_covers[pid]))
                    c_vec[off_ls_det + vi] = inst.line_stop_penalty_per_day
        else:
            for si, scen in enumerate(inst.scenarios):
                for ni, nid in enumerate(inst.spill_nodes):
                    cap_nid = float(inst.node_caps[nid] or 0.0)
                    mult_s = float(scen.capacity_multipliers.get(nid, inst.node_mults[nid]))
                    eff_scen_cap = max(0.0, cap_nid * mult_s)
                    row_sp = {
                        ix_x(ei, ki): 1.0
                        for ei in inst.out_edges_by_node[nid]
                        for ki in range(k_count)
                    }
                    row_sp[ix_spill(si, ni)] = -1.0
                    ub_rows.append((row_sp, eff_scen_cap))

                for vi, pid in enumerate(inst.plants):
                    dem_tot = max(1.0, inst.plant_totals[pid])
                    row_ls_s = {
                        ix_u(vi, ki): float(scen.duration_days) / dem_tot for ki in range(k_count)
                    }
                    row_ls_s[ix_ls_scen(si, vi)] = -1.0
                    ub_rows.append((row_ls_s, inst.plant_covers[pid]))

                row_sc: dict[int, float] = {off_sc + si: 1.0}
                for ei, edge in enumerate(inst.edges):
                    for ki in range(k_count):
                        row_sc[ix_x(ei, ki)] = -edge.cost
                for vi in range(v_count):
                    for ki, (_, weight) in enumerate(inst.commodities):
                        row_sc[ix_u(vi, ki)] = -_UNMET_PENALTY_PER_TEU * weight
                    if inst.line_stop_penalty_per_day > 0.0:
                        row_sc[ix_ls_scen(si, vi)] = -inst.line_stop_penalty_per_day
                for ni in range(n_spill):
                    row_sc[ix_spill(si, ni)] = -_SCENARIO_SPILL_PENALTY_PER_TEU
                eq_rows.append((row_sc, 0.0))

            if inst.risk_mode == "EXPECTED_COST":
                for si, prob_s in enumerate(inst.scenario_probs):
                    c_vec[off_sc + si] = prob_s
            else:
                w = inst.cvar_weight
                tail_denom = max(1e-6, 1.0 - inst.cvar_alpha)
                c_vec[off_zeta] = w
                for si, prob_s in enumerate(inst.scenario_probs):
                    ub_rows.append(({off_sc + si: 1.0, off_zeta: -1.0, off_eta + si: -1.0}, 0.0))
                    c_vec[off_sc + si] = (1.0 - w) * prob_s
                    c_vec[off_eta + si] = w * prob_s / tail_denom

        a_ub = np.zeros((len(ub_rows), n_vars), dtype=np.float64) if ub_rows else None
        b_ub = np.zeros(len(ub_rows), dtype=np.float64) if ub_rows else None
        if ub_rows and a_ub is not None and b_ub is not None:
            for r_idx, (row_dict, rhs) in enumerate(ub_rows):
                b_ub[r_idx] = rhs
                for c_idx, val in row_dict.items():
                    a_ub[r_idx, c_idx] = val

        a_eq = np.zeros((len(eq_rows), n_vars), dtype=np.float64) if eq_rows else None
        b_eq = np.zeros(len(eq_rows), dtype=np.float64) if eq_rows else None
        if eq_rows and a_eq is not None and b_eq is not None:
            for r_idx, (row_dict, rhs) in enumerate(eq_rows):
                b_eq[r_idx] = rhs
                for c_idx, val in row_dict.items():
                    a_eq[r_idx, c_idx] = val

        res = linprog(
            c=c_vec,
            A_ub=a_ub,
            b_ub=b_ub,
            A_eq=a_eq,
            b_eq=b_eq,
            bounds=(0.0, None),
            method="highs",
        )
        if not res.success:
            return _SolvedLPResult(
                solver_name="HIGHS",
                feasible=False,
                objective_value=float("inf"),
                edge_flows={},
                port_dispatches={},
                plant_deliveries={},
                plant_unmet={},
                scenario_costs=(),
                cvar_cost=None,
            )

        sol = res.x
        edge_flows = {
            (ei, ki): float(sol[ix_x(ei, ki)])
            for ei in range(e_count)
            for ki in range(k_count)
            if sol[ix_x(ei, ki)] > _LP_EPS
        }
        port_dispatches = {
            (pi, ki): float(sol[ix_s(pi, ki)])
            for pi in range(p_count)
            for ki in range(k_count)
            if sol[ix_s(pi, ki)] > _LP_EPS
        }
        plant_deliveries = {
            (vi, ki): float(sol[ix_d(vi, ki)])
            for vi in range(v_count)
            for ki in range(k_count)
            if sol[ix_d(vi, ki)] > _LP_EPS
        }
        plant_unmet = {
            (vi, ki): float(sol[ix_u(vi, ki)])
            for vi in range(v_count)
            for ki in range(k_count)
            if sol[ix_u(vi, ki)] > _LP_EPS
        }
        scen_cost_vals = (
            tuple(round(float(sol[off_sc + si]), 4) for si in range(s_count))
            if inst.use_scenarios
            else ()
        )
        cvar_val = (
            round(self._compute_cvar_scalar(scen_cost_vals, inst.scenario_probs, inst.cvar_alpha), 2)
            if inst.use_scenarios and scen_cost_vals
            else None
        )

        return _SolvedLPResult(
            solver_name="HIGHS",
            feasible=True,
            objective_value=float(res.fun),
            edge_flows=edge_flows,
            port_dispatches=port_dispatches,
            plant_deliveries=plant_deliveries,
            plant_unmet=plant_unmet,
            scenario_costs=scen_cost_vals,
            cvar_cost=cvar_val,
        )

    def _decompose_lp_to_plan(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        inst: _CorridorLPInstance,
        lp_res: _SolvedLPResult,
    ) -> MitigationPlan:
        """Deterministically peel LP edge flows into simple per-commodity corridor routes."""
        event = state.event
        assert event is not None

        plant_set = set(inst.plants)
        port_set = set(inst.ports)
        allocations: list[FlowAllocation] = []

        for ki, (comm_name, _) in enumerate(inst.commodities):
            rem_supply = {
                inst.ports[pi]: lp_res.port_dispatches[(pi, ki)]
                for pi in range(len(inst.ports))
                if lp_res.port_dispatches.get((pi, ki), 0.0) > _LP_EPS
            }
            rem_deliv = {
                inst.plants[vi]: lp_res.plant_deliveries[(vi, ki)]
                for vi in range(len(inst.plants))
                if lp_res.plant_deliveries.get((vi, ki), 0.0) > _LP_EPS
            }

            rem_edges: dict[tuple[str, str], float] = defaultdict(float)
            edge_cost_accum: dict[tuple[str, str], float] = defaultdict(float)
            edge_modes: dict[tuple[str, str], set[str]] = defaultdict(set)

            for ei, edge in enumerate(inst.edges):
                f_val = lp_res.edge_flows.get((ei, ki), 0.0)
                if f_val > _LP_EPS:
                    uv = (edge.u, edge.v)
                    rem_edges[uv] += f_val
                    edge_cost_accum[uv] += f_val * edge.cost
                    edge_modes[uv].add(edge.mode)

            edge_unit_cost = {
                uv: edge_cost_accum[uv] / f_tot for uv, f_tot in rem_edges.items() if f_tot > _LP_EPS
            }

            adj: dict[str, list[str]] = defaultdict(list)
            for u, v in sorted(rem_edges.keys()):
                adj[u].append(v)

            def _find_path(
                start_port: str,
                adj_map: dict[str, list[str]] = adj,
                edges_rem: dict[tuple[str, str], float] = rem_edges,
                deliv_rem: dict[str, float] = rem_deliv,
            ) -> list[str] | None:
                stack: list[tuple[str, list[str]]] = [(start_port, [start_port])]
                visited = {start_port}
                while stack:
                    curr, path = stack.pop()
                    if curr in plant_set and deliv_rem.get(curr, 0.0) > _LP_EPS:
                        return path
                    neighbors = [
                        nxt
                        for nxt in adj_map.get(curr, [])
                        if edges_rem.get((curr, nxt), 0.0) > _LP_EPS and nxt not in visited
                    ]
                    for nxt in reversed(neighbors):
                        visited.add(nxt)
                        stack.append((nxt, path + [nxt]))
                return None

            grouped: dict[tuple[str, str, tuple[str, ...]], float] = defaultdict(float)
            for port_id in sorted(rem_supply.keys()):
                guard = 0
                while rem_supply.get(port_id, 0.0) > _LP_EPS and guard < 1000:
                    guard += 1
                    path = _find_path(port_id)
                    if path is None:
                        break
                    dest = path[-1]
                    hops = list(zip(path, path[1:], strict=False))
                    peel = min(
                        rem_supply[port_id],
                        rem_deliv[dest],
                        *(rem_edges[hop] for hop in hops),
                    )
                    if peel <= _LP_EPS:
                        break
                    rem_supply[port_id] -= peel
                    rem_deliv[dest] -= peel
                    for hop in hops:
                        rem_edges[hop] -= peel
                    grouped[(port_id, dest, tuple(path))] += peel

            for (origin_id, dest_id, path_tuple), raw_flow in sorted(grouped.items()):
                flow_teu = round(raw_flow, 4)
                if flow_teu <= 1e-4:
                    continue
                path_list = list(path_tuple)
                unit_cost = round(
                    sum(
                        edge_unit_cost[(u, v)]
                        for u, v in zip(path_list, path_list[1:], strict=False)
                    ),
                    4,
                )
                uses_rail = any(
                    "RAIL" in edge_modes[(u, v)]
                    for u, v in zip(path_list, path_list[1:], strict=False)
                )
                alloc_mode = "INTERMODAL_RAIL" if uses_rail else "ROAD"
                allocations.append(
                    FlowAllocation(
                        commodity=comm_name,
                        origin_id=origin_id,
                        destination_id=dest_id,
                        path=path_list,
                        mode=alloc_mode,
                        flow_teu=flow_teu,
                        unit_cost=unit_cost,
                        total_cost=round(flow_teu * unit_cost, 4),
                    )
                )

        delivered_by_plant: dict[str, float] = defaultdict(float)
        port_totals: dict[str, float] = defaultdict(float)
        total_flow = 0.0
        total_transport_cost = 0.0
        road_flow = 0.0
        rail_flow = 0.0
        for a in allocations:
            delivered_by_plant[a.destination_id] += a.flow_teu
            if a.origin_id in port_set:
                port_totals[a.origin_id] += a.flow_teu
            total_flow += a.flow_teu
            total_transport_cost += a.total_cost
            if "RAIL" in a.mode:
                rail_flow += a.flow_teu
            else:
                road_flow += a.flow_teu

        unmet_demand_teu = round(
            sum(
                max(0.0, dem - delivered_by_plant.get(pid, 0.0))
                for pid, dem in inst.plant_totals.items()
            ),
            4,
        )

        top_ports = sorted(
            ((pid, round(val, 1)) for pid, val in port_totals.items()),
            key=lambda item: (-item[1], item[0]),
        )
        gateways_desc = ", ".join(f"{pid} ({val} TEU)" for pid, val in top_ports[:3]) or "none"
        eff_risk_mode = inst.risk_mode if inst.use_scenarios else "DETERMINISTIC"
        n_comm = len(inst.commodities)

        summary = (
            f"Allocated {round(total_flow, 1)} TEU across {len(allocations)} verified routes "
            f"({n_comm} commodit{'ies' if n_comm > 1 else 'y'}, mode={eff_risk_mode}, "
            f"solver={lp_res.solver_name}) following {event.primary_entity_id} disruption "
            f"(gateways: {gateways_desc}). Rail share="
            f"{round((rail_flow / total_flow) * 100.0, 1) if total_flow > 0 else 0.0}%, "
            f"Unmet assembly demand={round(unmet_demand_teu, 1)} TEU."
        )

        plan_fingerprint = (
            hashlib.sha1(
                f"{event.event_id}:{state.session_id}:{eff_risk_mode}:{lp_res.solver_name}:"
                f"{round(lp_res.objective_value, 2)}:{unmet_demand_teu}:{len(allocations)}".encode()
            )
            .hexdigest()[:8]
            .upper()
        )

        return MitigationPlan(
            plan_id=f"PLAN_{event.event_id}_{plan_fingerprint}",
            timestamp=event.timestamp,
            objective_cost=round(lp_res.objective_value, 2),
            allocations=allocations,
            unmet_demand_teu=unmet_demand_teu,
            mode_split={
                "ROAD": round(road_flow / total_flow, 4) if total_flow > 0 else 0.0,
                "INTERMODAL_RAIL": round(rail_flow / total_flow, 4) if total_flow > 0 else 0.0,
            },
            risk_mode=eff_risk_mode,
            cvar_cost=lp_res.cvar_cost,
            solver_engine=lp_res.solver_name,
            summary=summary,
        )

    def _solve_network_flow_networkx(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
    ) -> MitigationPlan:
        """Legacy NetworkX single-commodity min-cost flow comparator (when solver_type='NETWORKX')."""
        event = state.event
        graph_ctx = state.graph_context
        assert event is not None and graph_ctx is not None

        ports = sorted(self.registry.get_by_type(EntityType.PORT), key=lambda e: e.id)
        plants = sorted(self.registry.get_by_type(EntityType.PLANT), key=lambda e: e.id)

        port_ids = {p.id for p in ports}
        plant_ids = {p.id for p in plants}

        flow_g = nx.DiGraph()
        supersource = "__SUPERSOURCE__"

        total_demand_int = 0
        plant_demands_int: dict[str, int] = {}
        for p in plants:
            d_int = int(round((p.daily_demand_teu or 500.0) * _FLOW_SCALE))
            plant_demands_int[p.id] = d_int
            total_demand_int += d_int

        flow_g.add_node(supersource, demand=-total_demand_int)

        for nid in self.graph_store.get_all_nodes():
            ent = self.registry.get(nid)
            n_in = f"{nid}__IN"
            n_out = f"{nid}__OUT"
            flow_g.add_node(n_in, demand=0)
            flow_g.add_node(n_out, demand=0)

            n_mult = graph_ctx.node_capacity_multipliers.get(nid, 1.0)
            if ent.capacity_teu_per_day is not None:
                n_cap_int = max(0, int(math.floor(ent.capacity_teu_per_day * n_mult * _FLOW_SCALE)))
            else:
                n_cap_int = _PASS_THROUGH_INF_CAP if n_mult >= 0.99 else int(5000 * n_mult * _FLOW_SCALE)
            flow_g.add_edge(n_in, n_out, capacity=n_cap_int, weight=0)

        for port in ports:
            p_mult = graph_ctx.node_capacity_multipliers.get(port.id, 1.0)
            p_cap = float(port.capacity_teu_per_day or 3000.0)
            p_cap_int = max(0, int(math.floor(p_cap * p_mult * _FLOW_SCALE)))
            flow_g.add_edge(supersource, f"{port.id}__IN", capacity=p_cap_int, weight=0)

        physical_edge_nodes: list[tuple[str, str, str, dict]] = []
        for u, v, key, attrs in sorted(
            self.graph_store.graph.edges(keys=True, data=True),
            key=lambda item: (item[0], item[1], str(item[2])),
        ):
            if not attrs.get("active", True):
                continue
            e_mult = graph_ctx.edge_capacity_multipliers.get(f"{u}->{v}", 1.0)
            raw_cap = float(attrs.get("capacity_teu_per_day", 1000.0))
            e_cap_int = max(0, int(math.floor(raw_cap * e_mult * _FLOW_SCALE)))
            if e_cap_int <= 0:
                continue

            cost_int = max(1, int(round(float(attrs.get("base_cost_per_teu", 100.0)))))
            e_node = f"__E::{u}::{v}::{key}"
            flow_g.add_node(e_node, demand=0)
            flow_g.add_edge(f"{u}__OUT", e_node, capacity=e_cap_int, weight=cost_int)
            flow_g.add_edge(e_node, f"{v}__IN", capacity=e_cap_int, weight=0)
            physical_edge_nodes.append((u, v, str(key), dict(attrs)))

        for p in plants:
            d_int = plant_demands_int[p.id]
            p_sink = f"{p.id}__SINK"
            flow_g.add_node(p_sink, demand=d_int)
            flow_g.add_edge(f"{p.id}__IN", p_sink, capacity=d_int, weight=0)
            flow_g.add_edge(supersource, p_sink, capacity=d_int, weight=int(_UNMET_PENALTY_PER_TEU))

        flow_dict = nx.min_cost_flow(flow_g)

        rem_supply: dict[str, int] = {}
        for port in ports:
            used = flow_dict[supersource].get(f"{port.id}__IN", 0)
            if used > 0:
                rem_supply[port.id] = used

        rem_deliv: dict[str, int] = {}
        unmet_int = 0
        for p in plants:
            deliv = flow_dict[f"{p.id}__IN"].get(f"{p.id}__SINK", 0)
            if deliv > 0:
                rem_deliv[p.id] = deliv
            unmet_int += flow_dict[supersource].get(f"{p.id}__SINK", 0)

        rem_edges: dict[tuple[str, str], int] = defaultdict(int)
        edge_modes: dict[tuple[str, str], set[str]] = defaultdict(set)
        edge_cost_accum: dict[tuple[str, str], float] = defaultdict(float)
        for u, v, key, attrs in physical_edge_nodes:
            e_node = f"__E::{u}::{v}::{key}"
            f_val = flow_dict.get(e_node, {}).get(f"{v}__IN", 0)
            if f_val > 0:
                rem_edges[(u, v)] += f_val
                edge_cost_accum[(u, v)] += f_val * float(attrs.get("base_cost_per_teu", 100.0))
                edge_modes[(u, v)].add(str(attrs.get("mode", "ROAD")).upper())

        edge_weighted_cost = {uv: edge_cost_accum[uv] / f_tot for uv, f_tot in rem_edges.items()}

        adj: dict[str, list[str]] = defaultdict(list)
        for u, v in sorted(rem_edges.keys()):
            adj[u].append(v)

        def _find_residual_path(start_port: str) -> list[str] | None:
            stack: list[tuple[str, list[str]]] = [(start_port, [start_port])]
            visited: set[str] = {start_port}
            while stack:
                curr, path = stack.pop()
                if curr in plant_ids and rem_deliv.get(curr, 0) > 0:
                    return path
                neighbors = [
                    nxt
                    for nxt in adj.get(curr, [])
                    if rem_edges.get((curr, nxt), 0) > 0 and nxt not in visited
                ]
                for nxt in reversed(neighbors):
                    visited.add(nxt)
                    stack.append((nxt, path + [nxt]))
            return None

        grouped_paths: dict[tuple[str, str, tuple[str, ...]], int] = defaultdict(int)
        for port_id in sorted(rem_supply.keys()):
            while rem_supply.get(port_id, 0) > 0:
                path = _find_residual_path(port_id)
                if path is None:
                    break
                dest = path[-1]
                hops = list(zip(path, path[1:], strict=False))
                peel = min(rem_supply[port_id], rem_deliv[dest], *(rem_edges[hop] for hop in hops))
                rem_supply[port_id] -= peel
                rem_deliv[dest] -= peel
                for hop in hops:
                    rem_edges[hop] -= peel
                grouped_paths[(port_id, dest, tuple(path))] += peel

        allocations: list[FlowAllocation] = []
        for (origin_id, dest_id, path_tuple), f_int in sorted(grouped_paths.items()):
            if f_int <= 0:
                continue
            path_list = list(path_tuple)
            flow_teu = round(f_int / _FLOW_SCALE, 4)
            unit_cost = round(
                sum(
                    edge_weighted_cost[(u, v)]
                    for u, v in zip(path_list, path_list[1:], strict=False)
                ),
                4,
            )
            uses_rail = any(
                "RAIL" in edge_modes[(u, v)]
                for u, v in zip(path_list, path_list[1:], strict=False)
            )
            allocations.append(
                FlowAllocation(
                    commodity="CONTAINERISED_AUTO_PARTS",
                    origin_id=origin_id,
                    destination_id=dest_id,
                    path=path_list,
                    mode="INTERMODAL_RAIL" if uses_rail else "ROAD",
                    flow_teu=flow_teu,
                    unit_cost=unit_cost,
                    total_cost=round(flow_teu * unit_cost, 4),
                )
            )

        unmet_demand_teu = round(unmet_int / _FLOW_SCALE, 4)
        total_flow = sum(a.flow_teu for a in allocations)
        total_transport_cost = sum(a.total_cost for a in allocations)
        road_flow = sum(a.flow_teu for a in allocations if a.mode == "ROAD")
        rail_flow = sum(a.flow_teu for a in allocations if "RAIL" in a.mode)

        port_totals: dict[str, float] = defaultdict(float)
        for a in allocations:
            port_totals[a.origin_id] += a.flow_teu
        top_ports = sorted(
            ((pid, round(val, 1)) for pid, val in port_totals.items() if pid in port_ids),
            key=lambda x: (-x[1], x[0]),
        )
        gateways_desc = ", ".join(f"{pid} ({val} TEU)" for pid, val in top_ports[:3]) or "none"

        summary = (
            f"Allocated {round(total_flow, 1)} TEU across {len(allocations)} verified corridor routes "
            f"(solver=NETWORKX) following {event.primary_entity_id} disruption (gateways: {gateways_desc}). "
            f"Rail share={round((rail_flow / total_flow) * 100.0, 1) if total_flow > 0 else 0.0}%, "
            f"Unmet assembly demand={round(unmet_demand_teu, 1)} TEU."
        )

        plan_fingerprint = (
            hashlib.sha1(
                f"{event.event_id}:{state.session_id}:NETWORKX:{round(total_transport_cost, 2)}:{unmet_demand_teu}:{len(allocations)}".encode()
            )
            .hexdigest()[:8]
            .upper()
        )

        return MitigationPlan(
            plan_id=f"PLAN_{event.event_id}_{plan_fingerprint}",
            timestamp=event.timestamp,
            objective_cost=round(total_transport_cost + unmet_demand_teu * _UNMET_PENALTY_PER_TEU, 2),
            allocations=allocations,
            unmet_demand_teu=unmet_demand_teu,
            mode_split={
                "ROAD": round(road_flow / total_flow, 4) if total_flow > 0 else 0.0,
                "INTERMODAL_RAIL": round(rail_flow / total_flow, 4) if total_flow > 0 else 0.0,
            },
            risk_mode="DETERMINISTIC",
            cvar_cost=None,
            solver_engine=cfg.solver_type,
            summary=summary,
        )

    def run(
        self,
        state: PipelineState,
        cfg: PipelineConfig,
        rng: random.Random,
    ) -> tuple[PipelineState, OperatorResult]:
        """
        Execute Stage D optimization (OR-Tools + HiGHS dual verification) and L1-L3 verification.
        """
        _ = rng
        t0 = time.perf_counter()

        if not state.event or not state.graph_context:
            error_msg = "Stage D prerequisite failure: event or graph_context missing in PipelineState."
            return state, OperatorResult(
                operator_type=OperatorType.OPTIMIZE,
                success=False,
                message=error_msg,
                error=error_msg,
            )

        event = state.event
        graph_ctx = state.graph_context

        lp_inst = self._build_lp_instance(state, cfg)
        ortools_res: _SolvedLPResult | None = None
        highs_res: _SolvedLPResult | None = None

        if state.candidate_plan is not None:
            candidate_plan = state.candidate_plan
            highs_res = self._solve_with_highs_dual(lp_inst)
            ortools_res = self._solve_with_ortools(lp_inst)
        elif str(cfg.solver_type).upper() == "NETWORKX":
            candidate_plan = self._solve_network_flow_networkx(state, cfg)
        else:
            ortools_res = self._solve_with_ortools(lp_inst)
            highs_res = self._solve_with_highs_dual(lp_inst)
            if not ortools_res.feasible:
                error_msg = "OR-Tools primary LP failed to find a feasible relaxation."
                return state, OperatorResult(
                    operator_type=OperatorType.OPTIMIZE,
                    success=False,
                    message=error_msg,
                    error=error_msg,
                )
            candidate_plan = self._decompose_lp_to_plan(state, cfg, lp_inst, ortools_res)

        # -------------------------------------------------------------------
        # Three-Layer Verification Protocol (L1, L2, L3)
        # -------------------------------------------------------------------
        l1_checks: list[VerificationCheck] = []
        l2_checks: list[VerificationCheck] = []
        l3_checks: list[VerificationCheck] = []
        failed_checks: list[str] = []

        # --- Layer 1: Ingestion & Graph Grounding Validation ---
        all_plan_entities = set()
        for a in candidate_plan.allocations:
            all_plan_entities.add(a.origin_id)
            all_plan_entities.add(a.destination_id)
            all_plan_entities.update(a.path)

        unregistered = sorted(eid for eid in all_plan_entities if not self.registry.validate_id(eid))
        if not unregistered:
            l1_checks.append(
                VerificationCheck(
                    layer="L1",
                    check_name="CANONICAL_ENTITY_GROUNDING",
                    verdict=VerificationVerdict.PASS,
                    details="All referenced path nodes and origins/destinations exist in Canonical Registry.",
                    metrics={"validated_entity_count": len(all_plan_entities)},
                )
            )
        else:
            l1_checks.append(
                VerificationCheck(
                    layer="L1",
                    check_name="CANONICAL_ENTITY_GROUNDING",
                    verdict=VerificationVerdict.FAIL,
                    details=f"Ungrounded entity IDs detected in plan: {unregistered}",
                )
            )
            failed_checks.append("L1:CANONICAL_ENTITY_GROUNDING")

        if event.corroboration_count >= 1:
            l1_checks.append(
                VerificationCheck(
                    layer="L1",
                    check_name="SOURCE_CORROBORATION",
                    verdict=VerificationVerdict.PASS,
                    details=f"Event corroborated across {event.corroboration_count} source(s).",
                    metrics={"corroboration_count": event.corroboration_count},
                )
            )
        else:
            l1_checks.append(
                VerificationCheck(
                    layer="L1",
                    check_name="SOURCE_CORROBORATION",
                    verdict=VerificationVerdict.FAIL,
                    details="Corroboration count below required threshold of 1.",
                )
            )
            failed_checks.append("L1:SOURCE_CORROBORATION")

        # --- Layer 2: Network Feasibility & Mathematical Solvency ---
        # 2.1 Graph Edge Validity & Acyclic Continuity
        invalid_paths: list[str] = []
        for idx, a in enumerate(candidate_plan.allocations):
            if len(a.path) < 2:
                invalid_paths.append(f"alloc[{idx}] path length < 2")
                continue
            if a.path[0] != a.origin_id or a.path[-1] != a.destination_id:
                invalid_paths.append(
                    f"alloc[{idx}] endpoints mismatch ({a.origin_id}->{a.destination_id} vs {a.path[0]}->{a.path[-1]})"
                )
                continue
            if len(set(a.path)) != len(a.path):
                invalid_paths.append(f"alloc[{idx}] contains cycle {a.path}")
                continue
            for u, v in zip(a.path, a.path[1:], strict=False):
                if not self.graph_store.has_active_edge(u, v):
                    invalid_paths.append(f"alloc[{idx}] non-existent or inactive edge {u}->{v}")
                    break

        if not invalid_paths:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="GRAPH_EDGE_VALIDITY",
                    verdict=VerificationVerdict.PASS,
                    details="All allocation paths traverse active directed edges in CorridorGraphStore.",
                    metrics={"checked_allocations": len(candidate_plan.allocations)},
                )
            )
        else:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="GRAPH_EDGE_VALIDITY",
                    verdict=VerificationVerdict.FAIL,
                    details="; ".join(invalid_paths[:3]),
                )
            )
            failed_checks.append("L2:GRAPH_EDGE_VALIDITY")

        # 2.2 Aggregated Node & Edge Capacity Bounds (across all commodities)
        node_flows: dict[str, float] = defaultdict(float)
        node_passthrough_out: dict[str, float] = defaultdict(float)
        edge_flows: dict[tuple[str, str], float] = defaultdict(float)
        for a in candidate_plan.allocations:
            for nid in set(a.path):
                node_flows[nid] += a.flow_teu
            for hop_idx, (u, v) in enumerate(zip(a.path, a.path[1:], strict=False)):
                edge_flows[(u, v)] += a.flow_teu
                if hop_idx > 0:
                    node_passthrough_out[u] += a.flow_teu

        capacity_breaches: list[str] = []
        for nid, flow_val in sorted(node_flows.items()):
            if not self.registry.validate_id(nid):
                capacity_breaches.append(f"ungrounded node {nid}")
                continue
            ent = self.registry.get(nid)
            mult = graph_ctx.node_capacity_multipliers.get(nid, 1.0)
            if ent.capacity_teu_per_day is not None:
                eff_cap = ent.capacity_teu_per_day * mult
                if flow_val > eff_cap + 1e-4:
                    capacity_breaches.append(
                        f"node {nid} flow {round(flow_val, 2)} > effective cap {round(eff_cap, 2)}"
                    )
            else:
                if mult <= 0.0 and flow_val > 1e-4:
                    capacity_breaches.append(
                        f"closed node {nid} (mult=0.0) carried flow {round(flow_val, 2)}"
                    )
                elif mult < 0.99:
                    passthrough_cap = 5000.0 * mult
                    if node_passthrough_out[nid] > passthrough_cap + 1e-4:
                        capacity_breaches.append(
                            f"restricted node {nid} passthrough {round(node_passthrough_out[nid], 2)} "
                            f"> effective cap {round(passthrough_cap, 2)}"
                        )

        for (u, v), flow_val in sorted(edge_flows.items()):
            active_edges = self.graph_store.get_active_edges(u, v)
            if not active_edges:
                capacity_breaches.append(f"missing active edge {u}->{v}")
                continue
            nom_edge_cap = sum(
                float(attrs.get("capacity_teu_per_day", 0.0)) for _, attrs in active_edges
            )
            e_mult = graph_ctx.edge_capacity_multipliers.get(f"{u}->{v}", 1.0)
            eff_edge_cap = nom_edge_cap * e_mult
            if flow_val > eff_edge_cap + 1e-4:
                capacity_breaches.append(
                    f"edge {u}->{v} flow {round(flow_val, 2)} > effective cap {round(eff_edge_cap, 2)}"
                )

        if not capacity_breaches:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="EDGE_CAPACITY_BOUNDS",
                    verdict=VerificationVerdict.PASS,
                    details="Aggregated node and directed-edge flows obey physical effective capacity bounds.",
                    metrics={
                        "checked_nodes": len(node_flows),
                        "checked_edges": len(edge_flows),
                    },
                )
            )
        else:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="EDGE_CAPACITY_BOUNDS",
                    verdict=VerificationVerdict.FAIL,
                    details="; ".join(capacity_breaches[:3]),
                )
            )
            failed_checks.append("L2:EDGE_CAPACITY_BOUNDS")

        # 2.3 Per-Commodity Flow Conservation, Terminal Type Grounding & Per-Plant Demand Reconciliation
        port_ids = {e.id for e in self.registry.get_by_type(EntityType.PORT)}
        plants = self.registry.get_by_type(EntityType.PLANT)
        plant_demand_map = {p.id: float(p.daily_demand_teu or 500.0) for p in plants}

        conservation_errors: list[str] = []
        origin_outflows: dict[str, float] = defaultdict(float)
        dest_inflows: dict[str, float] = defaultdict(float)
        dest_comm_inflows: dict[tuple[str, str], float] = defaultdict(float)
        transit_in: dict[tuple[str, str], float] = defaultdict(float)
        transit_out: dict[tuple[str, str], float] = defaultdict(float)
        multi_comm_shares = {name: share for name, share, _ in _MULTI_COMMODITIES}

        for idx, a in enumerate(candidate_plan.allocations):
            if a.flow_teu < 0 or a.unit_cost < 0 or a.total_cost < 0:
                conservation_errors.append(f"alloc[{idx}] contains negative flow or cost")
                continue
            if a.flow_teu > 1e-4 and a.origin_id not in port_ids:
                conservation_errors.append(
                    f"alloc[{idx}] non-port origin '{a.origin_id}' cannot originate freight supply"
                )
            if a.flow_teu > 1e-4 and a.destination_id not in plant_demand_map:
                conservation_errors.append(
                    f"alloc[{idx}] non-plant destination '{a.destination_id}' cannot absorb demand"
                )
            expected_cost = a.flow_teu * a.unit_cost
            if abs(a.total_cost - expected_cost) > max(1.0, 0.01 * expected_cost):
                conservation_errors.append(
                    f"alloc[{idx}] total_cost {a.total_cost} != flow*unit_cost {round(expected_cost, 2)}"
                )
            origin_outflows[a.origin_id] += a.flow_teu
            dest_inflows[a.destination_id] += a.flow_teu
            dest_comm_inflows[(a.destination_id, a.commodity)] += a.flow_teu
            for hop_idx, (u, v) in enumerate(zip(a.path, a.path[1:], strict=False)):
                if hop_idx > 0:
                    transit_in[(u, a.commodity)] += a.flow_teu
                if hop_idx < len(a.path) - 2:
                    transit_out[(v, a.commodity)] += a.flow_teu

        all_transit_keys = set(transit_in.keys()) | set(transit_out.keys())
        for nid, comm in sorted(all_transit_keys):
            diff = abs(transit_in[(nid, comm)] - transit_out[(nid, comm)])
            if diff > 1e-3:
                conservation_errors.append(f"transit imbalance at ({nid}, {comm}): diff={round(diff, 4)}")

        total_origin = sum(origin_outflows.values())
        total_dest = sum(dest_inflows.values())
        if abs(total_origin - total_dest) > 1e-3:
            conservation_errors.append(f"origin total {total_origin} != destination total {total_dest}")

        for plant_id, plant_dem in sorted(plant_demand_map.items()):
            delivered = dest_inflows.get(plant_id, 0.0)
            if delivered > plant_dem + 0.5:
                conservation_errors.append(
                    f"over-delivery to {plant_id}: {round(delivered, 2)} > demand {round(plant_dem, 2)}"
                )
            for comm_name, share in multi_comm_shares.items():
                comm_deliv = dest_comm_inflows.get((plant_id, comm_name), 0.0)
                if comm_deliv > (plant_dem * share) + 0.5:
                    conservation_errors.append(
                        f"commodity over-delivery ({plant_id}, {comm_name}): "
                        f"{round(comm_deliv, 2)} > demand {round(plant_dem * share, 2)}"
                    )

        total_corridor_demand = sum(plant_demand_map.values())
        expected_unmet = sum(
            max(0.0, plant_dem - dest_inflows.get(plant_id, 0.0))
            for plant_id, plant_dem in plant_demand_map.items()
        )
        if candidate_plan.unmet_demand_teu < 0:
            conservation_errors.append("negative unmet_demand_teu")
        elif abs(candidate_plan.unmet_demand_teu - expected_unmet) > 0.5:
            conservation_errors.append(
                f"unmet_demand_teu ({round(candidate_plan.unmet_demand_teu, 2)}) != "
                f"reconciled plant shortfall ({round(expected_unmet, 2)})"
            )

        if not conservation_errors:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="FLOW_CONSERVATION",
                    verdict=VerificationVerdict.PASS,
                    details=(
                        f"Per-commodity flow conservation verified across {len(all_transit_keys)} transit keys; "
                        f"delivered {round(total_dest, 1)} / {round(total_corridor_demand, 1)} TEU "
                        f"(unmet {round(candidate_plan.unmet_demand_teu, 1)} TEU)."
                    ),
                    metrics={
                        "total_delivered_teu": round(total_dest, 2),
                        "total_demand_teu": round(total_corridor_demand, 2),
                        "unmet_demand_teu": round(candidate_plan.unmet_demand_teu, 2),
                    },
                )
            )
        else:
            l2_checks.append(
                VerificationCheck(
                    layer="L2",
                    check_name="FLOW_CONSERVATION",
                    verdict=VerificationVerdict.FAIL,
                    details="; ".join(conservation_errors[:3]),
                )
            )
            failed_checks.append("L2:FLOW_CONSERVATION")

        # 2.4 Dual-Solver Agreement (Google OR-Tools vs Independent SciPy HiGHS)
        if ortools_res is not None and highs_res is not None:
            if not (ortools_res.feasible and highs_res.feasible):
                l2_checks.append(
                    VerificationCheck(
                        layer="L2",
                        check_name="DUAL_SOLVER_AGREEMENT",
                        verdict=VerificationVerdict.FAIL,
                        details=(
                            f"Solver feasibility mismatch: OR-Tools={ortools_res.feasible}, "
                            f"HiGHS={highs_res.feasible}"
                        ),
                    )
                )
                failed_checks.append("L2:DUAL_SOLVER_AGREEMENT")
            else:
                abs_diff = abs(ortools_res.objective_value - highs_res.objective_value)
                tol = max(5.0, 0.001 * max(1.0, abs(highs_res.objective_value)))
                rel_pct = (
                    (abs_diff / max(1.0, abs(highs_res.objective_value))) * 100.0
                )
                # Flag valid-topology injected plans that claim artificially cheap cost below dual lower bound
                injected_struct_ok = (
                    state.candidate_plan is not None
                    and not invalid_paths
                    and not capacity_breaches
                    and not conservation_errors
                )
                cheated_lower_bound = (
                    injected_struct_ok
                    and candidate_plan.objective_cost + 5.0 < highs_res.objective_value
                )
                if abs_diff <= tol and not cheated_lower_bound:
                    l2_checks.append(
                        VerificationCheck(
                            layer="L2",
                            check_name="DUAL_SOLVER_AGREEMENT",
                            verdict=VerificationVerdict.PASS,
                            details=(
                                f"OR-Tools GLOP ({round(ortools_res.objective_value, 2)}) agrees with "
                                f"SciPy HiGHS ({round(highs_res.objective_value, 2)}) within {round(rel_pct, 5)}%."
                            ),
                            metrics={
                                "ortools_objective": round(ortools_res.objective_value, 2),
                                "highs_objective": round(highs_res.objective_value, 2),
                                "rel_diff_pct": round(rel_pct, 6),
                                "risk_mode": lp_inst.risk_mode,
                            },
                        )
                    )
                else:
                    l2_checks.append(
                        VerificationCheck(
                            layer="L2",
                            check_name="DUAL_SOLVER_AGREEMENT",
                            verdict=VerificationVerdict.FAIL,
                            details=(
                                f"Dual solver divergence or sub-lower-bound plan cost: "
                                f"OR={round(ortools_res.objective_value, 2)}, "
                                f"HiGHS={round(highs_res.objective_value, 2)}, "
                                f"plan={round(candidate_plan.objective_cost, 2)}"
                            ),
                        )
                    )
                    failed_checks.append("L2:DUAL_SOLVER_AGREEMENT")

        # --- Layer 3: Decision Sanity & Citation Support ---
        max_unmet_allowed = max(10.0, total_corridor_demand * cfg.max_unmet_demand_ratio)
        if candidate_plan.unmet_demand_teu <= max_unmet_allowed:
            l3_checks.append(
                VerificationCheck(
                    layer="L3",
                    check_name="UNMET_DEMAND_BOUND",
                    verdict=VerificationVerdict.PASS,
                    details=(
                        f"Unmet demand {round(candidate_plan.unmet_demand_teu, 1)} TEU is within "
                        f"tolerance ({round(max_unmet_allowed, 1)} TEU)."
                    ),
                    metrics={"unmet_demand_teu": candidate_plan.unmet_demand_teu},
                )
            )
        else:
            l3_checks.append(
                VerificationCheck(
                    layer="L3",
                    check_name="UNMET_DEMAND_BOUND",
                    verdict=VerificationVerdict.FAIL,
                    details=(
                        f"Unmet demand {round(candidate_plan.unmet_demand_teu, 1)} TEU exceeds "
                        f"tolerance ({round(max_unmet_allowed, 1)} TEU)."
                    ),
                )
            )
            failed_checks.append("L3:UNMET_DEMAND_BOUND")

        relevant_entities = {event.primary_entity_id, *event.affected_entity_ids, *all_plan_entities}
        covering_docs = [
            doc
            for doc in state.evidence_set
            if any(eid in relevant_entities for eid in doc.entity_ids)
        ]
        if covering_docs:
            l3_checks.append(
                VerificationCheck(
                    layer="L3",
                    check_name="CITATION_GROUNDING",
                    verdict=VerificationVerdict.PASS,
                    details=f"Plan grounded against {len(covering_docs)} entity-matched evidence citations.",
                    metrics={
                        "citation_count": len(covering_docs),
                        "citation_ids": [d.citation_id for d in covering_docs],
                    },
                )
            )
        else:
            l3_checks.append(
                VerificationCheck(
                    layer="L3",
                    check_name="CITATION_GROUNDING",
                    verdict=VerificationVerdict.WARN,
                    details="No retrieved evidence citations directly cover disrupted or rerouted entities.",
                    metrics={"citation_count": len(state.evidence_set)},
                )
            )

        overall_pass = len(failed_checks) == 0
        overall_verdict = VerificationVerdict.PASS if overall_pass else VerificationVerdict.FAIL

        verification_report = VerificationReport(
            overall_verdict=overall_verdict,
            passed=overall_pass,
            l1_checks=l1_checks,
            l2_checks=l2_checks,
            l3_checks=l3_checks,
            failed_checks=failed_checks,
        )

        duration_ms = (time.perf_counter() - t0) * 1000.0
        op_cost = 0.0075

        trace_item = OperatorTraceItem(
            step_index=state.step_count + 1,
            operator_type=OperatorType.VERIFY,
            input_summary=f"Plan {candidate_plan.plan_id}, allocations={len(candidate_plan.allocations)}",
            output_summary=f"Verification verdict={overall_verdict.value}, passed={overall_pass}",
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            seed=cfg.random_seed,
            timestamp=datetime.now(UTC),
        )

        new_status = PipelineStatus.VERIFIED if overall_pass else PipelineStatus.FAILED

        new_state = state.transition(
            updates={
                "candidate_plan": candidate_plan,
                "verification_report": verification_report,
                "status": new_status,
            },
            trace_item=trace_item,
        )

        result = OperatorResult(
            operator_type=OperatorType.VERIFY,
            success=overall_pass,
            message=(
                f"Stage D verified plan {candidate_plan.plan_id}: "
                f"Overall={overall_verdict.value}, failed_checks={failed_checks}."
            ),
            duration_ms=round(duration_ms, 2),
            cost=op_cost,
            artifacts={
                "plan_id": candidate_plan.plan_id,
                "overall_verdict": overall_verdict.value,
                "failed_checks": failed_checks,
                "solver_engine": candidate_plan.solver_engine,
                "risk_mode": candidate_plan.risk_mode,
            },
        )

        return new_state, result
