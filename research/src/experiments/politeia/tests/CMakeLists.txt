add_executable(test_cycle1_channels test_cycle1_channels.cpp)
target_link_libraries(test_cycle1_channels PRIVATE politeia_core)
add_test(NAME cycle1_channels COMMAND test_cycle1_channels)
set_tests_properties(cycle1_channels PROPERTIES
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)

add_executable(test_exchange_kernel test_exchange_kernel.cpp)
target_link_libraries(test_exchange_kernel PRIVATE politeia_core)
add_test(NAME exchange_kernel COMMAND test_exchange_kernel)
set_tests_properties(exchange_kernel PROPERTIES
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)

add_executable(test_active_path test_active_path.cpp)
target_link_libraries(test_active_path PRIVATE politeia_core)
add_test(NAME active_path COMMAND test_active_path)
set_tests_properties(active_path PROPERTIES
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)

add_executable(test_module_invariants test_module_invariants.cpp)
target_link_libraries(test_module_invariants PRIVATE politeia_core)
add_test(NAME module_invariants COMMAND test_module_invariants)
set_tests_properties(module_invariants PROPERTIES
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)

add_executable(test_io_roundtrip test_io_roundtrip.cpp)
target_link_libraries(test_io_roundtrip PRIVATE politeia_core)
add_test(NAME io_roundtrip COMMAND test_io_roundtrip)
set_tests_properties(io_roundtrip PROPERTIES
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
