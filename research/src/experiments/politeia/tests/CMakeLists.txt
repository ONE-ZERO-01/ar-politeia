add_executable(test_cycle1_channels test_cycle1_channels.cpp)
target_link_libraries(test_cycle1_channels PRIVATE politeia_core)
add_test(NAME cycle1_channels COMMAND test_cycle1_channels)
set_tests_properties(cycle1_channels PROPERTIES
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)
