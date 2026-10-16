#!/usr/bin/env python3
"""Preserve the live P-state definitions across sleep/wake in SMCAMDProcessor.

Run from the local SMCAMDProcessor repository root. The patch snapshots the live
P-state MSRs before sleep and reapplies that exact table on the first work-loop
callback after wake. It deliberately does not change the P1/P0 scale formula.
"""
from pathlib import Path
import shutil
import sys


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"Expected exactly one {label} anchor; found {count}. No files were changed.")
    return text.replace(old, new, 1)


root = Path.cwd()
cpp_path = root / "AMDRyzenCPUPowerManagement" / "AMDRyzenCPUPowerManagement.cpp"
hpp_path = root / "AMDRyzenCPUPowerManagement" / "AMDRyzenCPUPowerManagement.hpp"

if not cpp_path.is_file() or not hpp_path.is_file():
    fail(
        "Run this script from the local SMCAMDProcessor repository root, "
        "where AMDRyzenCPUPowerManagement/ exists."
    )

cpp = cpp_path.read_text(encoding="utf-8")
hpp = hpp_path.read_text(encoding="utf-8")

# Idempotency guard: never insert the same patch twice.
if "PStateDef_beforeSleep" in cpp or "PStateDef_beforeSleep" in hpp or "restorePStateAfterWake" in cpp or "restorePStateAfterWake" in hpp:
    fail("Sleep/wake P-state restore fields already exist; no changes were made.")

# 1. Keep an independent snapshot. Do not reuse PStateDef_perCore as the snapshot,
#    because dumpPstate() on resume would otherwise overwrite the saved values.
hpp = replace_once(
    hpp,
    "    uint64_t PStateDef_perCore[8];\n",
    "    uint64_t PStateDef_perCore[8];\n"
    "    // Preserve the live P-state definitions across sleep; firmware may rewrite P1 on resume.\n"
    "    uint64_t PStateDef_beforeSleep[8] {};\n"
    "    bool PStateDef_beforeSleepValid = false;\n"
    "    bool restorePStateAfterWake = false;\n",
    "PStateDef_perCore field",
)

# 2. At sleep entry, stop periodic work, read the current table on the master CPU,
#    and copy the complete table before firmware/PM resume code can alter it.
cpp = replace_once(
    cpp,
    "        wentToSleep = true;\n        stopWorkLoop();\n",
    "        wentToSleep = true;\n"
    "        stopWorkLoop();\n"
    "\n"
    "        // Snapshot the live P-state table before sleep can restore firmware defaults.\n"
    "        mp_rendezvous_no_intrs([](void *obj) {\n"
    "            auto provider = static_cast<AMDRyzenCPUPowerManagement*>(obj);\n"
    "            uint32_t cpu_num = cpu_number();\n"
    "            if (pmRyzen_cpu_is_master(cpu_num))\n"
    "                provider->dumpPstate();\n"
    "        }, this);\n"
    "        memcpy(PStateDef_beforeSleep, PStateDef_perCore, sizeof(PStateDef_beforeSleep));\n"
    "        const uint64_t p1 = PStateDef_beforeSleep[1];\n"
    "        PStateDef_beforeSleepValid = (p1 & (1ULL << 63)) != 0 &&\n"
    "                                     ((p1 >> 8) & 0x3f) != 0 &&\n"
    "                                     (p1 & 0xff) != 0;\n"
    "        restorePStateAfterWake = PStateDef_beforeSleepValid;\n"
    "        if (!PStateDef_beforeSleepValid)\n"
    "            IOLog(\"AMDCPUSupport::setPowerState no valid P1 snapshot; wake restore skipped\\n\");\n",
    "sleep transition block",
)

# 3. Restore before the normal post-wake initialization calls dumpPstate(); this
#    prevents that read from replacing the desired values with firmware defaults.
cpp = replace_once(
    cpp,
    "        if(!provider->serviceInitialized){\n",
    "        if(!provider->serviceInitialized){\n"
    "            if (provider->restorePStateAfterWake && provider->PStateDef_beforeSleepValid) {\n"
    "                IOLog(\"AMDCPUSupport::startWorkLoop restoring P-state definitions after wake\\n\");\n"
    "                provider->writePstate(provider->PStateDef_beforeSleep);\n"
    "                provider->restorePStateAfterWake = false;\n"
    "                if (provider->PStateDef_perCore[1] == provider->PStateDef_beforeSleep[1]) {\n"
    "                    IOLog(\"AMDCPUSupport::startWorkLoop P1 restore verified\\n\");\n"
    "                } else {\n"
    "                    IOLog(\"AMDCPUSupport::startWorkLoop P1 restore mismatch: saved=%llx current=%llx\\n\",\n"
    "                          (unsigned long long)provider->PStateDef_beforeSleep[1],\n"
    "                          (unsigned long long)provider->PStateDef_perCore[1]);\n"
    "                }\n"
    "            }\n",
    "post-wake initialization block",
)

backups = {
    cpp_path: cpp_path.with_suffix(cpp_path.suffix + ".before-pstate-sleep-restore.bak"),
    hpp_path: hpp_path.with_suffix(hpp_path.suffix + ".before-pstate-sleep-restore.bak"),
}
for original, backup in backups.items():
    if backup.exists():
        fail(f"Backup already exists: {backup}. Move it aside before applying; no files were changed.")

# Verify staged content before touching the original files.
if cpp.count("PStateDef_beforeSleep") < 3 or cpp.count("restorePStateAfterWake") < 2:
    fail("Internal verification failed for the C++ changes; no files were changed.")
if hpp.count("PStateDef_beforeSleep") != 2 or hpp.count("restorePStateAfterWake") != 1:
    fail("Internal verification failed for the header changes; no files were changed.")

try:
    for original, backup in backups.items():
        shutil.copy2(original, backup)
    cpp_path.write_text(cpp, encoding="utf-8")
    hpp_path.write_text(hpp, encoding="utf-8")
except Exception as exc:
    # Roll back both files if a write fails part-way through.
    for original, backup in backups.items():
        if backup.exists():
            shutil.copy2(backup, original)
    fail(f"Could not write patch ({exc}); originals restored where backups existed.")

# Verify what was actually written.
written_cpp = cpp_path.read_text(encoding="utf-8")
written_hpp = hpp_path.read_text(encoding="utf-8")
if (
    "provider->writePstate(provider->PStateDef_beforeSleep);" not in written_cpp
    or "PStateDef_beforeSleep[8] {}" not in written_hpp
    or "P1 restore verified" not in written_cpp
):
    for original, backup in backups.items():
        shutil.copy2(backup, original)
    fail("Post-write verification failed; original source files were restored.")

print("Patch applied successfully.")
print("Changed:")
print("  - AMDRyzenCPUPowerManagement/AMDRyzenCPUPowerManagement.hpp")
print("  - AMDRyzenCPUPowerManagement/AMDRyzenCPUPowerManagement.cpp")
print("Behavior: snapshot actual P-state MSR definitions before sleep, restore them on the first work-loop callback after wake, and log whether P1 matched the snapshot.")
print("The existing P1/P0 scale expression in pmAMDRyzen.c is untouched.")
for original, backup in backups.items():
    print(f"Backup: {backup}")
print("Next: rebuild AMDRyzenCPUPowerManagement.kext, install it, then test sleep/wake.")
