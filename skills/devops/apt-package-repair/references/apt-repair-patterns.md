# APT Repair Pattern Reference

## Pattern: DKMS Build Failure + File Conflict (nvidia-390 on kernel 6.17)

### Symptoms
```
apt-get check → unmet dependencies: nvidia-driver-390 Depends: libnvidia-cfg1-390
apt --fix-broken install → dpkg: error trying to overwrite '/usr/lib/x86_64-linux-gnu/libnvidia-cfg.so.1'
  which is also in package libnvidia-cfg1:amd64 610.43.02-1ubuntu1
```

### Root Cause
Two problems layered:
1. **File conflict**: `libnvidia-cfg1` (610 series, from a newer nvidia install) owns the same `.so` that `libnvidia-cfg1-390` needs. The 610 version was installed first, blocking the 390 version.
2. **DKMS build failure**: nvidia-390 (Fermi-era driver) can't compile against kernel 6.17 — missing headers in the source tree (`nv-misc.h`, `nv-linux.h` not found). This is a fundamental incompatibility: 390 series maxes out at kernel ~6.2.

### Hardware
Quadro 1000M (GF108GLM, Fermi architecture). Fermi GPUs only support up to nvidia-driver-390.

### Resolution Steps
1. Remove conflicting 610 package:
   ```bash
   sudo dpkg --remove --force-depends libnvidia-cfg1:amd64
   ```
2. Retry --fix-broken (fails on DKMS build — expected)
3. Purge entire nvidia-390 family:
   ```bash
   sudo apt purge -y nvidia-driver-390 nvidia-dkms-390 nvidia-kernel-common-390 \
     nvidia-kernel-source-390 nvidia-compute-utils-390 nvidia-utils-390 \
     xserver-xorg-video-nvidia-390 libnvidia-*390*
   ```
4. Clean up orphans:
   ```bash
   sudo apt autoremove -y
   ```
5. Verify: `sudo apt-get check` → exit 0

### Outcome
Falls back to nouveau open-source driver. No proprietary nvidia acceleration available for this GPU on kernel 6.17.

## Pattern: Simple Unmet Deps (no file conflict)

### Symptoms
```
apt-get check → unmet dependencies: <pkg> Depends: <dep> but it is not installed
```

### Resolution
```bash
sudo apt --fix-broken install -y
```
Works 90% of the time. Only fails when there's a file conflict or DKMS build error.

## Pattern: Stale dpkg Lock

### Symptoms
```
E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)
E: Unable to acquire the dpkg frontend lock
```

### Resolution
```bash
# Check for running apt/dpkg processes
ps aux | grep -E 'apt|dpkg'

# If no process but lock exists (stale)
sudo rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock
sudo dpkg --configure -a
```

## dpkg Status Codes Quick Reference

| Code | Meaning |
|------|---------|
| ii   | Installed + configured (OK) |
| iU   | Installed but unconfigured (broken) |
| rc   | Removed but config files remain |
| pn   | Never installed (purged) |
| iF   | Half-installed (failed during install) |
