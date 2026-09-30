# TP CoAP pour l'IoT : réponses

Environnement : Python 3.13.7, **aiocoap 0.4.17**, Windows 11 (sans Docker).
Toutes les sorties ci-dessous viennent de `./tests.sh` (fichier `tests_output.txt`) et du terminal serveur (`server.log`).

> **Remarques sur l'environnement**
> - Sous Windows, aiocoap n'a que le transport `simplesocketserver`, qui refuse l'adresse joker `::`. Le serveur écoute donc sur `::1` sous Windows et sur `::` sous Linux/macOS.
> - Sous Windows, le serveur tourne sur un `SelectorEventLoop`. Avec le `ProactorEventLoop` par défaut, un ICMP « port unreachable » (client déjà parti) fige la lecture UDP.
> - `aiocoap-client --observe` (0.4.17) n'affiche que la **première** valeur. Dans `cli/client.py`, un bloc `finally` appelle `observation.cancel()` juste après la réponse initiale. Les mesures Observe ont donc été faites avec `client.py --observe 10`.
> - `aiocoap-client` n'a pas d'option `--block`. La seule option de ce type est `--payload-initial-szx`, et elle ne s'applique qu'à Block1. Les blocs Block2 de 256 o ont donc été forcés avec `client.py --szx 4`.

---

## Module 1 : méthodes CoAP et codes retour

| Question | Réponse | Justification / sortie |
|---|---|---|
| Code retour de `GET /time` | **2.05 Content** | `2.05 Content from coap://localhost` puis `2026-09-30T13:41:28+00:00` (UTC, ISO 8601) |
| Code retour de `PUT /temp` (`30.5`) | **2.04 Changed** | `2.04 Changed from coap://localhost` puis `30.5` |
| `PUT /led` avec `blink` : code et raison | **4.00 Bad Request** | Le serveur n'accepte que `on` ou `off`. Tout autre payload est rejeté comme requête mal formée (erreur **client**, classe 4.xx) : `4.00 Bad Request` / `Valeur invalide : utiliser 'on' ou 'off'` |
| Commande pour éteindre la LED | `aiocoap-client -m PUT --payload off coap://localhost/led` | Réponse `2.04 Changed` / `off`, et un `GET /led` renvoie ensuite `off` |
| `GET /logs` après 2 `POST` | Liste de **2 entrées** numérotées | `1. [15:41:32] Capteur demarre` / `2. [15:41:32] Seuil depasse`. Chaque POST a répondu **2.01 Created** avec `Location-Path: logs/1` puis `logs/2` |
| Code retour de `DELETE /logs` | **2.02 Deleted** | `2.02 Deleted from coap://localhost` (sans payload). Un `GET /logs` renvoie ensuite `(aucun log)` |

Autres vérifications :
- `PUT /temp` avec `abc` donne `4.00 Bad Request` / `Valeur invalide : un nombre est attendu`.
- `GET /inexistant` donne `4.04 Not Found`.

Trace côté serveur (une ligne par requête reçue) :
```
15:41:29 [coap-server] PUT /temp from [::1]:55436 payload='30.5'
15:41:31 [coap-server] PUT /led from [::1]:55440 payload='blink'
15:41:32 [coap-server] POST /logs from [::1]:55444 payload='Capteur demarre'
15:41:32 [coap-server] POST /logs from [::1]:55445 payload='Seuil depasse'
15:41:33 [coap-server] DELETE /logs from [::1]:59737
```

---

## Module 2 : Observe

| Question | Réponse | Justification / sortie |
|---|---|---|
| Nombre de notifications reçues en 10 s | **5 notifications** (+ 1 réponse initiale) | La valeur change toutes les 2 s, soit 10 / 2 = 5. Voir l'extrait 1 |
| Deux observateurs simultanés | Les deux reçoivent **les mêmes notifications, au même instant** | Même valeur, même numéro `Observe`, même seconde. Le serveur compte `5 observateur(s)` puis `6 observateur(s)`. Voir l'extrait 2 |
| Polling : messages et octets | **120 messages, 2 400 octets** | Hypothèse : 1 min, 1 GET/s, soit 60 requêtes + 60 réponses = 120 msg × 20 o |
| Observe : messages et octets | **14 messages, 280 octets** | 1 GET Observe + 1 réponse + 12 notifications (valeur modifiée toutes les 5 s pendant 60 s) = 14 msg × 20 o. C'est **−88 %** de trafic par rapport au polling |
| 2 usages en serre connectée | 1. Alerte **température/humidité** : l'ordinateur de supervision observe les capteurs et ouvre l'aération ou lance la brumisation dès qu'une notification dépasse un seuil. 2. **Humidité du sol** : la vanne d'irrigation s'ouvre à la notification « sol sec », sans interroger le capteur en boucle. | Un capteur sur batterie n'émet que lors d'un changement. La réaction est immédiate et la radio reste éteinte le reste du temps |
| Méthode qui déclenche la notification | **`updated_state()`** | Elle est appelée dans `background_task()` (toutes les 2 s) et après un PUT valide sur `/temp`. Elle appelle `trigger()` sur chaque observation enregistrée, et aiocoap renvoie alors `render_get()` à chaque observateur |

**Extrait 1 : un observateur pendant 10 s**
```
$ python client.py coap://localhost/temp --observe 10
[15:41:56] réponse      Observe=0 valeur=21.2
[15:41:57] notification Observe=1 valeur=20.9
[15:41:59] notification Observe=2 valeur=24.1
[15:42:01] notification Observe=3 valeur=22.4
[15:42:03] notification Observe=4 valeur=21.0
[15:42:05] notification Observe=5 valeur=22.0
--> 5 notification(s) reçue(s) en 10.0 s (+ 1 réponse initiale)
```

**Extrait 2 : deux observateurs lancés en parallèle**
```
--- Observateur A
[15:42:07] notification Observe=1 valeur=22.4
[15:42:09] notification Observe=2 valeur=21.9
[15:42:11] notification Observe=3 valeur=24.7
...
--- Observateur B
[15:42:07] notification Observe=1 valeur=22.4
[15:42:09] notification Observe=2 valeur=21.9
[15:42:11] notification Observe=3 valeur=24.7
...
```
Côté serveur : `GET /temp from [::1]:62853 [Observe register]` puis `GET /temp from [::1]:62854 [Observe register]` : deux enregistrements distincts sur le même état.

`--verbose` montre l'option **Observe** dans la requête (`- Observe (6): 0`, enregistrement) et dans la réponse (`- Observe (6): 0`, numéro de séquence de la notification).

---

## Module 3 : découverte et blockwise

| Question | Réponse | Justification / sortie |
|---|---|---|
| Nombre de ressources dans `/.well-known/core` | **9 liens** : 8 ressources applicatives + `/.well-known/core` lui-même | `/temp`, `/led`, `/logs`, `/time`, `/sensors/room1/{temperature,humidity,light}`, `/biglog`. aiocoap ajoute aussi un lien `rel="impl-info"` vers sa documentation, qui n'est pas une ressource |
| Sens de `;obs` | La ressource est **observable** (RFC 7641) | Seule `</temp>;obs` porte cet attribut, car c'est la seule `ObservableResource`. Un client sait qu'il peut s'y abonner avec l'option Observe |
| Taille de `/biglog` | **1 782 octets** | `aiocoap-client coap://localhost/biglog \| wc -c` affiche `1782` |
| Nombre de blocs à 256 octets | **7 blocs** (6 × 256 + 1 × 246) | Calcul : ⌈1782 / 256⌉ = 7. Vérifié avec `client.py --szx 4` (dernier bloc `M=0`). Avec la taille par défaut (1024 o, SZX=6), il faut **2 blocs** : `Block2 ... block_number=1, more=False, size_exponent=6` |
| Intérêt du blockwise pour une caméra IoT | Transférer une image de plusieurs ko sur des liens contraints | Une trame 6LoWPAN/802.15.4 fait environ 127 o. Sans blockwise, on s'appuie sur la fragmentation IP : un fragment perdu fait perdre toute l'image. Avec Block2, chaque bloc est confirmé et **seul le bloc perdu est retransmis**. Le client choisit la taille (SZX) adaptée au lien, et un appareil à peu de RAM peut traiter l'image bloc par bloc |
| Intérêt du multicast pour 200 capteurs | **1 requête au lieu de 200** | Un seul `GET` NON vers `coap://[ff02::fd]/.well-known/core` (groupe « All CoAP Nodes », RFC 7252 §12.8) découvre ou interroge les 200 capteurs, contre 200 requêtes unicast. Cela coûte moins de trafic, moins d'énergie et moins de temps, et on n'a pas besoin de connaître les adresses à l'avance. Les réponses sont retardées aléatoirement (Leisure) pour éviter une rafale |

**Extraits**
```
$ aiocoap-client coap://localhost/.well-known/core
</.well-known/core>;ct="40",</temp>;obs,</led>,</logs>,</time>,</sensors/room1/temperature>,
</sensors/room1/humidity>,</sensors/room1/light>,</biglog>,
<https://christian.amsuess.com/tools/aiocoap/#version-0.4.17>;rel="impl-info"

$ aiocoap-client coap://localhost/biglog | wc -c
1782

$ aiocoap-client coap://localhost/biglog --verbose 2>&1 | grep Block2
INFO:coap.aiocoap-client:- Block2 (23): BlockwiseTuple(block_number=1, more=False, size_exponent=6)

$ python client.py coap://localhost/biglog --szx 4
Bloc  0 :  256 octets (Block2 num=0 M=1 SZX=4 -> 256 o)
Bloc  1 :  256 octets (Block2 num=1 M=1 SZX=4 -> 256 o)
...
Bloc  6 :  246 octets (Block2 num=6 M=0 SZX=4 -> 256 o)
--> 7 blocs, 1782 octets au total
```
Côté serveur, on voit une requête par bloc :
```
15:42:18 [coap-server] GET /biglog from [::1]:57351 [Block2 num=0 size=256]
15:42:18 [coap-server] GET /biglog from [::1]:57351 [Block2 num=1 size=256]
...
15:42:18 [coap-server] GET /biglog from [::1]:57351 [Block2 num=6 size=256]
```
