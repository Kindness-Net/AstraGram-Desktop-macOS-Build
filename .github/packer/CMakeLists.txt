cmake_minimum_required(VERSION 3.16)
project(MacUpdatePacker LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Qt6 REQUIRED COMPONENTS Core)
find_package(OpenSSL REQUIRED)
find_package(ZLIB REQUIRED)
find_package(LibLZMA REQUIRED)

add_executable(Packer
    "${SOURCE_ROOT}/Telegram/SourceFiles/_other/packer.cpp"
    "${SOURCE_ROOT}/Telegram/SourceFiles/core/update_verify.cpp")
target_include_directories(Packer PRIVATE "${SOURCE_ROOT}/Telegram/SourceFiles")
target_compile_options(Packer PRIVATE "SHELL:-include memory" "SHELL:-include cstring")
target_link_libraries(Packer PRIVATE Qt6::Core OpenSSL::Crypto ZLIB::ZLIB LibLZMA::LibLZMA)
