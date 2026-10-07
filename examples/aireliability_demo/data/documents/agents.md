# Autonomous AI Agent Reliability

Phase 40 agent reliability audits multi-step autonomous AI agents as continuous execution trajectories.
Successful final answers are prevented from masking intermediate errors such as tool failures or runaway loops.

## Trajectory Lifecycle Stages
- **Task Understanding & Decomposition**: Evaluates whether tasks are cleanly broken into executable subtasks with explicit dependencies.
- **Tool Selection & Execution**: Audits tool choice, argument validity, and handling of tool outputs.
- **Observation & State Management**: Tracks state updates, memory integrity, and prevents state corruption.
- **Loop & Runaway Detection**: Identifies infinite retry loops, repeating state cycles, and runaway execution limits.
- **Goal Verification**: Empirically verifies whether all success criteria were satisfied before concluding.
