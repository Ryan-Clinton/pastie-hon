import asyncio
from pyhon import Hon
from discover import load_credentials

def attr(a, k):
    p = a.attributes.get("parameters", {}) or {}
    v = p.get(k)
    return getattr(v, "value", v) if v is not None else None

def show(a, tag):
    print(f"  [{tag}] remoteCtrValid={attr(a,'remoteCtrValid')} "
          f"machMode={attr(a,'machMode')} onOff={attr(a,'onOffStatus')} "
          f"prCode={attr(a,'prCode')} programme={a.attributes.get('programName')}")

async def main():
    u, pw, _ = load_credentials()
    hon = await Hon(u, pw).create()
    try:
        a = hon.appliances[0]
        await a.update(); show(a, "before")
        print("  sending stopProgram ...")
        try:
            ok = await a.commands["stopProgram"].send()
            print(f"  result: {ok}")
        except Exception as exc:
            print(f"  REJECTED: {type(exc).__name__}: {exc}")
        for i in range(3):
            await asyncio.sleep(10)
            await a.update(); show(a, f"+{(i+1)*10}s")
    finally:
        await hon.close()

asyncio.run(main())
