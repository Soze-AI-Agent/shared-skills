# Flutter Mobile Build — Buzz Android APK

Building the Block Buzz mobile app from Flutter source for Android (debug APK).

## Prerequisites

```bash
# Java (OpenJDK 21)
sudo apt-get install -y openjdk-21-jdk-headless

# Flutter (check pubspec.yaml for required Dart version)
# Buzz mobile/ requires Dart ^3.11.4 → Flutter 3.47.0+
FLUTTER_VERSION="3.47.0"
curl -sL "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" -o flutter.tar.xz
tar xf flutter.tar.xz -C /home/m/
export PATH="/home/m/flutter/bin:$PATH"

# Android SDK
ANDROID_SDK_ROOT="/home/m/Android/Sdk"
mkdir -p $ANDROID_SDK_ROOT/cmdline-tools
curl -sL https://dl.google.com/android/repository/commandlinetools-linux-12266719_latest.zip -o cmdline-tools.zip
unzip -q cmdline-tools.zip -d $ANDROID_SDK_ROOT/cmdline-tools
mv $ANDROID_SDK_ROOT/cmdline-tools/cmdline-tools $ANDROID_SDK_ROOT/cmdline-tools/latest

# Accept licenses FIRST (critical)
export ANDROID_HOME=$ANDROID_SDK_ROOT
export ANDROID_SDK_ROOT=$ANDROID_SDK_ROOT
yes | $ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager --licenses

# Install platform + build tools
$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager --sdk_root=$ANDROID_SDK_ROOT \
    "platforms;android-34" "build-tools;34.0.0" "platform-tools"

# Linux build deps (for flutter doctor)
sudo apt-get install -y cmake ninja-build pkg-config
```

## Build debug APK

```bash
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=/home/m/Android/Sdk
export PATH="/home/m/flutter/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/build-tools/34.0.0:$JAVA_HOME/bin:$PATH"

cd /home/m/buzz/mobile
flutter pub get
flutter build apk --debug
```

Output: `build/app/outputs/flutter-apk/app-debug.apk`

## Build release APK (Block-internal only)

```bash
flutter build apk --release
```

**Fails without Block signing credentials:**
```
FAILURE: Release builds require Android upload signing credentials.
Missing: BUZZ_ANDROID_UPLOAD_KEYSTORE_PASSWORD,
        BUZZ_ANDROID_UPLOAD_KEYSTORE_PATH,
        BUZZ_ANDROID_UPLOAD_KEY_ALIAS,
        BUZZ_ANDROID_UPLOAD_KEY_PASSWORD.
```

Block-internal builds use `BUZZ_ANDROID_RELEASE_SIGNING=external` for CI pipelines.
For self-hosted deployments, debug APK is sufficient for testing.

## Serve APK

```bash
mkdir -p /home/m/site/agent-info/buzz
cp build/app/outputs/flutter-apk/app-debug.apk /home/m/site/agent-info/buzz/buzz-debug.apk
# Served by existing agent-info http.server on port 80
# URL: http://primary.tail298a48.ts.net/buzz/buzz-debug.apk
```

## Pitfalls

| Symptom | Cause / Fix |
|---|---|
| `Because buzz requires SDK version ^3.11.4, version solving failed` | Flutter too old. Upgrade to 3.47.0+ (Dart 3.13.0+). Check `flutter --version`. |
| `License for package Android SDK Platform 34 not accepted` | Run `yes | sdkmanager --licenses` before any package install. Licenses persist in `$ANDROID_SDK_ROOT/licenses/`. |
| Gradle build hangs downloading NDK | Normal on first build — NDK r28c is ~1GB. Wait for completion. Check with `ps aux | grep java`. |
| `metrics exporter must build exactly once: Address already in use` | Port 9102 conflict from previous relay container. `docker stop buzz-prod-relay-1 && docker rm buzz-prod-relay-1`. |
| `buzz-cli` not found in relay container | The relay image (`ghcr.io/block/buzz:main`) does not include `buzz-cli`. Install separately or use Nostr client libraries. |
| Debug APK is 192MB | Normal — Flutter debug builds include symbols and are not optimized. Release APK would be ~50MB but requires signing. |
| Android Studio not installed warning | Not needed for headless APK builds. `flutter doctor` warns but build succeeds. |
| CMake 3.22.1 auto-downloaded during first build | Gradle downloads CMake automatically. No manual intervention needed. |
