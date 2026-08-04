#!/bin/sh
# compile_and_package.sh
# Compiles the generated IncidentMemory.java and packages the plugin JAR
# Run INSIDE the GMS container after JDK is installed

set -e

LIBDIR=/tmp/gms/extraction/BOOT-INF/lib
WORK=/tmp/anamnesis-build
PLUGIN_DIR=/etc/datahub/plugins/models/anamnesis-incident-model/0.0.0-dev

echo "=== Step 5: Compile generated Java ==="
JAVAC_CP=""
for f in $LIBDIR/data-*.jar $LIBDIR/pegasus-common-*.jar $LIBDIR/restli-common-*.jar \
          $LIBDIR/javax.annotation-api-*.jar $LIBDIR/jsr305-*.jar; do
  JAVAC_CP="${JAVAC_CP}:${f}"
done
JAVAC_CP="${JAVAC_CP#:}"
echo "Compile classpath: $JAVAC_CP"

find "$WORK/src" -name "*.java" > /tmp/sources.txt
echo "Java sources to compile:"
cat /tmp/sources.txt

mkdir -p "$WORK/classes"
javac -cp "$JAVAC_CP" -d "$WORK/classes" @/tmp/sources.txt
echo "Compile exit: $?"

echo ""
echo "=== Step 6: List compiled classes ==="
find "$WORK/classes" -name "*.class" | sort

echo ""
echo "=== Step 7: Build META-INF/pegasus-models.idx ==="
mkdir -p "$WORK/jar/META-INF"
find "$WORK/classes" -name "*.class" | \
  grep -v '\$' | \
  sed "s|${WORK}/classes/||" | \
  sed 's|/|.|g' | \
  sed 's|\.class$||' | \
  sort > "$WORK/jar/META-INF/pegasus-models.idx"

echo "pegasus-models.idx contents:"
cat "$WORK/jar/META-INF/pegasus-models.idx"

echo ""
echo "=== Step 8: Copy classes into jar staging area ==="
cp -r "$WORK/classes/." "$WORK/jar/"

echo ""
echo "=== Step 9: Create JAR ==="
cd "$WORK/jar"
jar cf "$WORK/anamnesis-incident-model.jar" META-INF/ com/
echo "JAR size: $(ls -lh $WORK/anamnesis-incident-model.jar)"

echo ""
echo "=== Step 10: Verify JAR contents ==="
jar tf "$WORK/anamnesis-incident-model.jar"

echo ""
echo "=== Step 11: Install JAR into plugin directory ==="
cp "$WORK/anamnesis-incident-model.jar" "$PLUGIN_DIR/"
echo "Installed to $PLUGIN_DIR"

echo ""
echo "=== Step 12: Final plugin dir listing ==="
find "$PLUGIN_DIR" -type f | sort

echo ""
echo "=== DONE - Ready to restart GMS ==="
