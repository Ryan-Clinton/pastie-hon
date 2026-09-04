import asyncio
from pyhon import Hon
from discover import load_credentials

async def main():
    u, pw, _ = load_credentials()
    hon = await Hon(u, pw).create()
    try:
        a = hon.appliances[0]
        await a.update()
        params = a.attributes.get("parameters", {}) or {}
        print(f"programme={a.attributes.get('programName')}\n")
        for k in sorted(params):
            v = params[k]
            v = getattr(v, "value", v)
            print(f"  {k:<26} {v}")
    finally:
        await hon.close()

asyncio.run(main())
