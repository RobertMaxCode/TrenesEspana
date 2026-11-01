#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WROOT="$(cygpath -m "$ROOT")"
SDK="$(cygpath -m "$HOME/.local/android-sdk")"
BT="$SDK/build-tools/37.0.0"
AJ="$SDK/platforms/android-34/android.jar"
OUT="$ROOT/build"
WOUT="$WROOT/build"

rm -rf "$OUT"
mkdir -p "$OUT/gen" "$OUT/classes" "$OUT/dex"

"$BT/aapt2.exe" compile --dir "$ROOT/res" -o "$OUT/res.zip"

"$BT/aapt2.exe" link \
    -o "$OUT/base.apk" \
    -I "$AJ" \
    --manifest "$ROOT/AndroidManifest.xml" \
    --java "$OUT/gen" \
    --min-sdk-version 26 \
    --target-sdk-version 33 \
    --version-code 1 \
    --version-name 1.0 \
    -A "$WROOT/assets" \
    "$OUT/res.zip"

find "$ROOT/src" "$OUT/gen" -name '*.java' | sed "s|^$ROOT|$WROOT|" > "$OUT/sources.txt"
"$JAVA_HOME/bin/javac.exe" -encoding UTF-8 -source 8 -target 8 \
    -classpath "$AJ" -d "$OUT/classes" "@$OUT/sources.txt"

"$JAVA_HOME/bin/jar.exe" cf "$OUT/classes.jar" -C "$OUT/classes" .
"$BT/d8.bat" --release --lib "$AJ" --min-api 26 --output "$OUT/dex" "$OUT/classes.jar"

cp "$OUT/base.apk" "$OUT/unaligned.apk"
(cd "$OUT/dex" && "$JAVA_HOME/bin/jar.exe" uf "$OUT/unaligned.apk" classes.dex)
"$BT/zipalign.exe" -f 4 "$OUT/unaligned.apk" "$OUT/aligned.apk"

KS="$ROOT/debug.keystore"
if [ ! -f "$KS" ]; then
    "$JAVA_HOME/bin/keytool.exe" -genkeypair -keystore "$KS" -alias trenes \
        -storepass android -keypass android -keyalg RSA -keysize 2048 -validity 10000 \
        -dname "CN=Trenes, O=Personal, C=ES"
fi

"$BT/apksigner.bat" sign --ks "$KS" --ks-pass pass:android --key-pass pass:android \
    --out "$WROOT/Trenes.apk" "$OUT/aligned.apk"
"$BT/apksigner.bat" verify "$WROOT/Trenes.apk"
ls -lh "$ROOT/Trenes.apk"
echo "APK listo: $ROOT/Trenes.apk"
