#!/bin/sh
# Build the Anamnesis IncidentMemory plugin JAR with proper Pegasus codegen
# Run this INSIDE the datahub-gms container

set -e

LIBDIR=/tmp/gms/extraction/BOOT-INF/lib
PDL_SRC=/etc/datahub/plugins/models/anamnesis-incident-model/0.0.0-dev/com/anamnesis/incident/IncidentMemory.pdl
WORK=/tmp/anamnesis-build
PLUGIN_DIR=/etc/datahub/plugins/models/anamnesis-incident-model/0.0.0-dev

echo "=== Step 1: Setup workspace ==="
rm -rf "$WORK"
mkdir -p "$WORK/pdl/com/anamnesis/incident"
mkdir -p "$WORK/src"
mkdir -p "$WORK/classes/com/anamnesis/incident"
mkdir -p "$WORK/jar/META-INF"
cp "$PDL_SRC" "$WORK/pdl/com/anamnesis/incident/"

echo "=== Step 2: Build classpath ==="
CP=""
for f in $LIBDIR/*.jar; do
  CP="${CP}:${f}"
done
# Strip leading colon
CP="${CP#:}"
echo "Classpath built with $(echo $CP | tr ':' '\n' | wc -l) jars"

echo "=== Step 3: Run Pegasus codegen ==="
java -cp "$CP" com.linkedin.pegasus.generator.PegasusDataTemplateGenerator \
  "$WORK/src" \
  "$WORK/pdl/com/anamnesis/incident/IncidentMemory.pdl"
echo "Generator exit: $?"

echo "=== Step 4: Check generated Java ==="
find "$WORK/src" -name "*.java" | head -20

echo "=== Step 5: Compile generated Java ==="
JAVAC_CP=""
for f in $LIBDIR/data-*.jar $LIBDIR/pegasus-common-*.jar $LIBDIR/restli-common-*.jar; do
  JAVAC_CP="${JAVAC_CP}:${f}"
done
JAVAC_CP="${JAVAC_CP#:}"

find "$WORK/src" -name "*.java" > /tmp/sources.txt
javac -cp "$JAVAC_CP" -d "$WORK/classes" @/tmp/sources.txt
echo "Compile exit: $?"

echo "=== Step 6: Build pegasus-models.idx ==="
find "$WORK/classes" -name "*.class" | \
  grep -v '\$' | \
  sed "s|${WORK}/classes/||" | \
  sed 's|/|.|g' | \
  sed 's|\.class$||' > "$WORK/jar/META-INF/pegasus-models.idx"
echo "Index contents:"
cat "$WORK/jar/META-INF/pegasus-models.idx"

echo "=== Step 7: Package JAR ==="
cp -r "$WORK/classes/." "$WORK/jar/"
cd "$WORK/jar"
jar cf "$WORK/anamnesis-incident-model.jar" .
echo "JAR created: $(ls -lh $WORK/anamnesis-incident-model.jar)"

echo "=== Step 8: Install into plugin dir ==="
cp "$WORK/anamnesis-incident-model.jar" "$PLUGIN_DIR/"
echo "Installed JAR to $PLUGIN_DIR"

echo "=== Step 9: Final plugin dir contents ==="
find "$PLUGIN_DIR" -type f | sort

echo "=== DONE ==="
