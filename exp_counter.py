"""EXPERIMENT 1: does the appliance report a cycle counter or session id?"""
import asyncio, json, re
from pyhon import Hon
from discover import load_credentials

INTERESTING = re.compile(
    r"count|cycle|total|session|run|number|num|index|serial|seq|id$", re.I)

async def main():
    u, pw, _ = load_credentials()
    hon = await Hon(u, pw).create()
    try:
        a = hon.appliances[0]
        await a.update()

        print("=== live parameters matching counter-ish names ===")
        params = a.attributes.get("parameters", {}) or {}
        hits = 0
        for k in sorted(params):
            if INTERESTING.search(k):
                v = params[k]
                print(f"    {k:<28} {getattr(v,'value',v)}")
                hits += 1
        print(f"    ({hits} of {len(params)} parameters)")

        print("\n=== statistics endpoint ===")
        try:
            await a.load_statistics()
            st = a.statistics
            if st:
                for k, v in sorted(st.items()):
                    print(f"    {k:<28} {v}")
            else:
                print("    (empty)")
        except Exception as exc:
            print(f"    failed: {type(exc).__name__}: {exc}")

        print("\n=== anything else counter-ish anywhere in the appliance data ===")
        def walk(o, p=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield from walk(v, f"{p}.{k}" if p else k)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    yield from walk(v, f"{p}[{i}]")
            else:
                yield p, o
        seen = set()
        for path, val in walk(a.data):
            leaf = path.split(".")[-1]
            if INTERESTING.search(leaf) and path not in seen:
                seen.add(path)
                s = str(val)
                if len(s) < 40 and "HonAttribute" not in s:
                    print(f"    {path:<44} {s}")
    finally:
        await hon.close()

asyncio.run(main())
