import asyncio
from datetime import datetime
from pyhon import Hon
from discover import load_credentials

def attr(a, k):
    p = a.attributes.get("parameters", {}) or {}
    v = p.get(k)
    return getattr(v, "value", v) if v is not None else None

async def main():
    u, pw, _ = load_credentials()
    hon = await Hon(u, pw).create()
    try:
        a = hon.appliances[0]
        for i in range(4):
            await a.update()
            print(f"{datetime.now():%H:%M:%S}  remaining={str(attr(a,'remainingTimeMM')):<5}"
                  f" machMode={attr(a,'machMode')} prPhase={attr(a,'prPhase')}"
                  f" prCode={attr(a,'prCode')} dryLevel={attr(a,'dryLevel')}"
                  f" tempLevel={attr(a,'tempLevel')}", flush=True)
            if i < 3:
                await asyncio.sleep(90)
    finally:
        await hon.close()

asyncio.run(main())
