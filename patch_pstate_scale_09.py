#!/usr/bin/env python3
"""Change SMCAMDProcessor's kernel-initialized P1/P0 target ratio from 0.80 to 0.90.

Run from the local SMCAMDProcessor repository root, beside SMCAMDProcessor.xcodeproj.
The script edits only AMDRyzenCPUPowerManagement/pmAMDRyzen.c and creates a backup.
"""
from pathlib import Path
import shutil
import sys


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


root = Path.cwd()
source_path = root / "AMDRyzenCPUPowerManagement" / "pmAMDRyzen.c"
if not source_path.is_file():
    fail(
        "Run this script from the local SMCAMDProcessor repository root; "
        "AMDRyzenCPUPowerManagement/pmAMDRyzen.c was not found."
    )

source = source_path.read_text(encoding="utf-8")
old = "    uint64_t p1fid = (uint64_t)((p0spd * 0.80F) / 200.0F * (float)((p1 >> 8) & 0x1f));"
new = (
    "    // Target P1 at 90% of P0. Integer FID quantization can make the resulting ratio slightly lower.\n"
    "    uint64_t p1fid = (uint64_t)((p0spd * 0.90F) / 200.0F * (float)((p1 >> 8) & 0x1f));"
)

if old not in source:
    if "p0spd * 0.90F" in source:
        fail("The P1/P0 target ratio appears to be already set to 0.90; no changes were made.")
    fail("Could not find the expected original 0.80 P1 scale expression. File left unchanged.")
if source.count(old) != 1:
    fail(f"Expected the original P1 scale expression exactly once; found {source.count(old)} occurrences. File left unchanged.")

backup_path = source_path.with_suffix(source_path.suffix + ".before-pstate-scale-090.bak")
if backup_path.exists():
    fail(f"Backup already exists: {backup_path}. Move it aside before reapplying; file left unchanged.")

shutil.copy2(source_path, backup_path)
source_path.write_text(source.replace(old, new, 1), encoding="utf-8")

# Verify the expected change and ensure the old target expression is gone.
updated = source_path.read_text(encoding="utf-8")
if updated.count("p0spd * 0.90F") != 1 or "p0spd * 0.80F" in updated:
    shutil.copy2(backup_path, source_path)
    fail("Post-write verification failed; original source restored from backup.")

print("Patch applied successfully.")
print("Changed: pmRyzen_init_PState() P1/P0 target ratio 0.80 -> 0.90")
print(f"Backup: {backup_path}")
print("Next: rebuild AMDRyzenCPUPowerManagement.kext and test by loading it/restarting.")
print("Note: the calculated P1 may be slightly below exactly 90% because CpuFid is an integer.")
