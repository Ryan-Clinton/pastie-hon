"""EXPERIMENT 2: does pyhon-revived's MQTT push connect, stay up, and deliver?"""
import asyncio, inspect, logging, sys
from datetime import datetime

sys.path.insert(0, ".")
from discover import load_credentials
from pyhon import Hon

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s  MQTT  %(message)s",
                    datefmt="%H:%M:%S")
for n in ("aiohttp", "urllib3", "asyncio", "awscrt", "pyhon.connection.auth",
          "pyhon.connection.api", "pyhon.appliance", "pyhon.parameter"):
    logging.getLogger(n).setLevel(logging.WARNING)

def log(m): print(f"{datetime.now():%H:%M:%S}  {m}", flush=True)

pushes = []

async def main():
    u, pw, _ = load_credentials()
    hon = Hon(u, pw)
    await hon.create()
    a = hon.appliances[0]
    p = a.attributes.get("parameters", {}) or {}
    v = lambda k: getattr(p.get(k), "value", p.get(k))
    log(f"appliance {a.nick_name}   machMode={v('machMode')} "
        f"remoteAllowed={v('remoteCtrValid')}")

    log(f"subscribe_updates is a coroutine? {inspect.iscoroutinefunction(hon.subscribe_updates)}")

    def on_push(*args, **kwargs):
        pushes.append(datetime.now())
        log(f"  >>> PUSH #{len(pushes)}  args={[type(x).__name__ for x in args]}")

    try:
        r = hon.subscribe_updates(on_push)          # NOT awaited
        if inspect.isawaitable(r):
            await r
        log("subscribe_updates returned without error")
    except Exception as exc:
        log(f"subscribe_updates FAILED: {type(exc).__name__}: {exc}")
        await hon.close(); return

    log("listening 150s - watching MQTT lifecycle events ...")
    await asyncio.sleep(150)
    log(f"RESULT: {len(pushes)} push callback(s) in 150s "
        f"(machine idle, so few state changes expected)")
    await hon.close()

asyncio.run(main())
