"""Serveur CoAP du TP EFREI M2 "CoAP pour l'IoT" (aiocoap 0.4.x).

Ressources exposées sur coap://[::]:5683 :
  /temp                       Observable, GET / PUT (float)
  /led                        GET / PUT ("on" | "off")
  /logs                       GET / POST / DELETE
  /time                       GET (UTC, ISO 8601)
  /sensors/room1/temperature  GET
  /sensors/room1/humidity     GET
  /sensors/room1/light        GET
  /biglog                     GET (payload > 1024 o -> transfert blockwise)
  /.well-known/core           généré automatiquement par aiocoap
"""

import asyncio
import datetime
import logging
import random
import sys

import aiocoap
import aiocoap.resource as resource
from aiocoap.numbers.codes import Code

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("coap-server")
logging.getLogger("coap").setLevel(logging.WARNING)


def text(payload, code=Code.CONTENT):
    return aiocoap.Message(
        code=code,
        payload=payload.encode("utf-8"),
        content_format=0,  # text/plain;charset=utf-8
    )


class LoggingSite(resource.Site):
    """Site qui trace chaque requête reçue dans le terminal du serveur."""

    # En aiocoap 0.4.x, le point d'entrée des requêtes est render_to_pipe
    # (render() n'est plus appelé par le Site).
    async def render_to_pipe(self, pipe):
        request = pipe.request
        path = "/" + "/".join(request.opt.uri_path)
        extra = ""
        if request.opt.observe == 0:
            extra += " [Observe register]"
        if request.opt.block2 is not None:
            b2 = request.opt.block2
            extra += f" [Block2 num={b2.block_number} size={b2.size}]"
        payload = request.payload.decode("utf-8", "replace")
        if payload:
            extra += f" payload={payload!r}"
        log.info("%s %s from %s%s", request.code, path, request.remote.hostinfo, extra)
        return await super().render_to_pipe(pipe)


class TemperatureResource(resource.ObservableResource):
    """Température observable, mise à jour toutes les 2 s entre 20.0 et 25.0."""

    def __init__(self):
        super().__init__()
        self.value = 22.0
        self.handle = None

    def update_observation_count(self, count):
        log.info("/temp : %d observateur(s)", count)

    async def background_task(self):
        while True:
            await asyncio.sleep(2)
            self.value = round(random.uniform(20.0, 25.0), 1)
            self.updated_state()

    async def render_get(self, request):
        return text(f"{self.value:.1f}")

    async def render_put(self, request):
        try:
            self.value = float(request.payload.decode("utf-8").strip())
        except ValueError:
            return text("Valeur invalide : un nombre est attendu", Code.BAD_REQUEST)
        self.updated_state()
        return text(f"{self.value:.1f}", Code.CHANGED)


class LedResource(resource.Resource):
    def __init__(self):
        super().__init__()
        self.state = "off"

    async def render_get(self, request):
        return text(self.state)

    async def render_put(self, request):
        value = request.payload.decode("utf-8").strip().lower()
        if value not in ("on", "off"):
            return text("Valeur invalide : utiliser 'on' ou 'off'", Code.BAD_REQUEST)
        self.state = value
        return text(self.state, Code.CHANGED)


class LogsResource(resource.Resource):
    def __init__(self):
        super().__init__()
        self.logs = []

    async def render_get(self, request):
        if not self.logs:
            return text("(aucun log)")
        return text("\n".join(f"{i}. {l}" for i, l in enumerate(self.logs, 1)))

    async def render_post(self, request):
        entry = request.payload.decode("utf-8").strip()
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{now}] {entry}")
        response = text(f"Log {len(self.logs)} ajouté", Code.CREATED)
        response.opt.location_path = ("logs", str(len(self.logs)))
        return response

    async def render_delete(self, request):
        self.logs.clear()
        return aiocoap.Message(code=Code.DELETED)


class TimeResource(resource.Resource):
    async def render_get(self, request):
        now = datetime.datetime.now(datetime.timezone.utc)
        return text(now.isoformat(timespec="seconds"))


class SensorResource(resource.Resource):
    def __init__(self, value, unit=""):
        super().__init__()
        self.value = value
        self.unit = unit

    async def render_get(self, request):
        return text(f"{self.value}{self.unit}")


class BigLogResource(resource.Resource):
    """60 lignes (~1,8 ko) : dépasse 1024 o donc déclenche le Block2."""

    def __init__(self):
        super().__init__()
        self.content = "\n".join(
            f"Log {i}: capteur X - valeur {i * 7 % 100}" for i in range(60)
        )

    async def render_get(self, request):
        return text(self.content)


async def main():
    root = LoggingSite()
    root.add_resource(
        [".well-known", "core"],
        resource.WKCResource(root.get_resources_as_linkheader),
    )

    temp = TemperatureResource()
    root.add_resource(["temp"], temp)
    root.add_resource(["led"], LedResource())
    root.add_resource(["logs"], LogsResource())
    root.add_resource(["time"], TimeResource())
    root.add_resource(["sensors", "room1", "temperature"], SensorResource(23.5))
    root.add_resource(["sensors", "room1", "humidity"], SensorResource(55))
    root.add_resource(["sensors", "room1", "light"], SensorResource(150))
    root.add_resource(["biglog"], BigLogResource())

    # Sous Windows, aiocoap n'a que le transport "simplesocketserver", qui
    # refuse l'adresse joker "::" (pas de recvmsg/IPV6_PKTINFO) : on se
    # rabat sur la boucle locale IPv6.
    host = "::1" if sys.platform == "win32" else "::"
    await aiocoap.Context.create_server_context(root, bind=(host, 5683))
    log.info("Serveur CoAP démarré sur coap://[%s]:5683", host)

    temp.handle = asyncio.create_task(temp.background_task())
    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    # Sous Windows, le ProactorEventLoop arrête de lire la socket UDP dès
    # qu'un ICMP "port unreachable" revient (client parti) -> serveur figé.
    # Le SelectorEventLoop remonte l'erreur au protocole et continue.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    try:
        asyncio.run(main(), loop_factory=loop_factory)
    except KeyboardInterrupt:
        pass
