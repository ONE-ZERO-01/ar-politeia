cmake_minimum_required(VERSION 3.20)
project(Politeia
    VERSION 0.1.0
    LANGUAGES CXX
    DESCRIPTION "Minimal Langevin resource-landscape simulator for AR-Politeia Cycle 1"
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# --- Options ---
option(POLITEIA_USE_MPI "Enable MPI parallelization" OFF)
option(POLITEIA_USE_OPENMP "Enable OpenMP thread-level parallelism" OFF)
option(POLITEIA_BUILD_TESTS "Build unit tests" OFF)

# --- Compiler warnings ---
add_compile_options(
    -Wall -Wextra -Wpedantic
    -Wno-unused-parameter
)

if(CMAKE_BUILD_TYPE STREQUAL "Release")
    add_compile_options(-O3 -march=native -DNDEBUG)
elseif(CMAKE_BUILD_TYPE STREQUAL "Debug")
    add_compile_options(-g -O0 -fsanitize=address,undefined)
    add_link_options(-fsanitize=address,undefined)
    # MPI libraries (OpenMPI/PMIx) have known internal leaks that trigger
    # LeakSanitizer false positives; suppress them in Debug builds.
    if(POLITEIA_USE_MPI)
        add_compile_definitions(LSAN_OPTIONS="suppressions=${CMAKE_SOURCE_DIR}/lsan_suppressions.txt")
    endif()
endif()

# --- MPI (optional) ---
if(POLITEIA_USE_MPI)
    find_package(MPI REQUIRED COMPONENTS CXX)
    message(STATUS "MPI enabled: ${MPI_CXX_COMPILER}")
endif()

# --- OpenMP (optional) ---
if(POLITEIA_USE_OPENMP)
    find_package(OpenMP REQUIRED COMPONENTS CXX)
    message(STATUS "OpenMP enabled: ${OpenMP_CXX_FLAGS}")
endif()

# --- Source library ---
add_subdirectory(src)

# --- Tests (optional; tests/ lives on HPC checkout) ---
if(POLITEIA_BUILD_TESTS)
    if(EXISTS "${CMAKE_SOURCE_DIR}/tests/CMakeLists.txt")
        enable_testing()
        add_subdirectory(tests)
    else()
        message(STATUS "POLITEIA_BUILD_TESTS=ON but tests/ not found; skipping")
    endif()
endif()
