# Auto-exported DLLs use the same non-profiled objects in both PGO phases.
function(ladybird_windows_filter_pgo directory)
    get_property(targets DIRECTORY "${directory}" PROPERTY BUILDSYSTEM_TARGETS)
    foreach(target IN LISTS targets)
        get_target_property(type "${target}" TYPE)
        get_target_property(auto_exports "${target}" WINDOWS_EXPORT_ALL_SYMBOLS)
        if("${target}" STREQUAL "LibCore" AND LADYBIRD_WINDOWS_PGO_PHASE STREQUAL "generate")
            target_compile_definitions(LibCore PRIVATE LADYBIRD_PGO_TRAINING=1)
        elseif("${target}" STREQUAL "LibCore")
            # The training build's shutdown changes this file's CFG.
            set_property(SOURCE "${directory}/ProcessWindows.cpp" TARGET_DIRECTORY LibCore
                APPEND PROPERTY COMPILE_OPTIONS "/clang:-fno-profile-use")
        endif()
        # The separate helper programs define the same ladybird_main symbol.
        if(LADYBIRD_WINDOWS_PGO_PHASE STREQUAL "use" AND type STREQUAL "EXECUTABLE"
            AND directory MATCHES "/Services(/|$)" AND EXISTS "${directory}/main.cpp")
            set_property(SOURCE "${directory}/main.cpp" TARGET_DIRECTORY "${target}"
                APPEND PROPERTY COMPILE_OPTIONS "/clang:-fno-profile-use")
        endif()
        if(type STREQUAL "SHARED_LIBRARY" AND auto_exports)
            target_compile_options("${target}" PRIVATE "/clang:-fno-profile-${LADYBIRD_WINDOWS_PGO_PHASE}")
        endif()
    endforeach()

    get_property(children DIRECTORY "${directory}" PROPERTY SUBDIRECTORIES)
    foreach(child IN LISTS children)
        ladybird_windows_filter_pgo("${child}")
    endforeach()
endfunction()

if(WIN32 AND LADYBIRD_WINDOWS_PGO_PHASE MATCHES "^(generate|use)$")
    cmake_language(DEFER CALL ladybird_windows_filter_pgo "${CMAKE_CURRENT_SOURCE_DIR}")
endif()