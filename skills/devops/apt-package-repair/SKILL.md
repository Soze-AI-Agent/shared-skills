---
name: apt-package-repair
description: "Fix broken apt/dpkg package state on Ubuntu/Debian: unmet deps, half-installed packages, file conflicts, DKMS build failures, and stuck dpkg locks."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [apt, dpkg, package-management, ubuntu, debian, troubleshooting, system-repair]
    related_skills: [systematic-debugging]
---

# APT Package Repair

## Overview

Broken package state is common on long-lived Ubuntu/Debian systems. Symptoms: `apt-get check` returns non-zero, `apt` refuses to install/remove, dpkg errors during configure.

**Core principle:** Diagnose before force-fixing. `--force-depends` and `--force-remove-reinstreq` are last resorts, not first steps.

## When to Use

User says: "package system is broken", "apt is broken", "unmet dependencies", "dpkg error", "can't install anything", "E: Sub-process /usr/bin/dpkg returned an error code", "trying to overwrite ... which is also in package"

## Diagnostic Sequence

Run these in order, stop when you find the issue:

### 1. Check overall health

```bash
sudo apt-get check
```

Non-zero exit + unmet deps message → proceed.

### 2. Attempt auto-repair

```bash
sudo apt --fix-broken install -y
```

This is apt's built-in resolver. It often works for simple unmet deps.

### 3. If --fix-broken fails, read the error

Three common failure modes:

**A. File conflict** — dpkg says "trying to overwrite ... which is also in package"

Two packages own the same file. The newer/conflicting package was installed first, blocking the one apt needs.

Fix: Remove the conflicting package, then retry --fix-broken.

```bash
# Identify the conflicting package from the error
sudo dpkg --remove --force-depends <conflicting-package>
sudo apt --fix-broken install -y
```

**B. DKMS build failure** — "Bad return status for module build on kernel"

A kernel module (nvidia, zfs, virtualbox) failed to compile against the running kernel. The package is half-installed.

Two sub-cases:

- **Driver too old for kernel** (e.g. nvidia-390 on kernel 6.17): The driver version doesn't support this kernel. Purge it.

```bash
# List all packages from the broken family
dpkg -l | grep <driver-family>  # e.g. nvidia-390

# Purge the entire family
sudo apt purge -y <driver-metapackage> <dkms-package> <related-packages>

# Clean up orphans
sudo apt autoremove -y
```

- **Build environment issue** (missing kernel headers, compiler mismatch): Install the build deps and retry.

```bash
# Check what's missing
tail -50 /var/lib/dkms/<module>/<version>/build/make.log

# Install kernel headers
sudo apt install -y linux-headers-$(uname -r)

# Retry configure
sudo dpkg --configure -a
```

**C. dpkg lock held** — "Could not open lock file /var/lib/dpkg/lock-frontend"

Another apt/dpkg process is running. Wait or kill it.

```bash
# Find the holding process
sudo lsof /var/lib/dpkg/lock-frontend
sudo lsof /var/lib/dpkg/lock

# If stale (no process), remove lock
sudo rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock
sudo dpkg --configure -a
```

### 4. Verify fix

```bash
sudo apt-get check
```

Exit code 0 with no output = clean.

## Common Pitfalls

- **Purging the wrong package**: Check `dpkg -l | grep` output carefully. The `iU` status means "installed but unconfigured" — these are the broken ones. `ii` means fully installed and fine.
- **Removing critical system packages**: Never purge `apt`, `dpkg`, `libc6`, `systemd`, or `bash`. Check reverse-deps before force-removing anything.
- **DKMS failure on old hardware**: Fermi-era NVIDIA GPUs (Quadro 1000M, GeForce 400-500 series) only support driver 390, which won't build on kernels past ~6.2. The only fix is purging the proprietary driver and falling back to nouveau.
- **Autoremove removing too much**: After purging a driver family, `apt autoremove` may also remove unrelated packages that were pulled in as deps. Review the list before confirming with `-y`.
- **Crash report files blocking retry**: If dpkg says "Cannot create report: [Errno 17] File exists", remove the stale crash file: `sudo rm -f /var/crash/<package>.crash`

## Verification

After any repair:

```bash
sudo apt-get check && echo "CLEAN" || echo "STILL BROKEN"
sudo apt update 2>&1 | tail -3
```

If clean, also run `sudo apt upgrade --dry-run` to confirm no held-back packages.

## Reference

See `references/apt-repair-patterns.md` for session-specific error transcripts and reproduction recipes.
