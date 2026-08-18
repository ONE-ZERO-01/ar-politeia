add_library(politeia_core STATIC
    core/particle_data.cpp
    core/config.cpp
    domain/cell_list.cpp
    domain/decomposition.cpp
    domain/sfc_decomposition.cpp
    force/social_force.cpp
    force/terrain_force.cpp
    force/terrain_loader.cpp
    climate/climate_grid.cpp
    river/river_field.cpp
    integrator/langevin_integrator.cpp
    interaction/resource_exchange.cpp
    interaction/culture_dynamics.cpp
    interaction/tech_spread.cpp
    interaction/loyalty.cpp
    population/reproduction.cpp
    population/mortality.cpp
    population/plague.cpp
    population/carrying_capacity.cpp
    analysis/order_params.cpp
    analysis/network_analysis.cpp
    analysis/polity.cpp
    analysis/phase_transition.cpp
    analysis/perf_monitor.cpp
    io/csv_writer.cpp
    io/ic_loader.cpp
    io/checkpoint.cpp
)

target_include_directories(politeia_core
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}
)

target_compile_features(politeia_core PUBLIC cxx_std_20)

if(POLITEIA_USE_MPI)
    target_link_libraries(politeia_core PUBLIC MPI::MPI_CXX)
    target_compile_definitions(politeia_core PUBLIC POLITEIA_USE_MPI)
endif()

if(POLITEIA_USE_OPENMP)
    target_link_libraries(politeia_core PUBLIC OpenMP::OpenMP_CXX)
    target_compile_definitions(politeia_core PUBLIC POLITEIA_USE_OPENMP)
else()
    # Suppress warnings for #pragma omp in non-OpenMP builds
    target_compile_options(politeia_core PRIVATE -Wno-unknown-pragmas)
endif()

# --- Main executable ---
add_executable(politeia main.cpp)
target_link_libraries(politeia PRIVATE politeia_core)
