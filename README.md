# TP CoAP pour l'IoT (Python + aiocoap)

Serveur et client CoAP (RFC 7252) avec [aiocoap](https://aiocoap.readthedocs.io/) 0.4.17, sans Docker.

| Fichier | Rôle |
|---|---|
| `server.py` | Serveur CoAP UDP 5683 (ressources ci-dessous, trace de chaque requête) |
| `client.py` | Client async scriptable : GET, observation (`--observe`), blockwise manuel (`--szx`) |
| `tests.sh` | Enchaîne toutes les commandes du TP et écrit `tests_output.txt` |
| `REPONSES.md` | Réponses aux questions des modules 1 à 3 |

## Installation

```bash
python -m venv .venv
# Windows (Git Bash) : source .venv/Scripts/activate   | PowerShell : .venv\Scripts\Activate.ps1
# Linux/macOS        : source .venv/bin/activate
pip install -r requirements.txt
```

## Lancement

```bash
python server.py        # terminal 1 : le serveur (Ctrl+C pour arrêter)
./tests.sh              # terminal 2 : tous les tests (Git Bash sous Windows)
python client.py        # passerelle : GET coap://localhost/temp
```

Sous Windows, exportez `PYTHONIOENCODING=utf-8` avant d'appeler `aiocoap-client`. Sans cette variable, `aiocoap-client --help` plante en cp1252.

## Ressources

| URI | Méthodes | Détail |
|---|---|---|
| `/temp` | GET, PUT, Observe | Valeur aléatoire entre 20.0 et 25.0, changée toutes les 2 s. PUT non numérique → 4.00 |
| `/led` | GET, PUT | `on` / `off` → 2.04. Autre valeur → 4.00 |
| `/logs` | GET, POST, DELETE | POST → 2.01 + `Location-Path: logs/<n>`. DELETE → 2.02 |
| `/time` | GET | Heure UTC ISO 8601 |
| `/sensors/room1/{temperature,humidity,light}` | GET | 23.5 / 55 / 150 |
| `/biglog` | GET | 60 lignes (1 782 o) → transfert Block2 |
| `/.well-known/core` | GET | Découverte (générée par aiocoap) |

## Commandes utiles

```bash
C=aiocoap-client
$C coap://localhost/time
$C -m PUT --payload 30.5 coap://localhost/temp
$C -m PUT --payload off  coap://localhost/led
$C -m POST --payload "Seuil depasse" coap://localhost/logs -v   # voir Location-Path
$C -m DELETE coap://localhost/logs
$C coap://localhost/.well-known/core
$C coap://localhost/biglog | wc -c
$C coap://localhost/biglog --verbose 2>&1 | grep Block2

python client.py coap://localhost/temp --observe 10     # notifications pendant 10 s
python client.py coap://localhost/biglog --szx 4        # blocs de 256 octets
```

## Limitations connues (aiocoap 0.4.17)

- **`aiocoap-client --observe` n'affiche que la première valeur.** Dans `cli/client.py`, un bloc `finally` annule l'observation dès la réponse initiale. Utilisez `python client.py --observe N` à la place.
- **Pas d'option `--block`** dans `aiocoap-client`. `--payload-initial-szx` ne concerne que Block1 (envoi). Pour forcer la taille Block2, utilisez `client.py --szx`.
- **Windows** : le serveur écoute sur `::1`, car le transport `simplesocketserver` refuse `::`. Il tourne aussi sur un `SelectorEventLoop` : avec le Proactor, la socket UDP se fige après un ICMP « port unreachable ». Sous Linux/macOS, il écoute sur `::` (toutes interfaces).
