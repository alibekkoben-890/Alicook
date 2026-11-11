#!/usr/bin/env bash
# Checks an APK for things that commonly trigger Play Protect warnings
# or block installs. Fails the build if any check does not pass.
set -euo pipefail
APK="$1"
EXPECTED_CERT="f5f72d4211957b520ce9b3310b6ad7613bd9ecf5152081f3f416a0228fd486e0"
MIN_TARGET_SDK=35
ALLOWED_PERMISSIONS="android.permission.INTERNET android.permission.VIBRATE"

fail() { echo "::error::$1"; exit 1; }
ok() { echo "OK: $1"; }

test -s "$APK" || fail "APK not found: $APK"
echo "APK size: $(stat -c%s "$APK") bytes"

BT="$ANDROID_HOME/build-tools/$(ls -1 "$ANDROID_HOME/build-tools" | sort -V | tail -1)"
"$BT/apksigner" verify --verbose --print-certs "$APK" > "$RUNNER_TEMP/certs.txt" || fail "APK signature is invalid"
cat "$RUNNER_TEMP/certs.txt"
"$BT/aapt" dump badging "$APK" > "$RUNNER_TEMP/badging.txt"
head -3 "$RUNNER_TEMP/badging.txt"

# 1. Signed with the permanent AliCook key
grep -q "certificate SHA-256 digest: $EXPECTED_CERT" "$RUNNER_TEMP/certs.txt" \
  || fail "APK is not signed with the permanent AliCook key"
ok "signed with the permanent AliCook key"

# 2. Modern signature scheme
grep -q "Verified using v2 scheme (APK Signature Scheme v2): true" "$RUNNER_TEMP/certs.txt" \
  || fail "APK is not signed with APK Signature Scheme v2"
ok "APK Signature Scheme v2"

# 3. Not a debug build
if grep -q "application-debuggable" "$RUNNER_TEMP/badging.txt"; then
  fail "APK is debuggable (debug build); Play Protect treats these more strictly"
fi
ok "not debuggable"

# 4. Current targetSdk
TARGET=$(sed -n "s/^targetSdkVersion:'\([0-9]*\)'.*/\1/p" "$RUNNER_TEMP/badging.txt")
[ -n "$TARGET" ] && [ "$TARGET" -ge "$MIN_TARGET_SDK" ] \
  || fail "targetSdk is ${TARGET:-unknown}, need at least $MIN_TARGET_SDK"
ok "targetSdk $TARGET"

# 5. No extra permissions
EXTRA=$(sed -n "s/^uses-permission: name='\([^']*\)'.*/\1/p" "$RUNNER_TEMP/badging.txt" \
  | grep -vxF $(for p in $ALLOWED_PERMISSIONS; do printf -- "-e %s " "$p"; done) || true)
[ -z "$EXTRA" ] || fail "Unexpected permissions: $(echo $EXTRA)"
ok "permissions: $(sed -n "s/^uses-permission: name='\([^']*\)'.*/\1/p" "$RUNNER_TEMP/badging.txt" | tr '\n' ' ')"

# 6. App content is packaged
unzip -p "$APK" assets/index.html | grep -q 'catalog' || fail "assets/index.html missing from APK"
ok "assets/index.html packaged"

# 7. Report what is inside, so the build log shows it
ICONS=$(unzip -l "$APK" | grep -c 'assets/icons/.*\.svg' || true)
PHOTOS=$(unzip -l "$APK" | grep -c 'assets/photos/' || true)
ICON_RECIPES=$(unzip -p "$APK" assets/index.html | grep -o '"photo":"icons/' | wc -l)
APPVER=$(unzip -p "$APK" assets/index.html | grep -o 'app-version"[^>]*>[^<]*' | sed 's/.*>//' || true)
echo "Inside APK: $ICONS icon files, $PHOTOS photo files, $ICON_RECIPES recipes with icons, $APPVER"

echo "All checks passed"
