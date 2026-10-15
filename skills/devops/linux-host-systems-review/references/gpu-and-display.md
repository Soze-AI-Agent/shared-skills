# GPU and display recovery on Linux hosts

## Symptom triage — is a GPU driver bound at all?

```bash
cat /proc/fb                                   # simpledrmdrmfb == EFI framebuffer, no GPU driver
readlink -f /sys/class/drm/card0/device/driver # .../simple-framebuffer confirms the same
ls /sys/class/drm/                             # only card0-Unknown-1 == no connectors enumerated
lsmod | grep -E '^nouveau|^nvidia|^i915|^amdgpu'   # empty == no KMS driver
lspci | grep -iE 'vga|3d|display'              # which GPU(s) actually exist
cat /proc/cmdline                              # 'nomodeset' blocks KMS for every driver
```

A firmware framebuffer keeps the console and a desktop compositor alive, so the machine
*looks* fine while having no modesetting and no physical outputs. On a laptop, an absent
Intel entry in `lspci` means there is no iGPU to fall back on — the discrete GPU is the
only path.

## Why a vendor driver cannot drive the card

NVIDIA's `-open` kernel modules cover Turing and newer only. Fermi (GF10x, e.g. Quadro
1000M / GF108) is not supported: the module loads, the probe fails
(`NVRM: ... is not supported by open ... nvidia.ko`,
`probe with driver nvidia failed with error -1`), and something re-triggers it in a loop.
The legacy branches that do support Fermi do not build against current kernels.

## The blacklist that hides the working driver

The vendor package drops `/lib/modprobe.d/<vendor>-graphics-drivers.conf` containing
`blacklist nouveau`, `blacklist lbm-nouveau`, `alias nouveau off`. So the package both
installs a driver that cannot drive the card AND disables the one that can.

```bash
grep -rn nouveau /etc/modprobe.d /lib/modprobe.d /run/modprobe.d
```

Repair shape: purge the unusable vendor stack (the `-kernel-common` / `-driver` packages
own that blacklist file), then rebuild and reboot:

```bash
apt-get -s purge <vendor packages>      # simulate FIRST, guard for collateral damage
update-initramfs -u -k all
depmod -a
```

Guard the simulation output with word-anchored patterns, or a prefix match on a meta package
name (`xserver-xorg` vs `xserver-xorg-video-nvidia`) aborts a safe purge:

```bash
for p in gnome-shell xserver-xorg-core gdm3 mutter; do
  echo "$SIM" | grep -qE "^(Purg|Remv) ${p}([ :]|$)" && echo "WOULD REMOVE $p"
done
```

Post-reboot verification, in this order: `lsmod | grep nouveau`, `cat /proc/fb`, connector
names under `/sys/class/drm/`. If the driver fails to bind, the machine falls back to
`simpledrm` — exactly the pre-existing state, so the attempt is not a one-way door.

## Clamshell operation on an external display or KVM

Both layers must be told to ignore the lid.

systemd-logind drop-in, `/etc/systemd/logind.conf.d/10-lid-ignore.conf`:

```ini
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
LidSwitchIgnoreInhibited=yes
```

GNOME, per user, needs the session bus:

```bash
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
gsettings set org.gnome.settings-daemon.plugins.power lid-close-ac-action nothing
gsettings set org.gnome.settings-daemon.plugins.power lid-close-battery-action nothing
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type nothing
gsettings set org.gnome.desktop.session idle-delay 0
gsettings set org.gnome.desktop.screensaver lock-enabled false
```

Verify with `systemd-analyze cat-config systemd/logind.conf`. **`systemctl show
systemd-logind -p HandleLidSwitch` prints nothing** — logind does not expose its
configuration as unit properties, so that command is a silent no-op that reads like a pass.

## Choosing the output once a real driver is bound

Connector names (`eDP-1`, `LVDS-1`, `VGA-1`, `HDMI-1`) exist only after a KMS driver binds.
On Wayland `xrandr` is not available; configure through the desktop's monitor settings
(GNOME persists to `~/.config/monitors.xml`) or the display D-Bus API. For a laptop run
closed on one external screen, the clean end state is the external output as primary with
the internal panel disabled — that also removes any lid-close rendering ambiguity.

## Reboot staging

A driver change only takes effect at boot, and rebooting the machine you are running on
ends your own session. Before scheduling it: have a oneshot systemd unit write the post-boot
state you need (framebuffer, bound driver, connector table, lid config, service and container
health) to a log path, run `loginctl enable-linger <user>` so user services return without a
login, then `shutdown -r +2` (cancel with `shutdown -c`) and hand the user the log path.
