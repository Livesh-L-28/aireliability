"""Package entry for benchmarks.scenarios."""

from benchmarks.scenarios.latency_regression import (
    agent_f_faulty,
    agent_f_nominal,
    get_scenario_f,
)
from benchmarks.scenarios.missing_tool import (
    agent_d_faulty,
    agent_d_nominal,
    get_scenario_d,
)
from benchmarks.scenarios.output_regression import (
    agent_e_faulty,
    agent_e_nominal,
    get_scenario_e,
)
from benchmarks.scenarios.tool_order import (
    agent_a_faulty,
    agent_a_nominal,
    get_scenario_a,
)
from benchmarks.scenarios.wrong_arguments import (
    agent_c_faulty,
    agent_c_nominal,
    get_scenario_c,
)
from benchmarks.scenarios.wrong_tool import (
    agent_b_faulty,
    agent_b_nominal,
    get_scenario_b,
)

__all__ = [
    "agent_a_faulty",
    "agent_a_nominal",
    "agent_b_faulty",
    "agent_b_nominal",
    "agent_c_faulty",
    "agent_c_nominal",
    "agent_d_faulty",
    "agent_d_nominal",
    "agent_e_faulty",
    "agent_e_nominal",
    "agent_f_faulty",
    "agent_f_nominal",
    "get_scenario_a",
    "get_scenario_b",
    "get_scenario_c",
    "get_scenario_d",
    "get_scenario_e",
    "get_scenario_f",
]
