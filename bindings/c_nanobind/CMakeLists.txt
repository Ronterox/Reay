cmake_minimum_required(VERSION 3.18)
project(aigame LANGUAGES C CXX)

if (NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Python 3.8 COMPONENTS Interpreter Development.Module REQUIRED)
execute_process(COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
                OUTPUT_VARIABLE nanobind_ROOT OUTPUT_STRIP_TRAILING_WHITESPACE)
find_package(nanobind CONFIG REQUIRED)

set(REAY ${CMAKE_CURRENT_SOURCE_DIR}/../..)
set(VCPKG ${REAY}/vcpkg_installed/x64-linux)

# game.c is compiled as C; only the glue is C++.
nanobind_add_module(aigame aigame.cpp ${REAY}/src/game.c)
target_include_directories(aigame PRIVATE ${REAY}/src ${VCPKG}/include)
target_link_libraries(aigame PRIVATE ${VCPKG}/lib/libraylib.a ${VCPKG}/lib/libglfw3.a m)

nanobind_add_stub(aigame_stub MODULE aigame OUTPUT aigame.pyi
                  PYTHON_PATH $<TARGET_FILE_DIR:aigame> DEPENDS aigame)
