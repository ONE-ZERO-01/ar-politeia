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
