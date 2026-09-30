#!/usr/bin/env bash
# Lance toutes les commandes du TP CoAP avec aiocoap-client.
# Prérequis : le serveur tourne déjà (python server.py) dans un autre terminal.
# Usage : ./tests.sh [hôte]      (défaut : localhost)
# Sortie : terminal + tests_output.txt

HOST="${1:-localhost}"
BASE="coap://$HOST"
cd "$(dirname "$0")"

# venv : Scripts/ sous Windows, bin/ ailleurs
if [ -d .venv/Scripts ]; then VENV_BIN=.venv/Scripts; else VENV_BIN=.venv/bin; fi
CLIENT="$VENV_BIN/aiocoap-client"
PYTHON="$VENV_BIN/python"

# Console Windows en cp1252 : évite les UnicodeEncodeError ; sortie non bufferisée
# pour ne rien perdre quand `timeout` coupe l'observation.
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1

exec > >(tee tests_output.txt) 2>&1

section() { printf '\n==================== %s ====================\n' "$*"; }
run() { printf '\n$ %s\n' "$*"; "$@"; echo; }

section "MODULE 1 - Méthodes CoAP et codes retour"
run "$CLIENT" "$BASE/time" -v 2>&1
run "$CLIENT" "$BASE/temp"
run "$CLIENT" -m PUT --payload 30.5 "$BASE/temp" -v
run "$CLIENT" -m PUT --payload abc "$BASE/temp" -v
run "$CLIENT" "$BASE/led"
run "$CLIENT" -m PUT --payload on "$BASE/led" -v
run "$CLIENT" -m PUT --payload blink "$BASE/led" -v
run "$CLIENT" -m PUT --payload off "$BASE/led" -v
run "$CLIENT" "$BASE/led"
run "$CLIENT" -m DELETE "$BASE/logs" -v   # part d'une liste vide
run "$CLIENT" -m POST --payload "Capteur demarre" "$BASE/logs" -v
run "$CLIENT" -m POST --payload "Seuil depasse" "$BASE/logs" -v
run "$CLIENT" "$BASE/logs"
run "$CLIENT" -m DELETE "$BASE/logs" -v
run "$CLIENT" "$BASE/logs"
run "$CLIENT" "$BASE/sensors/room1/temperature"
run "$CLIENT" "$BASE/sensors/room1/humidity"
run "$CLIENT" "$BASE/sensors/room1/light"
run "$CLIENT" "$BASE/inexistant" -v

section "MODULE 2 - Observe"
# aiocoap-client 0.4.17 : --observe n'affiche que la 1re valeur, car
# cli/client.py annule l'observation (bloc finally) juste après la réponse.
echo '$ timeout 10 aiocoap-client --observe /temp   (limité par le bug 0.4.17)'
timeout 10 "$CLIENT" --observe "$BASE/temp"
echo

echo '$ timeout 10 aiocoap-client --observe /temp --verbose'
timeout 10 "$CLIENT" --observe "$BASE/temp" --verbose 2>&1
echo

# Mesures réelles avec client.py (observation complète)
run "$PYTHON" client.py "$BASE/temp" --observe 10

echo '$ 2 observateurs simultanés (client.py --observe 10, x2)'
"$PYTHON" client.py "$BASE/temp" --observe 10 > obs_A.txt &
PID_A=$!
"$PYTHON" client.py "$BASE/temp" --observe 10 > obs_B.txt &
PID_B=$!
wait "$PID_A" "$PID_B"   # pas de `wait` nu : il attendrait aussi le tee
echo "--- Observateur A"; cat obs_A.txt
echo "--- Observateur B"; cat obs_B.txt
rm -f obs_A.txt obs_B.txt

section "MODULE 3 - Découverte et blockwise"
run "$CLIENT" "$BASE/.well-known/core"
echo "--> nombre de ressources : $("$CLIENT" "$BASE/.well-known/core" | tr ',' '\n' | grep -c '^</')"

echo
echo '$ aiocoap-client /biglog | wc -c'
"$CLIENT" "$BASE/biglog" | wc -c
"$CLIENT" "$BASE/biglog" | head -3

echo
echo '$ aiocoap-client /biglog --verbose 2>&1 | grep Block2'
"$CLIENT" "$BASE/biglog" --verbose 2>&1 | grep Block2

# aiocoap-client n'a pas d'option --block (cf. --help) : seule
# --payload-initial-szx existe, et elle ne concerne que Block1 (payload envoyé).
# On force donc la taille Block2 (256 o, SZX=4) via client.py --szx.
run "$PYTHON" client.py "$BASE/biglog" --szx 4

section "Passerelle client.py"
run "$PYTHON" client.py "$BASE/temp"
