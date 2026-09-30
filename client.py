"""Client CoAP scriptable (passerelle) : GET /temp et affichage du résultat.

Usage :
  python client.py                               # GET coap://localhost/temp
  python client.py coap://localhost/time         # GET d'une autre ressource
  python client.py --observe 10                  # observe /temp pendant 10 s
  python client.py coap://localhost/biglog --szx 4
      # blockwise manuel avec des blocs Block2 de 2**(4+4) = 256 octets

--observe remplace `aiocoap-client --observe`, qui en 0.4.17 annule
l'observation juste après la première réponse (cli/client.py, bloc finally).
"""

import argparse
import asyncio
import datetime

import aiocoap
from aiocoap.optiontypes import BlockOption


async def get(context, uri):
    request = aiocoap.Message(code=aiocoap.GET, uri=uri)
    response = await context.request(request).response
    print(f"URI     : {uri}")
    print(f"Code    : {response.code}")
    print(f"Taille  : {len(response.payload)} octets")
    print(f"Payload : {response.payload.decode('utf-8', 'replace')}")


async def observe(context, uri, duration):
    request = aiocoap.Message(code=aiocoap.GET, uri=uri, observe=0)
    requester = context.request(request)
    count = 0

    def show(message, kind):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        value = message.payload.decode("utf-8", "replace")
        print(f"[{now}] {kind:<12} Observe={message.opt.observe} valeur={value}",
              flush=True)

    first = await requester.response
    show(first, "réponse")

    async def notifications():
        nonlocal count
        async for notification in requester.observation:
            count += 1
            show(notification, "notification")

    try:
        await asyncio.wait_for(notifications(), duration)
    except asyncio.TimeoutError:
        pass
    finally:
        if not requester.observation.cancelled:
            requester.observation.cancel()
    print(f"--> {count} notification(s) reçue(s) en {duration} s "
          f"(+ 1 réponse initiale)")


async def blockwise(context, uri, szx):
    """Récupère la ressource bloc par bloc (Block2) pour visualiser le découpage."""
    payload = b""
    num = 0
    while True:
        request = aiocoap.Message(code=aiocoap.GET, uri=uri)
        request.opt.block2 = BlockOption.BlockwiseTuple(num, False, szx)
        response = await context.request(request, handle_blockwise=False).response
        block = response.opt.block2
        payload += response.payload
        print(f"Bloc {block.block_number:>2} : {len(response.payload):>4} octets "
              f"(Block2 num={block.block_number} M={int(block.more)} "
              f"SZX={block.size_exponent} -> {block.size} o)")
        if not block.more:
            break
        num += 1
    print(f"--> {num + 1} blocs, {len(payload)} octets au total")


async def main():
    parser = argparse.ArgumentParser(description="Passerelle CoAP")
    parser.add_argument("uri", nargs="?", default="coap://localhost/temp")
    parser.add_argument("--observe", type=float, metavar="SECONDES",
                        help="Observe la ressource pendant SECONDES")
    parser.add_argument("--szx", type=int, choices=range(7),
                        help="Blockwise manuel : taille 2**(SZX+4) (4 = 256 o)")
    args = parser.parse_args()

    context = await aiocoap.Context.create_client_context()
    try:
        if args.observe:
            await observe(context, args.uri, args.observe)
        elif args.szx is not None:
            await blockwise(context, args.uri, args.szx)
        else:
            await get(context, args.uri)
    except aiocoap.error.Error as e:
        print(f"Échec de la requête vers {args.uri} : {e}")
    finally:
        await context.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
