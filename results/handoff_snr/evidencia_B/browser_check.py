"""Real-browser check of «Mejora infrarroja» (headless Chrome driven through the DevTools protocol)."""
import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

OUT = Path(sys.argv[1])
PROFILE = sys.argv[2]
URL = "http://localhost:8520/"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9337
log = []


class Page:
    def __init__(self, ws):
        self.ws, self.n, self.errors = ws, 0, []

    async def cmd(self, method, **params):
        self.n += 1
        mid = self.n
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            if msg.get("method") == "Runtime.exceptionThrown":
                self.errors.append(msg["params"]["exceptionDetails"].get("text", "") + " " + str(
                    msg["params"]["exceptionDetails"].get("exception", {}).get("description", ""))[:200])
            if msg.get("method") == "Log.entryAdded" and msg["params"]["entry"]["level"] == "error":
                self.errors.append(msg["params"]["entry"]["text"][:200])

    async def js(self, expr):
        r = await self.cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    async def wait(self, expr, timeout=240, what=""):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if await self.js(expr):
                return round(time.time() - t0, 1)
            await asyncio.sleep(0.5)
        raise TimeoutError(what or expr)

    async def click(self, finder, what=""):
        """Real mouse click at the centre of the element returned by the JS expression ``finder``."""
        box = await self.js(f"(() => {{ const e = {finder}; if (!e) return null; e.scrollIntoView({{block:'center'}});"
                            " const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")
        if not box:
            raise RuntimeError("not found: " + (what or finder))
        await asyncio.sleep(0.3)
        box = await self.js(f"(() => {{ const r = ({finder}).getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }})()")
        for kind in ("mousePressed", "mouseReleased"):
            await self.cmd("Input.dispatchMouseEvent", type=kind, x=box[0], y=box[1], button="left", clickCount=1)
        await asyncio.sleep(0.8)

    async def shot(self, name, full=True):
        if full:
            m = await self.cmd("Page.getLayoutMetrics")
            size = m["cssContentSize"]
            data = await self.cmd("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                                  clip={"x": 0, "y": 0, "width": size["width"], "height": min(size["height"], 5000), "scale": 1})
        else:
            data = await self.cmd("Page.captureScreenshot", format="png")
        (OUT / name).write_bytes(base64.b64decode(data["data"]))

    async def overflow(self):
        return await self.js("document.documentElement.scrollWidth - window.innerWidth")


TEXT = "document.body.innerText.toLowerCase()"
DEEPEST = lambda text: ("[...document.querySelectorAll('div,span,li,p')].filter(e => e.innerText && "  # noqa: E731
                        f"e.innerText.trim().startsWith({json.dumps(text)})).pop()")
SELECT = DEEPEST("Las ")
BY_TEXT = lambda tag, text: (f"[...document.querySelectorAll('{tag}')].find(e => e.innerText && "  # noqa: E731
                             f"e.innerText.trim().toLowerCase().includes({json.dumps(text.lower())}))")
IDLE = "!document.querySelector('[data-testid=\"stStatusWidget\"]') || !document.querySelector('[data-testid=\"stStatusWidget\"]').innerText.includes('running')"


def note(key, value):
    log.append({key: value})
    print(key, "->", value, flush=True)


async def settle(p, extra=1.0):
    await asyncio.sleep(1.0)
    await p.wait(IDLE, what="app idle")
    await asyncio.sleep(extra)


async def main():
    chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}",
                               "--window-size=1280,1400", "--hide-scrollbars", "--no-first-run", "about:blank"])
    try:
        for _ in range(40):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read())
                break
            except Exception:
                time.sleep(0.5)
        ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
        async with websockets.connect(ws_url, max_size=None) as ws:
            p = Page(ws)
            for d in ("Page", "Runtime", "Log"):
                await p.cmd(d + ".enable")
            await p.cmd("Emulation.setDeviceMetricsOverride", width=1280, height=1400, deviceScaleFactor=1, mobile=False)
            await p.cmd("Page.navigate", url=URL)
            await p.wait(f"{TEXT}.includes('skyclues')", what="home")
            await settle(p, 2)
            # Científico, M101 validated example
            await p.click(BY_TEXT("button", "Científico"), "level Científico")
            await settle(p)
            await p.click(BY_TEXT("button", "M101 · 4 épocas"), "M101 example")
            await p.wait("!!document.querySelector('iframe')", what="sequence player")
            await settle(p)
            note("m101_sequence_opened", await p.js(f"{TEXT}.includes('mejora infrarroja')"))
            await p.click(BY_TEXT("label", "Mejora infrarroja"), "toggle")
            note("m101_sequence_seconds", await p.wait(f"{TEXT}.includes('imagen mejorada')", what="enhanced image"))
            await settle(p)
            note("m101_sci_text", await p.js(
                f"['ganancia s/n','mismo canal','exposiciones combinadas','qué combinar'].map(t => {TEXT}.includes(t))"))
            note("m101_sci_overflow_px", await p.overflow())
            await p.shot("browser_m101_scientific.png")
            # Sencillo: same product, plain words
            await p.click(BY_TEXT("button", "Sencillo"), "level Sencillo")
            await settle(p)
            note("m101_simple_text", await p.js(
                f"[{TEXT}.includes('imagen mejorada'), {TEXT}.includes('mejora de la señal'), "
                f"!{TEXT}.includes('ganancia s/n'), !{TEXT}.includes('variance')]"))
            await p.shot("browser_m101_simple.png")
            # Narrow window
            await p.cmd("Emulation.setDeviceMetricsOverride", width=420, height=900, deviceScaleFactor=1, mobile=False)
            await settle(p, 2)
            note("m101_narrow_overflow_px", await p.overflow())
            await p.shot("browser_m101_narrow.png")
            await p.cmd("Emulation.setDeviceMetricsOverride", width=1280, height=1400, deviceScaleFactor=1, mobile=False)
            await settle(p)
            # Toggle off: the original sequence comes back
            await p.click(BY_TEXT("label", "Mejora infrarroja"), "toggle off")
            await p.wait("!!document.querySelector('iframe')", what="player back")
            note("m101_player_back", True)
            await p.click(BY_TEXT("label", "Mejora infrarroja"), "toggle on")
            await p.wait(f"{TEXT}.includes('imagen mejorada')")
            # Region and back: the option and the FOV are kept
            await p.click(BY_TEXT("button", "Región"), "nav Región")
            await settle(p)
            await p.click(BY_TEXT("button", "Tiempo"), "nav Tiempo")
            await p.wait(f"{TEXT}.includes('imagen mejorada')", what="state kept after navigation")
            note("m101_state_kept_after_navigation", await p.js(f"{TEXT}.includes('6.0′')"))
            # Nearby exposures of one date (broad band): Disponible -> Procesando -> result
            await p.click(BY_TEXT("button", "Científico"), "level Científico")
            await settle(p)
            await p.click(SELECT, "Qué combinar")
            await p.click(DEEPEST("Exposiciones próximas al 2026-05-22"), "option nearby")
            await p.wait(f"{TEXT}.includes('buscar y combinar exposiciones')", what="available state")
            note("m101_nearby_available", await p.js(f"[{TEXT}.includes('disponible'), !{TEXT}.includes('imagen mejorada')]"))
            await p.shot("browser_m101_nearby_available.png", full=False)
            await p.click(BY_TEXT("button", "Buscar y combinar exposiciones"), "run nearby")
            note("m101_nearby_seconds", await p.wait(
                f"{TEXT}.includes('imagen mejorada') || {TEXT}.includes('no disponible para estas observaciones')",
                timeout=600, what="nearby result"))
            await settle(p)
            note("m101_nearby_text", await p.js(
                f"[{TEXT}.includes('imagen mejorada'), {TEXT}.includes('banda ancha'), {TEXT}.includes('banda ancha')]"))
            note("m101_nearby_facts", await p.js("[...document.querySelectorAll('.sc-facts div')].map(e => e.innerText.replace(/\\n/g, ' | '))"))
            await p.shot("browser_m101_nearby_scientific.png")
            # WISE 0855: a target that moves between the dates of the sequence
            await p.click(BY_TEXT("button", "Región"), "nav Región")
            await settle(p)
            await p.click(BY_TEXT("button", "WISE 0855 · 2 épocas"), "WISE example")
            await p.wait(f"{TEXT}.includes('qué combinar')", what="WISE time view")
            await settle(p)
            note("wise_sequence_unavailable", await p.js(
                f"[{TEXT}.includes('no disponible para estas observaciones'), {TEXT}.includes('emborronaría')]"))
            await p.shot("browser_wise0855_unavailable.png", full=False)
            await p.click(SELECT, "Qué combinar")
            options = await p.js("[...new Set([...document.querySelectorAll('[role=option],li')].map(e => e.innerText.trim()))]")
            note("wise_options", options)
            last = [o for o in options if "próximas al" in o][-1]
            await p.click(DEEPEST(last), "option nearby WISE")
            await p.wait(f"{TEXT}.includes('buscar y combinar exposiciones')")
            await p.click(BY_TEXT("button", "Buscar y combinar exposiciones"), "run nearby WISE")
            note("wise_nearby_seconds", await p.wait(
                f"{TEXT}.includes('imagen mejorada') || {TEXT}.includes('no disponible para estas observaciones')",
                timeout=600, what="WISE nearby result"))
            await settle(p)
            note("wise_nearby_state", await p.js(
                f"[{TEXT}.includes('imagen mejorada'), {TEXT}.includes('no disponible para estas observaciones')]"))
            note("wise_nearby_facts", await p.js("[...document.querySelectorAll('.sc-facts div')].map(e => e.innerText.replace(/\\n/g, ' | '))"))
            await p.shot("browser_wise0855_nearby_scientific.png")
            await p.click(BY_TEXT("button", "Sencillo"), "level Sencillo")
            await settle(p)
            note("wise_simple_facts", await p.js("[...document.querySelectorAll('.sc-facts div')].map(e => e.innerText.replace(/\\n/g, ' | '))"))
            await p.shot("browser_wise0855_nearby_simple.png")
            note("console_errors", p.errors)
    finally:
        chrome.terminate()
        (OUT / "browser_check.json").write_text(json.dumps(
            {"checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "url": URL,
             "browser": "Google Chrome headless (DevTools protocol)", "steps": log}, indent=1, ensure_ascii=False),
            encoding="utf-8")


asyncio.run(main())
