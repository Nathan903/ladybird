# Build Ladybird natively on Windows x64

These procedures build the Qt browser from Ladybird commit `3d6d3bb3be21b4ffc99f0d0defb97f09a99e57a2` with the Windows fixes in this checkout. Both use clang-cl, lld-link, the MSVC libraries, and the Windows SDK. Commands and troubleshooting notes were tested on Windows 10 x64 build 19044.

## Quick start with vcpkg

Install Git for Windows, Python, Rust for `x86_64-pc-windows-msvc`, and Visual Studio Build Tools with the C++ workload, Clang tools, and the Windows SDK. The tools used here were clang-cl 22.1.3, SDK 10.0.26100.0, Rust 1.98.0, CMake 4.4.5, and Ninja 1.13.2. Open an **x64 Native Tools Command Prompt for VS**. Put CMake, Ninja, Python, Git, and Cargo on `PATH`. Use a checkout path without spaces.

For a clean checkout at the commit above, save and apply `LadybirdWindowsSource.patch` from the checkout root with `git apply C:\path\to\LadybirdWindowsSource.patch`. Save `native-windows-helpers.patch` to `Meta\CMake\vcpkg` for the vcpkg step. This checkout already has both changes and patch files. [Ladybird source fixes](LadybirdWindowsSource.patch) · [vcpkg compatibility patch](../Meta/CMake/vcpkg/native-windows-helpers.patch)

From the Ladybird root, prepare the vcpkg version pinned in `vcpkg.json`. On this Windows 10 build, vcpkg's PowerShell 7.6.9 failed to start because of CET support. The `git apply` command selects the PowerShell 7.4.22 entry from the compatibility patch.

```bat
set "LADYBIRD_SRC=%CD%"
set "VCPKG_ROOT=%LOCALAPPDATA%\LadybirdBuild\vcpkg-stock"
set "PATH=%VCINSTALLDIR%Tools\Llvm\x64\bin;%PATH%"
clang-cl --version
git clone https://github.com/microsoft/vcpkg.git "%VCPKG_ROOT%"
git -C "%VCPKG_ROOT%" checkout 8f363bdc11359ede4bc51e5eb32a2617538049c8
git -C "%VCPKG_ROOT%" apply --include=scripts/vcpkg-tools.json "%LADYBIRD_SRC%\Meta\CMake\vcpkg\native-windows-helpers.patch"
call "%VCPKG_ROOT%\bootstrap-vcpkg.bat" -disableMetrics
```

Give the MSVC linker the path to Clang's runtime library. Qt's `moc` links against `clang_rt.builtins-x86_64.lib` on this toolchain. vcpkg provisions Qt and the build helpers, including MSYS2 and Strawberry Perl, into its own folders.

```bat
for /f "delims=" %I in ('clang-cl --print-resource-dir') do set "LLVM_RESOURCE_DIR=%I"
set _LINK_=/LIBPATH:"%LLVM_RESOURCE_DIR%\lib\windows"
set "VCPKG_KEEP_ENV_VARS=_LINK_"
set "VCPKG_MAX_CONCURRENCY=2"

cmake --preset Release -B Build\release-simple -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DLAGOM_LINK_POOL_SIZE=1 -DLADYBIRD_ENABLE_LTO=OFF
cmake --build Build\release-simple --target ladybird --parallel 2
```

The browser and its helper executables and DLLs are under `Build\release-simple\bin`. Keep the surrounding build tree for resources. For a launch check, run `Build\release-simple\bin\Ladybird.exe "https://en.wikipedia.org/wiki/Ladybird_(web_browser)"` from the checkout. Use the same developer prompt and vcpkg settings for incremental builds. On a configure failure, inspect `Build\release-simple\vcpkg-manifest-install.log` for the first failing port, then open its log under `%VCPKG_ROOT%\buildtrees`.

## Original build with Cygwin and an external Qt SDK

The original build used Cygwin helpers for FFmpeg, ICU, and libpng, and a prebuilt Qt 6.10.3 MSVC SDK. Its runtime contains Windows PE binaries with the MSVC ABI. The sections below record the toolchain and exact workaround for each component.

### Install the toolchain

Run the PowerShell blocks from the Ladybird checkout. Use paths without spaces for the checkout and the task directory because FFmpeg rejects spaces in its source path.

The build used Visual Studio 2026 Build Tools, MSVC 14.52, clang-cl 22.1.3, Windows SDK 10.0.26100.0, Git for Windows, Python 3.11.1 for the tool environment, and Python 3.14.5 for the Ladybird generators.

```powershell
$source = (Get-Location).Path
$state = Join-Path $env:LOCALAPPDATA 'LadybirdBuild'
New-Item -ItemType Directory -Path $state -Force | Out-Null

git rev-parse HEAD
curl.exe -fL -o "$state\vs_BuildTools.exe" https://aka.ms/vs/18/stable/vs_BuildTools.exe
$sig = Get-AuthenticodeSignature -LiteralPath "$state\vs_BuildTools.exe"
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
    throw 'Invalid Visual Studio installer signature'
}
$components = @(
    '--passive', '--norestart', '--wait',
    '--add', 'Microsoft.VisualStudio.Workload.VCTools',
    '--add', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
    '--add', 'Microsoft.VisualStudio.Component.Windows11SDK.26100',
    '--add', 'Microsoft.VisualStudio.Component.VC.Llvm.Clang',
    '--add', 'Microsoft.VisualStudio.Component.VC.CMake.Project'
)
& "$state\vs_BuildTools.exe" @components
```

Wait for Visual Studio setup to finish. `vswhere.exe` under `%ProgramFiles(x86)%\Microsoft Visual Studio\Installer` should list a complete and launchable Build Tools instance. The build used the standard version 18 installation path. [Visual Studio Build Tools components](https://learn.microsoft.com/en-us/visualstudio/install/workload-component-id-vs-build-tools?view=visualstudio)

Install CMake, Ninja, Meson, and the MSVC x64 Qt SDK. The Qt SDK supplies Qt Positioning and Qt GuiPrivate.

```powershell
py -3.11 -m venv "$state\python-tools"
& "$state\python-tools\Scripts\python.exe" -m pip install cmake==4.4.5 ninja==1.13.2 meson==1.12.1 aqtinstall==3.3.0
& "$state\python-tools\Scripts\aqt.exe" install-qt windows desktop 6.10.3 win64_msvc2022_64 -m qtpositioning -O "$state\Qt"

$env:RUSTUP_HOME = "$state\rustup"
$env:CARGO_HOME = "$state\cargo"
$rustupUrl = 'https://static.rust-lang.org/rustup/archive/1.29.3/x86_64-pc-windows-msvc/rustup-init.exe'
curl.exe -fL -o "$state\rustup-init.exe" $rustupUrl
$expected = (curl.exe -fsSL "$rustupUrl.sha256") -split '\s+' | Select-Object -First 1
if ((Get-FileHash "$state\rustup-init.exe" -Algorithm SHA256).Hash -ne $expected) {
    throw 'Rustup checksum mismatch'
}
& "$state\rustup-init.exe" -y --no-modify-path --profile minimal --default-host x86_64-pc-windows-msvc --default-toolchain 1.98.0
```

### Install the Cygwin build helpers

The build used Cygwin 3.6.12, GNU Make 4.4.1, and Automake 1.20. Install into a dedicated root so the following mount configuration applies only to these build helpers. [Cygwin setup](https://cygwin.com/install.html)

```powershell
$cygwinRoot = "$state\cygwin"
$cache = "$state\cygwin-packages"
New-Item -ItemType Directory -Path $cache -Force | Out-Null
curl.exe -fL -o "$state\setup-cygwin-x86_64.exe" https://cygwin.com/setup-x86_64.exe
if ((Get-AuthenticodeSignature "$state\setup-cygwin-x86_64.exe").Status -ne 'Valid') {
    throw 'Invalid Cygwin installer signature'
}
$packages = 'bash,make,autoconf,autoconf-archive,automake,binutils,libtool,perl,pkgconf,file,diffutils,findutils,patch,sed,gawk,grep'
$setupOptions = @(
    '--quiet-mode', '--no-admin', '--no-write-registry',
    '--no-shortcuts', '--no-startmenu', '--no-desktop',
    '--site', 'https://mirrors.kernel.org/sourceware/cygwin/', '--only-site',
    '--root', $cygwinRoot, '--local-package-dir', $cache, '--packages', $packages
)
& "$state\setup-cygwin-x86_64.exe" @setupOptions
```

After setup exits, give the Windows-side vcpkg scripts a physical path to `usr\bin`. The mount entry makes Cygwin accept the `/c/Users/...` paths produced by vcpkg's make helpers.

```powershell
if (-not (Test-Path -LiteralPath "$cygwinRoot\usr\bin")) {
    New-Item -ItemType Junction -Path "$cygwinRoot\usr\bin" -Target "$cygwinRoot\bin" | Out-Null
}
$fstab = "$cygwinRoot\etc\fstab"
$mounts = Get-Content -LiteralPath $fstab |
    Where-Object { $_ -notmatch '^\s*\S+\s+\S+\s+cygdrive\s+' }
$text = ($mounts -join [char]10) + [char]10 + 'none / cygdrive binary,posix=0,user 0 0' + [char]10
[IO.File]::WriteAllText($fstab, $text, [Text.Encoding]::ASCII)
& "$cygwinRoot\bin\cygpath.exe" -u 'C:\Windows'
```

Expect `/c/Windows`. For manual Cygwin diagnostics, put the Cygwin `bin` directory after MSVC's native tool directory and before `System32`. Windows includes a WSL `bash.exe` in `System32`, so check `where.exe bash` before running a diagnostic that invokes Bash by name.

### Initialize the x64 developer environment

The pinned vcpkg PowerShell 7.6.9 crashed on this Windows build with `Your Windows doesn't fully support CET`. PowerShell 7.4.22 x64 ran on the same installation. [PowerShell 7.4.22 release](https://github.com/PowerShell/PowerShell/releases/tag/v7.4.22)

```powershell
$psZip = "$state\PowerShell-7.4.22-win-x64.zip"
curl.exe -fL -o $psZip https://github.com/PowerShell/PowerShell/releases/download/v7.4.22/PowerShell-7.4.22-win-x64.zip
$psHash = '5f89f51860a1a3b07937945663afd7cbd44387361ff9985f5758939cb9bd6359'
if ((Get-FileHash -LiteralPath $psZip -Algorithm SHA256).Hash -ne $psHash) {
    throw 'PowerShell checksum mismatch'
}
Expand-Archive -LiteralPath $psZip -DestinationPath "$state\powershell-compatible"
& "$state\powershell-compatible\pwsh.exe" --version
```

Save the following script as `%LOCALAPPDATA%\LadybirdBuild\native-env.cmd`. Adjust the Git and Python paths for your machine. It initializes the Visual Studio x64 environment and uses a build-specific `PATH`.

```batch
@echo off
setlocal
set "STATE=%LOCALAPPDATA%\LadybirdBuild"
set "PATH=%STATE%\powershell-compatible;%STATE%\python-tools\Scripts;%STATE%\cargo\bin;%SystemRoot%\System32;%SystemRoot%;C:\Program Files\Git\cmd;C:\Python314;%ProgramFiles(x86)%\Microsoft Visual Studio\Installer"
set "RUSTUP_HOME=%STATE%\rustup"
set "CARGO_HOME=%STATE%\cargo"
call "%ProgramFiles(x86)%\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -no_logo -arch=x64 -host_arch=x64
if errorlevel 1 exit /b %errorlevel%
if exist "%VCINSTALLDIR%Tools\Llvm\x64\bin\clang-cl.exe" set "PATH=%VCINSTALLDIR%Tools\Llvm\x64\bin;%PATH%"
if "%~1"=="" exit /b 0
%*
exit /b %errorlevel%
```

```powershell
& "$state\native-env.cmd" clang-cl --version
& "$state\native-env.cmd" where.exe rc.exe
& "$state\native-env.cmd" rustc --version
```

Confirm `x86_64-pc-windows-msvc` in the clang-cl output and verify that the SDK's `rc.exe` is available.

### Build native pkgconf and Perl

vcpkg uses pkgconf to find libraries and Perl to run OpenSSL's build scripts. Compile both with the Visual Studio toolchain.

```powershell
git -c core.autocrlf=false clone --depth=1 --branch pkgconf-3.0.7 https://github.com/pkgconf/pkgconf.git "$state\pkgconf-src"
& "$state\native-env.cmd" meson setup "$state\pkgconf-build" "$state\pkgconf-src" --buildtype=release --default-library=static
& "$state\native-env.cmd" meson compile -C "$state\pkgconf-build" pkgconf:executable
& "$state\pkgconf-build\pkgconf.exe" --version

git -c core.autocrlf=false clone --depth=1 --branch v5.44.0 https://github.com/Perl/perl5.git "$state\perl-src"
$perlMakefile = "$state\perl-src\win32\Makefile"
$makefileText = [IO.File]::ReadAllText($perlMakefile)
$makefileText = $makefileText.Replace(
    'cd .. && miniperl -Ilib make_patchnum.pl && cd win32',
    'cd .. && .\miniperl.exe -Ilib make_patchnum.pl && cd win32')
[IO.File]::WriteAllText($perlMakefile, $makefileText, [Text.UTF8Encoding]::new($false))

Push-Location "$state\perl-src\win32"
try {
    & "$state\native-env.cmd" nmake /nologo CCTYPE=MSVC145 "INST_TOP=$state\perl"
    if ($LASTEXITCODE) { throw "Perl build failed with exit $LASTEXITCODE" }
    & "$state\native-env.cmd" nmake /nologo CCTYPE=MSVC145 "INST_TOP=$state\perl" install
    if ($LASTEXITCODE) { throw "Perl install failed with exit $LASTEXITCODE" }
} finally {
    Pop-Location
}
& "$state\perl\bin\perl.exe" -V:archname -V:version
```

The explicit `.\miniperl.exe` works when Windows command lookup excludes the current directory. Installed Perl should report `MSWin32-x64-multi-thread`.

### Prepare vcpkg and the dependency manifest

Use the pinned vcpkg baseline `8f363bdc11359ede4bc51e5eb32a2617538049c8`. A full clone includes the blobs used by Ladybird's version pins.

```powershell
$baseline = (Get-Content "$source\vcpkg.json" -Raw | ConvertFrom-Json).'builtin-baseline'
git -c core.autocrlf=false clone --no-checkout https://github.com/microsoft/vcpkg.git "$state\vcpkg"
git -C "$state\vcpkg" -c core.autocrlf=false checkout $baseline
& "$state\vcpkg\bootstrap-vcpkg.bat" -disableMetrics
git -C "$state\vcpkg" apply "$source\Meta\CMake\vcpkg\native-windows-helpers.patch"
Copy-Item -LiteralPath $psZip -Destination "$state\vcpkg\downloads\"
```

The patch pins PowerShell 7.4.22, selects the native Perl, and routes supported MSYS2 helper requests to the dedicated Cygwin installation. An unsupported request fails before vcpkg can download MSYS2. [Local vcpkg patch](../Meta/CMake/vcpkg/native-windows-helpers.patch)

Ensure `Meta/CMake/vcpkg/user-variables.cmake` contains this block so the built-in release triplet passes helper paths to ports.

```cmake
if(CMAKE_HOST_WIN32)
    list(APPEND VCPKG_ENV_PASSTHROUGH LADYBIRD_CYGWIN_ROOT PKG_CONFIG LADYBIRD_NATIVE_PERL)
endif()
```

Create a separate manifest that uses the downloaded Qt SDK. It omits the Windows Qt packages and keeps the other dependency declarations, pins, and overlays.

```powershell
$env:LADYBIRD_BUILD_STATE = $state
@'
import json
import os
from pathlib import Path

source = Path.cwd()
output = Path(os.environ["LADYBIRD_BUILD_STATE"]) / "windows-manifest"
output.mkdir(parents=True, exist_ok=True)
manifest = json.loads((source / "vcpkg.json").read_text(encoding="utf-8"))
omit = {("qtbase", "windows"), ("qtpositioning", "windows | freebsd")}
original = manifest["dependencies"]
manifest["dependencies"] = [
    entry for entry in original
    if not isinstance(entry, dict) or (entry.get("name"), entry.get("platform")) not in omit
]
if len(original) - len(manifest["dependencies"]) != 2:
    raise SystemExit("Unexpected Qt dependency declarations")
config = json.loads((source / "vcpkg-configuration.json").read_text(encoding="utf-8"))
config["overlay-ports"] = [(source / path).as_posix() for path in config["overlay-ports"]]
for name, data in (("vcpkg.json", manifest), ("vcpkg-configuration.json", config)):
    (output / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
'@ | py -3.11 -
```

The Ladybird checkout needs the source changes included with this guide.

- FFmpeg generates Bash scripts with LF endings. Its Cygwin build also creates a native Windows junction so clang-cl can read its out-of-tree sources. [FFmpeg port](../Meta/CMake/vcpkg/overlay-ports/ffmpeg/portfile.cmake) · [FFmpeg build script](../Meta/CMake/vcpkg/overlay-ports/ffmpeg/build.sh.in)
- ICU converts data paths to Windows paths before calling `pkgdata.exe`. [ICU patch](../Meta/CMake/vcpkg/overlay-ports/icu/cygwin-native-pkgdata-paths.patch)
- The Rust CMake rules append the Cargo pool to the global job pools. Without the change, setting the linker pool causes Ninja to report `unknown pool name 'link_pool'`. [Rust CMake rules](../Meta/CMake/rust_crate.cmake)

### Configure and compile Ladybird

Build the `ladybird` target in Release with the external Qt SDK. This configuration uses clang-cl's `/O2` optimizations and builds Skia with Direct3D support. It leaves link-time optimization off. The build used three parallel jobs and one linker job on the 16 GB laptop. The CMake configuration omits the test targets.

```powershell
$env:VCPKG_ROOT = "$state\vcpkg"
$env:VCPKG_MAX_CONCURRENCY = '3'
$env:LADYBIRD_CYGWIN_ROOT = "$state\cygwin"
$env:PKG_CONFIG = "$state\pkgconf-build\pkgconf.exe"
$env:LADYBIRD_NATIVE_PERL = "$state\perl\bin\perl.exe"
$qt = "$state\Qt\6.10.3\msvc2022_64"
$build = "$source\Build\release"
$configure = @(
    '--preset', 'Release', '-B', $build,
    '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_TESTING=OFF', '-DLAGOM_LINK_POOL_SIZE=1',
    "-DCMAKE_PREFIX_PATH=$qt", "-DPKG_CONFIG_EXECUTABLE=$env:PKG_CONFIG",
    "-DVCPKG_MANIFEST_DIR=$state\windows-manifest",
    '-DVCPKG_TARGET_TRIPLET=x64-windows', '-DVCPKG_HOST_TRIPLET=x64-windows'
)
& "$state\native-env.cmd" cmake @configure
if ($LASTEXITCODE) { throw "CMake configuration failed with exit $LASTEXITCODE" }

& "$state\native-env.cmd" cmake --build $build --target ladybird --parallel 3
if ($LASTEXITCODE) { throw "Ladybird build failed with exit $LASTEXITCODE" }
```

CMake initially builds the dependencies with vcpkg. For a configure failure, look in `Build\release\vcpkg-manifest-install.log` for the first failing port. Its detailed log is under `%LOCALAPPDATA%\LadybirdBuild\vcpkg\buildtrees\<port>`. Reuse `Build\release` after correcting a failure to retain installed dependencies and compiled objects.

## Verify and launch

The browser target and its helper targets use `Build\release\bin`. The Qt deployment step runs after linking. Keep the resources in the build tree when running from that directory.

```powershell
$bin = Join-Path $build 'bin'
$browser = Join-Path $bin 'Ladybird.exe'
& "$state\native-env.cmd" dumpbin /headers $browser | Select-String 'machine \(x64\)'
& "$state\native-env.cmd" dumpbin /dependents $browser
Start-Process -FilePath $browser -WorkingDirectory $bin -ArgumentList 'https://en.wikipedia.org/wiki/Ladybird_(web_browser)'
```

The first graphical launch opens a Welcome tab before the requested page. Select the Wikipedia tab to view the article. To verify rendering directly, give the browser a short, absolute profile path and use screenshot mode.

```powershell
$profile = Join-Path $env:LOCALAPPDATA 'LBWikiProbe'
$image = Join-Path $state 'wikipedia.png'
$url = 'https://en.wikipedia.org/wiki/Ladybird_(web_browser)'
& $browser --headless=screenshot --profile-path $profile --screenshot-delay=4 --screenshot-path $image $url
```

The preserved build on the laptop is `C:\src\ladybird\Build\release\bin\Ladybird.exe`. Its helper executables, Qt and engine DLLs, and platform plugins are in the same `bin` tree. The original build opened a Windows window titled `Ladybird (web browser) - Wikipedia - Ladybird`, exported the article text, and saved a rendered screenshot. An inspection of the 109 executable and DLL files in the runtime confirmed AMD64 PE headers and found no Cygwin, MSYS2, or MinGW runtime imports. The VC redistributable installer was outside that inspection.

The quick-start build used vcpkg's Qt 6.11.3 and passed the same graphical Wikipedia launch. All 110 executable and DLL files in its runtime audit had AMD64 PE headers. A second invocation with `--new-window` opened `Example Domain` in the running instance and returned exit code 0. The first instance also returned exit code 0 when its windows closed. Headless text and screenshot runs with `--temporary-profile` completed. Windows logged `unlink: Permission denied (errno=13)` when it tried to remove their temporary profile directories. The original build showed a `0xc0000005` access violation at shutdown and had a longer temporary profile path. The source patch includes the profile and shutdown fixes used by the quick-start build.

On this Windows 10 build, the compositor logged `80004002` for the DirectComposition texture interface. The browser still opened and rendered the test pages. The benchmarks reflect the presentation path supported by this machine.

## Build with ThinLTO

Run these commands from the same x64 developer prompt as the quick start, after vcpkg has installed the dependencies. The separate build directory shares the stock build's installed dependencies. The Windows source fix uses ordinary COFF object files for DLLs that rely on CMake's automatic export list. LibWeb and LibJS retain ThinLTO.

```bat
set "LTO_LINK_FLAGS=/machine:x64 /OPT:LLDLTOJOBS=2"
cmake --preset Release -B Build\release-lto-stock ^
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DLAGOM_LINK_POOL_SIZE=1 -DLADYBIRD_ENABLE_LTO=ON ^
  -DVCPKG_MANIFEST_INSTALL=OFF "-DVCPKG_INSTALLED_DIR=%LADYBIRD_SRC%\Build\release-simple\vcpkg_installed" ^
  "-DCMAKE_EXE_LINKER_FLAGS=%LTO_LINK_FLAGS%" "-DCMAKE_SHARED_LINKER_FLAGS=%LTO_LINK_FLAGS%" ^
  "-DCMAKE_MODULE_LINKER_FLAGS=%LTO_LINK_FLAGS%"
cmake --build Build\release-lto-stock --target ladybird --parallel 2
```

## Compare speed and memory

The Ladybird Web Benchmarks checkout used for comparison is `4c18fcb1a97e7dd888583a6928a7f6996eb42a1e`. The Windows runner patch uses IPv4 loopback and closes only the browser instance started for that benchmark. It samples private committed bytes for the browser process and its children every half second. Each run uses a fresh test profile. [Ladybird Web Benchmarks](https://github.com/LadybirdBrowser/web-benchmarks) · [Windows benchmark patch](LadybirdWindowsBenchmark.patch)

```powershell
$bench = Join-Path $state 'web-benchmarks'
git clone https://github.com/LadybirdBrowser/web-benchmarks.git $bench
git -C $bench checkout 4c18fcb1a97e7dd888583a6928a7f6996eb42a1e
git -C $bench apply "$source\Documentation\LadybirdWindowsBenchmark.patch"
$py = Join-Path $state 'python-tools\Scripts\python.exe'
& $py -m pip install -r "$bench\requirements.txt" psutil==7.2.2

$exe = "$source\Build\release\bin\Ladybird.exe"
$runner = Join-Path $bench 'run.py'
$result = Join-Path $state 'baseline-speedometer.json'
$log = Join-Path $state 'baseline-speedometer.log'
$env:LADYBIRD_BENCH_MEMORY_JSON = Join-Path $state 'baseline-speedometer-memory.json'
$env:PYTHONUTF8 = '1'
cmd.exe /d /c "$py -u $runner --executable $exe --benchmarks Speedometer3 --iterations 3 --show-window --timeout 90 --output $result > $log 2>&1"
```

Repeat with each candidate executable and distinct JSON and log paths. Run comparisons with compilation stopped and under the same power and browser window conditions. Compare the Speedometer scores alongside the running-phase private-memory samples. The memory figure measures private committed bytes, including paged memory.

### Initial results on this laptop

The original Release and the stock-vcpkg Release each ran Speedometer 3 in two independent browser launches with three iterations per launch. The order was reversed for the second pass. These results were collected before the stock browser's shutdown fix. Median memory is the mean of the two running-phase medians. Peak is the largest sample in either launch.

| Build and allocator setting | Mean score | Median private MiB | Peak private MiB |
| --- | ---: | ---: | ---: |
| Original Release | 6.247 | 1,331.1 | 1,431.7 |
| Stock-vcpkg Release | 6.254 | 1,343.8 | 1,421.8 |
| Stock-vcpkg Release with `MIMALLOC_PURGE_DELAY=0` | 6.186 | 1,310.5 | 1,385.9 |

The difference between the two default configurations was smaller than the variation between launches. Immediate purging in the stock build reduced the median by 33 MiB in this pass. A second pass with the rebuilt stock browser reversed that result, with 1,330.7 MiB for the default and 1,339.1 MiB for immediate purging. Keep the allocator default for comparisons. The raw data are in `%LOCALAPPDATA%\LadybirdBuild\benchmark-runs\20261124-065105` and `20261124-075805`.

### ThinLTO results

The ThinLTO browser and the rebuilt stock browser passed the Windows launch, forwarding, and shutdown checks. All 110 executable and DLL files in the ThinLTO runtime audit had AMD64 PE headers. Both builds use the same vcpkg dependencies and default allocator settings. Each benchmark ran for three iterations in two independent browser launches per build.

| Build | Speedometer 3 score | Speedometer median private MiB | StyleBench score | StyleBench median private MiB |
| --- | ---: | ---: | ---: | ---: |
| Original Release | 6.343 | 1,329.2 | 119.750 | 1,190.5 |
| Stock-vcpkg Release | 6.354 | 1,335.8 | 119.031 | 1,188.1 |
| Selective ThinLTO | 6.593 | 1,360.0 | 119.232 | 1,184.8 |

ThinLTO raised the mean Speedometer score by 3.8% and its median private memory by 24 MiB compared with stock. StyleBench scores were close, and ThinLTO used 3 MiB less median private memory in that workload. The benchmark JSON and process samples are in `%LOCALAPPDATA%\LadybirdBuild\benchmark-runs\20261124-083929`.

## Reproduce the profile-guided build

Use the same x64 developer environment, the stock-vcpkg dependencies, and the benchmark checkout above. Profile-guided optimization (PGO) compiles the browser twice in `Build\release-pgo-stock`. The first pass collects profiles. The second uses the profiles to compile the browser you run. Save the training script beside the `web-benchmarks` checkout under `%LOCALAPPDATA%\LadybirdBuild`. [CMake PGO hook](../Meta/CMake/windows_pgo.cmake) · [Windows training script](LadybirdWindowsPGOTraining.py)

The CMake hook leaves DLLs that use automatic exports uninstrumented because profiling counter names can break the generated export list. During training, LibCore uses the CRT exit path so the renderer can write its profiles. The final build uses the regular exit path. It compiles `ProcessWindows.cpp` without profile input because its control flow differs from training, and the helper entry points without profile input because separate executables share the `ladybird_main` symbol.

Enter PowerShell from the x64 developer prompt and define the two build phases.

```powershell
$root = (Get-Location).Path
$state = Join-Path $env:LOCALAPPDATA 'LadybirdBuild'
$build = Join-Path $root 'Build\release-pgo-stock'
$installed = Join-Path $root 'Build\release-simple\vcpkg_installed'
$hook = Join-Path $root 'Meta\CMake\windows_pgo.cmake'
$profile = (Join-Path $state 'ladybird-pgo.profdata').Replace('\', '/')
$clangResource = (clang-cl --print-resource-dir).Trim().Replace('\', '/')
$llvm = Split-Path (Get-Command clang-cl.exe).Source
$runtime = "$clangResource/lib/windows/clang_rt.profile-x86_64.lib"

function Invoke-LadybirdPgoBuild([ValidateSet('generate', 'use')] [string] $Phase) {
    $linkerFlags = '/machine:x64 /OPT:LLDLTOJOBS=2'
    $profileFlag = "/clang:-fprofile-use=$profile"
    if ($Phase -eq 'generate') {
        $profileFlag = '/clang:-fprofile-generate'
        $linkerFlags += ' /DEFAULTLIB:"' + $runtime + '"'
    }
    $cache = Join-Path $state "pgo-$Phase-flags.cmake"
    $flags = @"
set(CMAKE_C_FLAGS_RELEASE [=[/O2 /Ob2 /DNDEBUG $profileFlag]=] CACHE STRING "" FORCE)
set(CMAKE_CXX_FLAGS_RELEASE [=[/O2 /Ob2 /DNDEBUG $profileFlag]=] CACHE STRING "" FORCE)
set(CMAKE_EXE_LINKER_FLAGS [=[$linkerFlags]=] CACHE STRING "" FORCE)
set(CMAKE_SHARED_LINKER_FLAGS [=[$linkerFlags]=] CACHE STRING "" FORCE)
set(CMAKE_MODULE_LINKER_FLAGS [=[$linkerFlags]=] CACHE STRING "" FORCE)
"@
    [IO.File]::WriteAllText($cache, $flags)
    $configure = @(
        '-C', $cache, '--preset', 'Release', '-B', $build,
        '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_TESTING=OFF', '-DLAGOM_LINK_POOL_SIZE=1',
        '-DLADYBIRD_ENABLE_LTO=ON', '-DVCPKG_MANIFEST_INSTALL=OFF',
        "-DVCPKG_INSTALLED_DIR=$installed", "-DCMAKE_PROJECT_ladybird_INCLUDE=$hook",
        "-DLADYBIRD_WINDOWS_PGO_PHASE=$Phase"
    )
    cmake @configure
    if ($LASTEXITCODE) { throw "PGO $Phase configuration failed with exit $LASTEXITCODE" }
    cmake --build $build --target ladybird --parallel 2
    if ($LASTEXITCODE) { throw "PGO $Phase build failed with exit $LASTEXITCODE" }
}
```

Build and train. The script opens Wikipedia in headless text mode, then runs five Speedometer 2 iterations in a visible window. It stores raw data by process and module, merges it with `llvm-profdata`, and checks for executed Web and JS functions before saving the profile.

```powershell
$trainer = Join-Path $state 'LadybirdWindowsPGOTraining.py'
Copy-Item .\Documentation\LadybirdWindowsPGOTraining.py $trainer
$py = Join-Path $state 'python-tools\Scripts\python.exe'
$browser = Join-Path $build 'bin\Ladybird.exe'
$generatorProfiles = Join-Path $state 'pgo-build-raw'
New-Item -ItemType Directory -Path $generatorProfiles -Force | Out-Null
$env:LLVM_PROFILE_FILE = Join-Path $generatorProfiles 'build-%p-%m.profraw'
try {
    Invoke-LadybirdPgoBuild generate
} finally {
    Remove-Item Env:LLVM_PROFILE_FILE
}
& $py -u $trainer $browser (Join-Path $llvm 'llvm-profdata.exe')
if ($LASTEXITCODE) { throw "PGO training failed with exit $LASTEXITCODE" }
Invoke-LadybirdPgoBuild use
```

The renderer training pass on this laptop merged 170 profiles with 92,714 function records. Executed functions included 13,274 Web and 4,774 JS symbol matches. The training files are in `%LOCALAPPDATA%\LadybirdBuild\pgo-train-20261124-101749`. Use Speedometer 3 and StyleBench to compare builds on workloads outside that training run.

### Final performance comparison

The PGO build was the fastest on both tests in the final comparison. Its GUI opened Wikipedia, forwarded a second launch, and closed with exit code 0. All 110 runtime executables and DLLs passed the AMD64 PE audit. The executable is at `C:\src\ladybird\Build\release-pgo-stock\bin\Ladybird.exe`, with its DLLs and helpers in the same `bin` directory.

| Build | Speedometer 3 score | Speedometer median private MiB | StyleBench score | StyleBench median private MiB |
| --- | ---: | ---: | ---: | ---: |
| Stock-vcpkg Release | 6.227 | 1,353.1 | 114.100 | 1,217.6 |
| Selective ThinLTO | 6.488 | 1,330.6 | 115.514 | 1,211.1 |
| Selective ThinLTO with PGO | 7.020 | 1,365.5 | 117.583 | 1,205.5 |

PGO scored 12.7% higher than stock on Speedometer 3 and 3.1% higher on StyleBench. ThinLTO had the lowest median private memory on Speedometer 3 in this pass. PGO had the lowest median on StyleBench. Each score is the mean from two browser launches with three iterations each. The run order was reversed for the second launch of each build. The benchmark JSON and process samples are in `%LOCALAPPDATA%\LadybirdBuild\benchmark-runs\20261124-112748`.
