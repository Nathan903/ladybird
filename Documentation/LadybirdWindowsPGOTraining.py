import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

state = Path(__file__).resolve().parent
browser = Path(sys.argv[1]).resolve()
llvm = Path(sys.argv[2]).resolve()
profdata = state / "ladybird-pgo.profdata"
raw = state / ("pgo-train-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
raw.mkdir()
env = {**os.environ, "LLVM_PROFILE_FILE": str(raw / "ladybird-%p-%m.profraw"), "PYTHONUTF8": "1"}

def run(command, name, timeout):
    print(f"Running {name}", flush=True)
    with (raw / f"{name}.log").open("wb") as log:
        status = subprocess.run(command, cwd=browser.parent, env=env, stdout=log, stderr=subprocess.STDOUT,
                                timeout=timeout)
    print(f"{name} exited {status.returncode}", flush=True)
    return status.returncode

article = "https://en.wikipedia.org/wiki/Ladybird_(web_browser)"
run([browser, "--headless=text", "--temporary-profile", article], "wikipedia-text", 50)
benchmark = state / "web-benchmarks" / "run.py"
scores = raw / "training-speedometer2.json"
score_status = run([sys.executable, "-u", benchmark, "--executable", browser, "--benchmarks", "Speedometer2",
                    "--iterations", "5", "--show-window", "--timeout", "90", "--output", scores],
                   "speedometer2", 600)
if score_status or not scores.is_file():
    raise RuntimeError(f"Speedometer 2 training did not complete. See {raw}")
time.sleep(5)

data = sorted(path for path in raw.glob("*.profraw") if path.stat().st_size)
if len(data) < 2:
    raise RuntimeError(f"Expected raw profiles from multiple process modules. See {raw}")
inputs = raw / "inputs.txt"
inputs.write_text("\n".join(str(path) for path in data) + "\n", encoding="utf-8")
temporary_profile = raw / "merged.profdata"
subprocess.run([llvm, "merge", f"--input-files={inputs}", f"--output={temporary_profile}"], check=True)
subprocess.run([llvm, "show", temporary_profile], check=True)
covered = subprocess.check_output([llvm, "show", "--covered", temporary_profile],
                                  text=True, encoding="utf-8", errors="replace").splitlines()
for namespace in ("Web", "JS"):
    matching = [name for name in covered if f"@{namespace}@@" in name]
    (raw / f"covered-{namespace.lower()}-functions.txt").write_text("\n".join(matching) + "\n",
                                                                  encoding="utf-8")
    print(f"Covered {namespace} functions: {len(matching)}", flush=True)
    if not matching:
        raise RuntimeError(f"The renderer did not provide coverage for {namespace}. See {raw}")
temporary_profile.replace(profdata)
print(f"Merged {len(data)} profiles into {profdata}", flush=True)
print(f"Raw profiles and training coverage: {raw}", flush=True)
