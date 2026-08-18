# Politeia

**A Langevin-dynamics simulator for human civilization evolution.**

Politeia models every individual as a *particle* evolving on real-world terrain potential surfaces, driven by deterministic forces, dissipation, stochastic noise, and Poisson jumps. From purely symmetric micro-rules, macroscopic social phenomena — inequality, cultural boundaries, political hierarchies, and regime transitions — emerge spontaneously.

## Core Equation

```
m·q̈ = −∇V(q) − γ·q̇ + ξ(t) + J(t)
```

| Term | Physics | Social Analogy |
|------|---------|----------------|
| −∇V | Deterministic force | Terrain + interpersonal attraction/repulsion |
| −γ·q̇ | Dissipation | Institutional decay, knowledge loss |
| ξ(t) | Gaussian white noise | Everyday random events |
| J(t) | Poisson jumps | Technological breakthroughs, plagues |

## Agent State Vector

Each agent (person) carries five irreducible degrees of freedom:

```
Z_i(t) = (x_i, p_i, w_i, c⃗_i, ε_i)
```

| Symbol | Meaning | Dimension |
|--------|---------|-----------|
| **x** | Geographic position | 2D |
| **p** | Momentum | 2D |
| **w** | Wealth / resources | scalar |
| **c⃗** | Culture vector (knowledge + identity) | d-dim |
| **ε** | Energy utilization capability (technology level) | scalar |

## Key Emergent Phenomena

All results arise from **symmetric rules** — no social structure is pre-programmed.

| Phenomenon | Mechanism | Result |
|------------|-----------|--------|
| Inequality | Symmetric resource exchange | Gini: 0 → 0.89 |
| Cultural boundaries | Local assimilation + distant repulsion | Distinct cultural zones |
| Political hierarchy | Loyalty dynamics + conquest | Band → Tribe → State → Empire (H = 5–7) |
| Geographic determinism | Terrain-mediated interactions | Plains → centralization; Mountains → fragmentation |
| Mating systems | Biological asymmetry + wealth stratification | Monogamy → polygyny emergence |

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | C++20 |
| Build | CMake 3.20+ |
| Parallelism | MPI + OpenMP (optional) |
| Spatial decomposition | Morton Z-curve (SFC) |
| Testing | GoogleTest + CTest |
| Visualization | Python scripts |

## Project Structure

```
Politeia/
├── src/                    # C++ source code
│   ├── core/               # ParticleData (SoA), Config, constants
│   ├── domain/             # CellList, SFC decomposition, halo exchange
│   ├── force/              # Social forces, terrain, river field
│   ├── integrator/         # BBK Langevin integrator, RNG
│   ├── interaction/        # Resource exchange, culture, tech, loyalty
│   ├── population/         # Reproduction, mortality, plague, carrying capacity
│   ├── analysis/           # Order parameters, polity detection, perf monitor
│   ├── io/                 # CSV/checkpoint I/O, IC loader
│   └── main.cpp
├── tests/                  # GoogleTest suite (110+ tests)
├── scripts/                # Python: visualization, param scans, data tools
├── examples/               # Configuration files and initial conditions
├── docs/                   # Technical documentation
├── wiki/                   # LLM-assisted knowledge layer
├── research-proposal.md    # Scientific foundation (living document)
├── DEVELOPMENT_PLAN.md     # Engineering roadmap (31 phases, all complete)
└── CODE_GUIDE.md           # Module-by-module physics mapping
```

## Quick Start

### Build

```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . -j$(nproc)
```

### Run

```bash
# Single process
./politeia ../examples/minimal_1k.cfg

# MPI parallel
mpirun -np 4 ./politeia ../examples/minimal_1k.cfg

# Restart from checkpoint
mpirun -np 8 ./politeia --restart checkpoints/checkpoint_step_500000.bin
```

### Test

```bash
cd build && ctest --output-on-failure
```

## Development Status

**31 phases completed** (~44 weeks of development):

- Phases 0–3: Spatial dynamics, resource exchange, Langevin integration
- Phases 4–6: Culture vectors, population dynamics, Poisson jumps
- Phases 7–12: MPI parallelization, Morton SFC, OpenMP, real terrain
- Phases 13–16: Loyalty system, succession, polity detection
- Phases 17–26: Scaling tests, terrain experiments, configurable framework
- Phases 27–31: World map visualization, HYDE 3.3 calibration, checkpoint/restart, river corridors

## Vibe Research

This project is built through the **Vibe Research** paradigm — a human-AI collaborative workflow where the researcher provides creative direction and physical insight while AI agents handle code implementation, testing, and documentation. See `AGENTS.md` for the LLM Wiki knowledge management schema.

## References

- **Physical framework**: Langevin dynamics, Lennard-Jones potential, BBK integrator
- **Population data**: HYDE 3.3 (Klein Goldewijk et al., 2023)
- **Terrain data**: NOAA ETOPO1
- **Vibe Research**: Feng & Liu, "A Visionary Look at Vibe Researching" (arXiv:2604.00945, 2026)

## License

This project is for academic research purposes.
