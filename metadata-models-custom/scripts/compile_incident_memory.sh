#!/bin/sh
set -e

PLUGIN_DIR="/etc/datahub/plugins/models/anamnesis-incident-model/0.0.0-dev"
PDL_FILE="${PLUGIN_DIR}/com/anamnesis/incident/IncidentMemory.pdl"
WORK_DIR="/tmp/incident-memory-build"
JAR_DIR="/tmp/pegasus-jars/BOOT-INF/lib"

rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}/src" "${WORK_DIR}/classes"

# Build classpath from ALL jars in the extracted WAR lib dir
CP=""
for jar in "${JAR_DIR}"/*.jar; do
  CP="${CP}:${jar}"
done
# strip leading colon
CP="${CP#:}"

echo "=== [1] Generating Java from PDL ==="
java -cp "${CP}" \
  com.linkedin.pegasus.generator.PegasusDataTemplateGenerator \
  "${WORK_DIR}/src" \
  "${PDL_FILE}"

echo "=== [2] Generated files ==="
find "${WORK_DIR}/src" -name "*.java"

JAVA_COUNT=$(find "${WORK_DIR}/src" -name "*.java" | wc -l)
if [ "${JAVA_COUNT}" -eq 0 ]; then
  echo "ERROR: No Java files generated. Aborting."
  exit 1
fi

echo "=== [3] Compiling Java ==="
find "${WORK_DIR}/src" -name "*.java" > /tmp/java_sources.txt
javac -cp "${CP}" -d "${WORK_DIR}/classes" @/tmp/java_sources.txt

echo "=== [4] Packaging JAR ==="
cd "${WORK_DIR}/classes"
jar cf "${PLUGIN_DIR}/incident-memory-plugin.jar" .

echo "=== SUCCESS ==="
ls -lh "${PLUGIN_DIR}/incident-memory-plugin.jar"
echo "--- Plugin directory ---"
ls "${PLUGIN_DIR}/"
