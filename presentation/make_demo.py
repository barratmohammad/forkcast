"""
Build the narrated 5-minute ForkCast capstone presentation video.

    docker compose up -d                                   # in the project root; the stack must be running
    .venv/bin/python make_demo.py                          # preview narration with macOS `say`
    .venv/bin/python make_demo.py --narration narration    # with your own recorded voice

1. Narration: your clips (narration/01.wav, 02.wav, ...) or macOS `say`.
2. Drives the REAL running app (the Streamlit container) with Playwright, plus slides for the
   architecture, the guardrail calibration and the improvements, and captures 1080p frames.
   Each step is held at least as long as its narration clip.
3. Stitches frames and audio together with ffmpeg.

Before recording it resets the demo account through the API: the `demo` user exists, it owns a
fresh "Grandma's Lentil Soup" (vegan, no bacon yet), and it has no meal plans. The model is warmed
up so the first on-camera answer doesn't include model load time.
"""

import argparse
import asyncio
import base64
import html
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
OUT = HERE / "build"
FRAMES = OUT / "frames"
AUDIO = OUT / "audio"
VOICE = os.environ.get("VOICE", "Samantha")
RATE = os.environ.get("RATE", "160")  # close to a natural speaking pace
GAP = 0.45  # pause after each narration line
VIEW_W, VIEW_H, SCALE = 1440, 810, 4 / 3  # renders at 1920x1080


def env_value(key, default):
    """Read a value from the project's .env (so the script uses the same ports as compose)."""
    env = PROJECT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return default


UI_PORT = env_value("FRONTEND_PORT", "8501")
API_PORT = env_value("BACKEND_PORT", "8000")
# 127.0.0.1, not localhost: another project may hold the IPv6 side of the same port.
UI = f"http://127.0.0.1:{UI_PORT}"
API = f"http://127.0.0.1:{API_PORT}"

USERNAME, PASSWORD = "demo", "demopass123"
SOUP = "Grandma's Lentil Soup"
SOUP_BODY = {
    "title": SOUP,
    "category": "Soup",
    "cuisine": "Comfort",
    "ingredients": [
        {"name": "red lentils", "measure": "1 cup"},
        {"name": "carrots", "measure": "2"},
        {"name": "onion", "measure": "1"},
        {"name": "vegetable stock", "measure": "1 litre"},
        {"name": "cumin", "measure": "1 tsp"},
    ],
    "instructions": "Soften the onion and carrots, add the lentils, stock and cumin, "
    "then simmer for 25 minutes and blend.",
}

Q1 = "I have chickpeas, spinach and rice. What can I make tonight?"
Q2 = "Explain quantum computing"
ON_HAND = "chickpeas, spinach, rice"

# --------------------------------------------------------------------------- slides
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:1440px;height:810px;overflow:hidden;background:#14110f;color:#f2ede8;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
.wrap{padding:56px 80px;height:100%;display:flex;flex-direction:column}
.kicker{color:#f0896b;font:600 16px/1 Menlo,monospace;letter-spacing:.12em;text-transform:uppercase;margin-bottom:14px}
h1{font-size:58px;font-weight:750;letter-spacing:-.02em}
h2{font-size:34px;font-weight:700;letter-spacing:-.01em;margin-bottom:22px}
.sub{color:#b5aca4;font-size:22px;margin-top:16px;line-height:1.5}
.pill{display:inline-block;border:1px solid #3a322c;background:#1d1815;border-radius:999px;padding:8px 16px;margin:0 8px 10px 0;font-size:16px;color:#d9d0c8}
.mono{font-family:Menlo,monospace;font-size:.9em}
.card{background:#1d1815;border:1px solid #332b25;border-radius:14px;padding:22px 24px;transition:border-color .4s,opacity .4s,background .4s}
.card.dim{opacity:.28}.card.on{border-color:#f0896b;opacity:1;background:#2a1d18}
.card .n{font:700 30px/1 Menlo,monospace;color:#f0896b;margin-bottom:12px}
.card h3{font-size:20px;margin-bottom:8px}
.card p{color:#d9d0c8;font-size:16px;line-height:1.5}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:24px;flex:1;align-items:start}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:8px}
/* architecture */
.arch{position:relative;flex:1}
.box{position:absolute;background:#1d1815;border:2px solid #332b25;border-radius:14px;padding:14px 18px;
 transition:opacity .45s,border-color .45s,background .45s,box-shadow .45s}
.box h3{font-size:19px;margin-bottom:4px}.box p{color:#b5aca4;font-size:14px;line-height:1.45}
.box .tag{font:600 11px Menlo,monospace;color:#f0896b;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px}
.zone{position:absolute;border:2px dashed #3a322c;border-radius:18px;transition:opacity .45s,border-color .45s}
.zone span{position:absolute;top:-11px;left:18px;background:#14110f;padding:0 8px;color:#8d837b;font:600 13px Menlo,monospace}
.arch.focus .box,.arch.focus .zone,.arch.focus .arr{opacity:.25}
.arch .hl{opacity:1!important;border-color:#f0896b!important}
.box.hl{background:#2a1d18;box-shadow:0 0 0 4px rgba(240,137,107,.12)}
.arr{position:absolute;height:2px;background:#6f655e;transition:opacity .45s,background .45s}
.arr::after{content:"";position:absolute;right:-2px;top:-5px;border:6px solid transparent;border-left:9px solid #6f655e}
.arr.hl{background:#f0896b}.arr.hl::after{border-left-color:#f0896b}
.arr .lbl{position:absolute;top:-24px;left:0;right:0;text-align:center;font:12.5px Menlo,monospace;color:#b5aca4;white-space:nowrap}
.varr{position:absolute;width:2px;background:#6f655e;transition:opacity .45s}
.varr.hl{background:#f0896b}
.foot{position:absolute;left:0;right:0;display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start;transition:opacity .45s}
/* chart */
.chart{background:#1d1815;border:1px solid #332b25;border-radius:14px;padding:18px 24px 38px;position:relative}
.row{display:grid;grid-template-columns:330px 1fr 56px;align-items:center;gap:12px;height:38px;font-size:17px;transition:opacity .4s}
.row .lab{color:#d9d0c8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .track{position:relative;height:16px}
.row .fill{height:100%;border-radius:4px;width:0;transition:width .9s ease}
.row .val{font:13px Menlo,monospace;color:#b5aca4;text-align:right}
.on-t .fill{background:#6fb38a}.off-t .fill{background:#6f655e}
.row.leak .lab{color:#ff8a80;font-weight:600}.row.leak .fill{background:#e05a4f}
.thr{position:absolute;top:10px;bottom:30px;border-left:2px dashed #f0b45a;transition:left 1.2s ease}
.thr span{position:absolute;bottom:-26px;left:-62px;color:#f0b45a;font:600 13px Menlo,monospace;white-space:nowrap}
.legend{display:flex;gap:26px;margin-top:16px;color:#b5aca4;font-size:15px}
.legend i{display:inline-block;width:14px;height:14px;border-radius:3px;margin-right:8px;vertical-align:-2px}
.big{font:800 46px/1.1 -apple-system,Helvetica,sans-serif;margin:6px 0 10px}
.ex{font:14px/1.7 Menlo,monospace;color:#d9d0c8}
.ex b{color:#ff8a80;font-weight:600}
"""


def page(body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"


TITLE = page("""
<div class="wrap" style="justify-content:center">
  <div class="kicker">Module 9 · Capstone · AI-Powered Application</div>
  <h1>🍴 ForkCast</h1>
  <p class="sub" style="font-size:26px;color:#f2ede8">An AI recipe assistant: grounded answers, diet-aware search, meal plans.</p>
  <p class="sub">790 real recipes · FastAPI · SQLAlchemy · ChromaDB · Ollama · Streamlit · one <span class="mono">docker compose up</span></p>
  <div style="margin-top:36px">
    <span class="pill">1 · Live demo</span><span class="pill">2 · Architecture</span>
    <span class="pill">3 · Hardest problem</span><span class="pill">4 · What I'd improve</span>
  </div>
</div>""")

ARCH = page("""
<div class="wrap" style="padding-top:44px;padding-bottom:40px"><div class="kicker">2 · Architecture</div>
<h2 style="margin-bottom:30px">Two containers, one volume, the model on the host</h2>
<div class="arch focus" id="arch">
  <div class="zone" id="z-docker" style="left:150px;top:16px;width:880px;height:430px"><span>docker compose</span></div>
  <div class="zone" id="z-host" style="left:1060px;top:16px;width:220px;height:430px"><span>host Mac</span></div>

  <div class="box" id="b-user" style="left:0;top:150px;width:120px;text-align:center"><div class="tag">you</div><h3>Browser</h3></div>
  <div class="arr" id="a-user" style="left:122px;top:190px;width:56px"></div>

  <div class="box" id="b-fe" style="left:180px;top:120px;width:230px">
    <div class="tag">frontend</div><h3>Streamlit</h3><p>Chat, browse, my recipes, meal planner · JWT in session</p></div>
  <div class="arr" id="a-fe" style="left:412px;top:180px;width:96px"><div class="lbl">REST + JWT</div></div>

  <div class="box" id="b-be" style="left:510px;top:96px;width:250px">
    <div class="tag">backend</div><h3>FastAPI</h3>
    <p>Pydantic on every endpoint · auth · CRUD · RAG pipeline · guardrails</p>
    <p class="mono" style="margin-top:6px;color:#f0896b;font-size:12.5px">http://backend:8000</p></div>
  <div class="arr" id="a-ol" style="left:762px;top:160px;width:316px"><div class="lbl">host.docker.internal:11434</div></div>

  <div class="box" id="b-ol" style="left:1080px;top:110px;width:180px">
    <div class="tag">ollama</div><h3>Ollama</h3><p>llama3.2:3b<br>nomic-embed-text<br>Apple GPU</p></div>

  <div class="varr" id="v-db" style="left:580px;top:226px;height:64px"></div>
  <div class="varr" id="v-vs" style="left:700px;top:226px;height:64px"></div>
  <div class="box" id="b-db" style="left:420px;top:292px;width:260px">
    <div class="tag">SQLAlchemy</div><h3>SQLite</h3><p>users · recipes · tags · recipe_tags · meal_plans · meal_plan_items</p></div>
  <div class="box" id="b-vs" style="left:700px;top:292px;width:220px">
    <div class="tag">embedded</div><h3>ChromaDB</h3><p>790 recipe vectors · diet tags as metadata filters</p></div>
  <div class="zone" id="z-vol" style="left:404px;top:278px;width:534px;height:152px;border-color:#5a4a3f"><span>volume: backend_data</span></div>

  <div class="foot" id="foot" style="top:470px">
    <span class="pill">81 pytest tests · fake Ollama client</span><span class="pill">ruff lint</span>
    <span class="pill">services talk by name, not localhost</span><span class="pill">data survives restarts</span>
  </div>
</div></div>
<script>
window.focusOn = (ids) => {
  const arch = document.getElementById('arch');
  arch.classList.toggle('focus', ids.length > 0);
  document.querySelectorAll('.box,.zone,.arr,.varr,.foot').forEach(e => e.classList.toggle('hl', ids.includes(e.id)));
};
</script>""")

# Best-match cosine distance on the real index (scripts/tune_threshold.py). Lower = closer.
CALIBRATION = [
    ("How do I make pancakes", 0.191, "on"),
    ("Vegan curry", 0.219, "on"),
    ("I have chickpeas and spinach…", 0.229, "on"),
    ("Something spicy with chicken", 0.262, "on"),
    ("Something with leftover rice", 0.323, "on"),
    ("Quick pasta for a weeknight", 0.394, "on"),
    ("How to train a puppy", 0.419, "off"),
    ("What is the capital of France", 0.427, "off"),
    ("How do I change a car tire?", 0.468, "leak"),
    ("How do I reset my password", 0.502, "off"),
    ("Explain quantum computing", 0.525, "off"),
]
SCALE_MAX = 0.6


def challenge_page():
    rows = "".join(
        f'<div class="row {"on-t" if kind == "on" else "off-t"}" data-kind="{kind}">'
        f'<div class="lab">{"🍳" if kind == "on" else "🚫"} {html.escape(q)}</div>'
        f'<div class="track"><div class="fill" data-w="{v / SCALE_MAX * 100:.1f}"></div></div>'
        f'<div class="val">{v:.2f}</div></div>'
        for q, v, kind in CALIBRATION
    )

    def thr(value):
        return f"calc(24px + 342px + (100% - 48px - 342px - 68px) * {value / SCALE_MAX:.4f})"

    return page(f"""
<div class="wrap" style="padding-top:44px"><div class="kicker">3 · Hardest problem</div>
<h2 style="margin-bottom:16px">Making the "I don't know" guardrail trustworthy</h2>
<div class="chart">{rows}
  <div class="thr" id="thr" style="left:{thr(0.50)}"><span id="thr-l">first guess 0.50</span></div></div>
<div class="legend"><span><i style="background:#6fb38a"></i>cooking question</span>
  <span><i style="background:#6f655e"></i>off-topic question</span>
  <span>bar = distance to the closest recipe (lower = closer) · answer only if under the line</span></div>
</div>
<script>
window.grow = () => document.querySelectorAll('.fill').forEach(f => f.style.width = f.dataset.w + '%');
window.leak = () => document.querySelectorAll('.row[data-kind=leak]').forEach(r => r.classList.add('leak'));
window.tune = () => {{
  const t = document.getElementById('thr'); t.style.left = "{thr(0.41)}";
  document.getElementById('thr-l').textContent = 'measured 0.41';
  document.querySelectorAll('.row.leak').forEach(r => r.classList.remove('leak'));
}};
</script>""")


FINDINGS = page("""
<div class="wrap"><div class="kicker">3 · What live testing caught</div>
<h2>Two more fixes the fake tests couldn't find</h2>
<div class="grid2">
 <div class="card dim" id="f1"><h3>The small model's citation style</h3>
  <p>The prompt asks for <span class="mono">[#185]</span>; llama3.2 often writes <span class="mono">(#185)</span>,
  so well-grounded answers were marked ungrounded.</p>
  <div class="big" style="color:#6fb38a">[#185] · (#185) · #185</div>
  <p>The parser accepts any bracket style, and every cited id is still checked against what was retrieved.</p></div>
 <div class="card dim" id="f2"><h3>The source data was wrong</h3>
  <p>The ingredient-based diet tagger flagged recipes that TheMealDB labels <b>Vegetarian</b>:</p>
  <div class="big" style="color:#ff8a80">14 recipes</div>
  <div class="ex">Egg Drop Soup · <b>chicken stock</b><br>Flamiche · <b>lard</b><br>
   Liegeoise Salad · <b>bacon</b><br>Thai rice noodle salad · <b>fish sauce, pork</b></div></div>
</div></div>""")

IMPROVE = page("""
<div class="wrap"><div class="kicker">4 · With more time</div><h2>What I'd improve</h2>
<div class="grid2" style="gap:22px">
 <div class="card dim" id="k1"><div class="n">01</div><h3>Stream the answer</h3>
  <p>Send tokens as they're generated, so the first words appear right away instead of after a 3–6 second spinner</p></div>
 <div class="card dim" id="k2"><div class="n">02</div><h3>Hybrid search + reranking</h3>
  <p>Keyword (BM25) search next to the vectors, then a reranker, so exact ingredient names like <span class="mono">harissa</span> always match</p></div>
 <div class="card dim" id="k3"><div class="n">03</div><h3>Grow into a real product</h3>
  <p>Nutrition estimates, shared meal plans, and PostgreSQL with an admin role for multi-user use</p></div>
 <div class="card dim" id="k4"><div class="n">04</div><h3>An evaluation set in CI</h3>
  <p>30 questions with the recipes they should find, run on every push, so a prompt or threshold change can't quietly make answers worse</p></div>
</div></div>""")

END = page("""
<div class="wrap" style="justify-content:center;align-items:center;text-align:center">
  <div class="kicker">Thanks for watching</div><h1>🍴 ForkCast</h1>
  <p class="sub"><span class="mono">github.com/barratmohammad/forkcast</span></p>
  <p class="sub"><span class="mono">cp .env.example .env &amp;&amp; docker compose up --build</span></p></div>""")


# --------------------------------------------------------------------------- overlay helpers
OVERLAY_JS = """
() => {
  if (document.getElementById('__cur')) return;
  const s = document.createElement('style');
  s.textContent = `#__cur{position:fixed;z-index:2147483647;width:22px;height:22px;pointer-events:none;
    left:0;top:0;transform:translate(-3px,-2px);filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))}
   .__rip{position:fixed;z-index:2147483646;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;
    border:3px solid #c8384a;pointer-events:none;animation:__r .55s ease-out forwards}
   @keyframes __r{from{transform:scale(.3);opacity:1}to{transform:scale(1.6);opacity:0}}
   #__chap{position:fixed;z-index:2147483645;right:18px;bottom:16px;background:rgba(20,17,15,.88);color:#fff;
    font:600 14px/1 -apple-system,Helvetica,sans-serif;padding:10px 14px;border-radius:8px;border-left:4px solid #c8384a}
   .__spot{outline:3px solid #c8384a !important;outline-offset:4px;border-radius:8px;transition:outline-color .3s}`;
  document.head.appendChild(s);
  const c = document.createElement('div'); c.id='__cur';
  c.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22"><path d="M3 2l7.5 19 2.6-7.9L21 10.5z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  document.body.appendChild(c);
  document.addEventListener('mousemove', e => { c.style.left = e.clientX+'px'; c.style.top = e.clientY+'px'; }, true);
  document.addEventListener('mousedown', e => { const r=document.createElement('div'); r.className='__rip';
    r.style.left=e.clientX+'px'; r.style.top=e.clientY+'px'; document.body.appendChild(r); setTimeout(()=>r.remove(),600); }, true);
}
"""


class Demo:
    def __init__(self, page):
        self.p = page
        self.mx, self.my = VIEW_W / 2, VIEW_H / 2

    async def overlay(self):
        await self.p.evaluate(OVERLAY_JS)
        await self.p.mouse.move(self.mx, self.my)

    async def chapter(self, text):
        await self.p.evaluate(
            """t => { let e = document.getElementById('__chap'); if (!e) { e = document.createElement('div');
               e.id='__chap'; document.body.appendChild(e);} e.textContent = t; }""", text)

    async def nudge(self, dx=30, dy=18):
        """Move the cursor a little; static DOM changes may not emit a screencast frame otherwise."""
        await self.p.mouse.move(self.mx + dx, self.my + dy, steps=10)
        self.mx, self.my = self.mx + dx, self.my + dy

    async def move_to(self, loc, steps=24):
        try:
            await loc.scroll_into_view_if_needed(timeout=5_000)
            box = await loc.bounding_box()
        except Exception as exc:  # noqa: BLE001 - a missing element shouldn't abort a 5-minute recording
            print(f"    (skipped cursor move: {str(exc).splitlines()[0][:80]})", flush=True)
            return
        if not box:
            return
        x, y = box["x"] + min(box["width"] / 2, 70), box["y"] + box["height"] / 2
        await self.p.mouse.move(x, y, steps=steps)
        self.mx, self.my = x, y
        await asyncio.sleep(0.15)

    async def move_xy(self, x, y, steps=20):
        await self.p.mouse.move(x, y, steps=steps)
        self.mx, self.my = x, y

    async def click(self, loc):
        await self.move_to(loc)
        await loc.click()
        await asyncio.sleep(0.4)

    async def type_into(self, loc, text, delay=45):
        await self.click(loc)
        await loc.press_sequentially(text, delay=delay)

    async def spot(self, *locs):
        await self.unspot()
        for loc in locs:
            await loc.evaluate("e => e.classList.add('__spot')")
        await self.nudge()

    async def unspot(self):
        await self.p.evaluate("document.querySelectorAll('.__spot').forEach(e => e.classList.remove('__spot'))")


# --------------------------------------------------------------------------- script
def build_steps(d: Demo):
    p = d.p
    sidebar = lambda: p.get_by_test_id("stSidebar")  # noqa: E731
    messages = lambda: p.get_by_test_id("stChatMessage")  # noqa: E731

    async def slide(content):
        await p.set_content(content)
        await d.overlay()

    def tab(name):
        return p.get_by_role("tab", name=name, exact=True)

    async def show_title():
        await slide(TITLE)

    async def open_and_login():
        await p.goto(UI)
        user = p.get_by_role("textbox", name="Username", exact=True)
        await user.wait_for(timeout=60_000)
        await asyncio.sleep(0.6)
        await d.overlay()
        await d.chapter(f"1 · Live demo · localhost:{UI_PORT}")
        await asyncio.sleep(1.2)
        await d.type_into(user, USERNAME, delay=70)
        await d.type_into(p.get_by_role("textbox", name="Password", exact=True), PASSWORD, delay=50)
        await d.click(p.get_by_role("button", name="Log in"))
        await tab("💬 Ask the Chef").wait_for(timeout=30_000)
        await asyncio.sleep(0.8)
        await d.overlay()
        await d.chapter("1 · Live demo")

    async def sidebar_tour():
        status = sidebar().get_by_text("AI model")
        await d.spot(status.locator("xpath=ancestor::div[@data-testid='stMarkdownContainer'][1]"))
        await d.move_to(status)
        await asyncio.sleep(3.0)
        await d.spot(sidebar().get_by_test_id("stMetric").first.locator("xpath=../.."))
        await d.move_to(sidebar().get_by_test_id("stMetric").first)
        await asyncio.sleep(2.5)
        await d.unspot()
        await d.click(sidebar().get_by_text("Vegetarian", exact=True))
        await d.nudge()

    async def ask_q1():
        box = p.get_by_test_id("stChatInputTextArea")
        await d.type_into(box, Q1, delay=40)
        await asyncio.sleep(0.3)
        await box.press("Enter")
        await messages().nth(1).get_by_test_id("stExpander").first.wait_for(timeout=180_000)
        await asyncio.sleep(0.5)
        await d.overlay()
        await d.chapter("1 · Live demo · grounded answer")

    async def show_answer():
        msg = messages().nth(1)
        await d.spot(msg)
        await d.move_to(msg.get_by_test_id("stMarkdownContainer").first)
        await asyncio.sleep(3.5)
        exp = msg.get_by_test_id("stExpander").first
        await d.click(exp.locator("summary"))
        await asyncio.sleep(0.8)
        await d.spot(exp)
        await d.move_to(exp.locator("summary"))
        await asyncio.sleep(1.0)
        await p.mouse.wheel(0, 260)
        await d.nudge(-20, 10)

    async def ask_q2():
        await d.unspot()
        await d.click(messages().nth(1).get_by_test_id("stExpander").first.locator("summary"))
        box = p.get_by_test_id("stChatInputTextArea")
        await d.type_into(box, Q2, delay=45)
        await asyncio.sleep(0.3)
        await box.press("Enter")
        await p.get_by_text("couldn't find a recipe in the collection").wait_for(timeout=60_000)
        await asyncio.sleep(0.4)
        await d.overlay()
        await d.chapter("1 · Live demo · guardrail")

    async def show_guardrail():
        msg = messages().last
        await msg.scroll_into_view_if_needed()
        await d.spot(msg)
        await d.move_to(msg.get_by_text("couldn't find a recipe"))

    async def open_soup():
        await d.unspot()
        await d.click(tab("📖 My Recipes"))
        await asyncio.sleep(0.8)
        await d.chapter("1 · Live demo · CRUD")
        select = p.get_by_test_id("stSelectbox").filter(has_text="Pick a recipe")
        await d.click(select)
        await asyncio.sleep(0.4)
        await d.click(p.get_by_role("option", name=SOUP))
        await p.get_by_role("heading", name=SOUP).wait_for(timeout=20_000)
        await asyncio.sleep(0.6)
        await d.overlay()
        tags = p.get_by_role("heading", name=SOUP).locator("xpath=ancestor::div[@data-testid='stVerticalBlock'][1]") \
            .get_by_test_id("stMarkdownContainer").filter(has_text="vegetarian").first
        await d.spot(tags)
        await d.move_to(tags.get_by_text("vegan", exact=True))

    async def edit_soup():
        await d.unspot()
        await d.click(tab("Edit / delete"))
        await asyncio.sleep(1.0)
        grid = p.get_by_test_id("stDataFrame").first
        await grid.evaluate("e => e.scrollIntoView({block: 'center'})")
        await asyncio.sleep(0.6)
        await d.move_to(grid)
        # Type into the grid's trailing empty row: editing it appends a new row.
        box = await grid.bounding_box()
        row_h = 35
        n_rows = round((box["height"] - row_h) / row_h)  # data rows + the trailing empty row
        y = box["y"] + row_h + (n_rows - 1) * row_h + row_h / 2
        x_name, x_amt = box["x"] + 33 + 120, box["x"] + box["width"] * 0.6
        await d.move_xy(x_name, y)
        await p.mouse.dblclick(x_name, y)
        await asyncio.sleep(0.4)
        await p.keyboard.type("bacon", delay=90)
        await p.keyboard.press("Enter")
        await asyncio.sleep(0.4)
        await d.move_xy(x_amt, y)
        await p.mouse.dblclick(x_amt, y)
        await asyncio.sleep(0.4)
        await p.keyboard.type("4 rashers", delay=80)
        await p.keyboard.press("Enter")
        await asyncio.sleep(0.3)
        await p.keyboard.press("Escape")  # clear the grid's (red) cell selection
        await asyncio.sleep(0.4)
        await d.move_to(p.get_by_text("Auto-detect diet tags from ingredients"))

    async def save_soup():
        await d.click(p.get_by_role("button", name="Save changes"))
        await p.get_by_role("tab", name="View", exact=True).wait_for(timeout=30_000)
        await asyncio.sleep(1.5)
        await d.click(p.get_by_role("tab", name="View", exact=True))
        await asyncio.sleep(0.8)
        await p.mouse.wheel(0, -2000)
        await asyncio.sleep(0.4)
        await d.overlay()
        heading = p.get_by_role("heading", name=SOUP)
        tags = heading.locator("xpath=ancestor::div[@data-testid='stVerticalBlock'][1]") \
            .get_by_test_id("stMarkdownContainer").filter(has_text="dairy-free").first
        await d.spot(tags)
        await d.move_to(tags)
        await asyncio.sleep(2.0)
        await d.move_to(p.get_by_text("4 rashers bacon"))

    async def plan():
        await d.unspot()
        await d.click(tab("🗓️ Meal Plan"))
        await asyncio.sleep(0.8)
        await d.chapter("1 · Live demo · meal plan")
        await d.type_into(
            p.get_by_role("textbox", name="Ingredients you already have (comma-separated)"), ON_HAND, delay=45)
        await d.click(p.get_by_role("button", name="Plan my meals"))
        await p.get_by_role("heading", name="3-day plan").first.wait_for(timeout=240_000)
        await asyncio.sleep(0.6)
        await d.overlay()
        heading = p.get_by_role("heading", name="3-day plan").first
        await heading.scroll_into_view_if_needed()
        await d.move_to(heading)

    async def shopping():
        head = p.get_by_role("heading", name="Shopping list")
        await head.scroll_into_view_if_needed()
        await p.mouse.wheel(0, 200)
        await asyncio.sleep(0.4)
        await d.spot(head)
        await d.move_to(head)
        await asyncio.sleep(2.5)
        await d.move_to(p.get_by_text("you already have").first)
        await asyncio.sleep(2.0)
        await d.unspot()
        await d.move_to(p.get_by_role("button", name="Download shopping list"))

    def arch(*ids, chapter=False):
        async def f():
            if chapter:
                await slide(ARCH)
                await d.chapter("2 · Architecture")
                await asyncio.sleep(0.6)
            await p.evaluate("ids => window.focusOn(ids)", list(ids))
            await d.nudge()
        return f

    async def challenge():
        await slide(challenge_page())
        await d.chapter("3 · Hardest problem")
        await asyncio.sleep(0.4)
        await p.evaluate("() => window.grow()")
        await d.nudge()
        await asyncio.sleep(3.5)
        await p.evaluate("() => window.leak()")
        await d.nudge()

    async def tune():
        await asyncio.sleep(1.0)
        await p.evaluate("() => window.tune()")
        await d.nudge()

    def finding(i, first=False):
        async def f():
            if first:
                await slide(FINDINGS)
                await d.chapter("3 · Hardest problem")
                await asyncio.sleep(0.5)
            await p.evaluate("i => { const e=document.getElementById(i); e.classList.remove('dim'); e.classList.add('on'); }", i)
            await d.nudge()
        return f

    def card(i, first=False, delay=0.0):
        async def f():
            if first:
                await slide(IMPROVE)
                await d.chapter("4 · What I'd improve")
            await asyncio.sleep(delay)
            await p.evaluate("i => { const e=document.getElementById(i); e.classList.remove('dim'); e.classList.add('on'); }", i)
            await d.nudge()
        return f

    async def end():
        await p.set_content(END)

    # (narration, action): the action starts with the narration, and the step lasts as long as the clip
    return [
        # ---- intro
        ("Hi! This is my capstone: ForkCast, an AI recipe assistant. You tell it what you've got and what you "
         "can't eat, and it finds real recipes, answers with sources, and plans your week. It's FastAPI, "
         "ChromaDB, Ollama and Streamlit, and the whole thing starts with one docker compose up.", show_title),
        # ---- 1 · live demo
        ("Here's the app, running in Docker. I'll log in. The backend checks my password against a bcrypt hash "
         "and gives me a JWT, and every request after this carries it.", open_and_login),
        ("The sidebar shows live health checks for the API, the AI model, and the search index, with all 790 "
         "recipes embedded. I'll turn on the vegetarian filter. It applies to chat, search, and meal plans.",
         sidebar_tour),
        (f"Let me ask: {Q1} The backend embeds my question, ChromaDB finds the closest vegetarian recipes, and "
         "the local Llama model answers using only those.", ask_q1),
        ("The answer cites recipe numbers, and the backend checks every citation against what was actually "
         "retrieved, so the model can't point to a recipe it wasn't given. Opening a source shows the full "
         "recipe and how closely it matched.", show_answer),
        ("Now something off-topic: explain quantum computing.", ask_q2),
        ("Nothing in the collection is close enough, so the guardrail says so honestly, in under a second. The "
         "language model is never even called.", show_guardrail),
        ("Next, a CRUD operation on my own recipe: Grandma's lentil soup. When I saved it, ForkCast read the "
         "ingredients and tagged it vegan, vegetarian, gluten-free, and dairy-free.", open_soup),
        ("I'll edit it and add a row: bacon, four rashers. Auto-detect is on, so the tags will be worked out "
         "again from the new ingredients.", edit_soup),
        ("I save, and it's no longer vegan or vegetarian. The update also re-indexes the recipe, so it drops out "
         "of vegetarian searches straight away.", save_soup),
        ("Last, the meal planner. I tell it what's already in my kitchen. The model can only pick from recipes "
         "the search actually found. Any recipe number it makes up is thrown away.", plan),
        ("And the shopping list is built in plain Python from the real ingredients, leaving out what I already "
         "have. I can download it as a checklist.", shopping),
        # ---- 2 · architecture
        ("Here's the architecture. Two containers. The Streamlit frontend only talks to the FastAPI backend, over "
         "HTTP with the JWT, using the service name backend, not localhost.",
         arch("b-user", "a-user", "b-fe", "a-fe", "b-be", "z-docker", chapter=True)),
        ("The backend keeps users, recipes, diet tags and meal plans in SQLite through SQLAlchemy: six related "
         "tables, including a many-to-many between recipes and tags. ChromaDB runs embedded, and both live in one "
         "Docker volume, so the data survives restarts.",
         arch("b-be", "v-db", "v-vs", "b-db", "b-vs", "z-vol")),
        ("Ollama runs natively on my Mac, because Docker on a Mac can't use the GPU. The backend reaches it "
         "through host dot docker dot internal. Every endpoint validates with Pydantic, and 81 tests run without "
         "the model, using a fake client.", arch("b-be", "a-ol", "b-ol", "z-host", "foot")),
        ("docker compose up builds both images and starts the backend first. The frontend waits for its health "
         "check. On the very first start, the backend loads the recipes and indexes them in the background, and "
         "if Ollama isn't running yet, it retries every thirty seconds until it is.",
         arch("z-docker", "b-fe", "b-be", "z-vol", "b-db", "b-vs")),
        # ---- 3 · hardest problem
        ("The hardest problem was making the guardrail trustworthy. My first threshold, 0.5, was a guess. With "
         "the real model, 'how do I change a car tire' slipped through.", challenge),
        ("To diagnose it, I wrote a small script that sends twenty real questions to the search endpoint, and "
         "prints how far each one is from its closest recipe. Here are some of the results.", None),
        ("So I measured instead of guessing. Cooking questions scored between 0.19 and 0.39, and off-topic ones "
         "between 0.42 and 0.53. So the cut-off is 0.41, right in the gap.", tune),
        ("Live testing caught two more things. The small model writes its citations in parentheses, so I made the "
         "parser accept both styles.", finding("f1", first=True)),
        ("And my diet tagger found fourteen recipes that TheMealDB labels vegetarian, but that actually contain "
         "chicken stock, lard, or bacon.", finding("f2")),
        # ---- 4 · improvements
        ("With more time, I'd add four things. First, streaming. Right now you wait three to six seconds for the "
         "whole answer. Streaming would show the first words almost instantly.", card("k1", first=True, delay=0.8)),
        ("Second, hybrid search: keyword search next to the vectors, plus a reranker, so exact ingredient names "
         "like harissa always match, even when the meaning search misses them.", card("k2")),
        ("Third, nutrition estimates, shared meal plans, and PostgreSQL with an admin role, so it can grow into a "
         "real multi-user app.", card("k3")),
        ("And fourth, an evaluation set: thirty questions with the recipes they should find, run on every push, "
         "so a change to the prompt or the threshold can't quietly make the answers worse.", card("k4")),
        ("Thanks for watching!", end),
    ]


def narration_lines():
    """The narration lines, in order (used by record_narration.py too)."""
    return [s[0] for s in build_steps(Demo(None))]


# --------------------------------------------------------------------------- audio
# Readable script text -> how macOS `say` needs it spelled (only used without --narration)
SAY_FIXES = [
    ("0.19", "point one nine"), ("0.39", "point three nine"), ("0.42", "point four two"),
    ("0.53", "point five three"), ("0.41", "point four one"), ("0.5,", "point five,"),
    ("FastAPI", "Fast A P I"), ("ChromaDB", "Chroma D B"), ("SQLAlchemy", "sequel alchemy"),
    ("SQLite", "sequel light"), ("PostgreSQL", "postgres Q L"), ("TheMealDB", "the meal D B"),
    ("JWT", "J W T"), ("CRUD", "crud"), ("HTTP", "H T T P"), ("bcrypt", "B crypt"),
    ("Ollama", "Oh llama"), ("Pydantic", "Pie dantic"), ("ForkCast", "Fork Cast"),
]


def spoken(text):
    for a, b in SAY_FIXES:
        text = text.replace(a, b)
    return text


def duration(path):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).decode())


def tts(i, text):
    aiff, wav = AUDIO / f"{i:02d}.aiff", AUDIO / f"{i:02d}.wav"
    subprocess.run(["say", "-v", VOICE, "-r", RATE, "-o", str(aiff), spoken(text)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "48000", "-ac", "2", str(wav)], check=True)
    return wav, duration(wav)


# Trim silence at both ends, remove rumble and light background hiss, even out loudness
VOICE_FILTER = (
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,"
    "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,areverse,"
    "highpass=f=80,afftdn=nr=10,loudnorm=I=-16:TP=-1.5:LRA=11"
)


def find_clip(folder: Path, n: int):
    """Clip for line n (1-based): 01.wav / 01.m4a / 01.mp3 / ..."""
    hits = sorted(p for p in folder.glob(f"{n:02d}.*") if p.suffix.lower() in {".wav", ".m4a", ".mp3", ".aiff", ".caf"})
    return hits[0] if hits else None


def prepare_clip(i, src: Path):
    wav = AUDIO / f"{i:02d}.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", VOICE_FILTER,
                    "-ar", "48000", "-ac", "2", str(wav)], check=True)
    return wav, duration(wav)


# --------------------------------------------------------------------------- stack checks + demo data
def api(method, path, token=None, body=None, form=None, timeout=60):
    """Small JSON client for preparing the demo account."""
    headers = {}
    data = None
    if body is not None:
        data, headers["content-type"] = json.dumps(body).encode(), "application/json"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["content-type"] = "application/x-www-form-urlencoded"
    if token:
        headers["authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def prepare_stack():
    """Check the stack is healthy, reset the demo account's data, and warm up the model."""
    try:
        health = api("GET", "/health", timeout=10)
        urllib.request.urlopen(f"{UI}/_stcore/health", timeout=10)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"The stack isn't reachable ({exc}). Run `docker compose up -d` in {PROJECT} first.")
    if health["status"] != "ok" or health["indexed_recipes"] < 700:
        sys.exit(f"Backend is not ready yet (wait for indexing to finish): {health}")

    try:
        api("POST", "/auth/register", body={"username": USERNAME, "password": PASSWORD})
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise
    token = api("POST", "/auth/token", form={"username": USERNAME, "password": PASSWORD})["access_token"]
    for r in api("GET", "/recipes?mine=true&limit=100", token)["items"]:
        api("DELETE", f"/recipes/{r['id']}", token)
    soup = api("POST", "/recipes", token, body=SOUP_BODY)
    for plan in api("GET", "/meal-plans", token):
        api("DELETE", f"/meal-plans/{plan['id']}", token)
    print(f"demo account reset: {SOUP} #{soup['id']} tags={soup['tags']}")

    # Warm the model so the first on-camera answer doesn't include model load time
    api("POST", "/ask", token, body={"question": "a quick vegetarian dinner", "tags": ["vegetarian"]}, timeout=300)
    print("stack ready, model warm")


# --------------------------------------------------------------------------- capture + assemble
async def warm_up(browser):
    """Load the app once so Streamlit's first (slow) script run happens off camera."""
    page = await browser.new_page()
    await page.goto(UI)
    await page.get_by_role("textbox", name="Username", exact=True).wait_for(timeout=60_000)
    await page.close()


async def record(durations):
    frames = []  # (timestamp, path)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        await warm_up(browser)
        ctx = await browser.new_context(viewport={"width": VIEW_W, "height": VIEW_H}, device_scale_factor=SCALE)
        page = await ctx.new_page()
        page.set_default_timeout(30_000)
        cdp = await ctx.new_cdp_session(page)

        def on_frame(ev):
            path = FRAMES / f"f{len(frames):06d}.jpg"
            path.write_bytes(base64.b64decode(ev["data"]))
            frames.append((ev["metadata"]["timestamp"], path))
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}))

        cdp.on("Page.screencastFrame", on_frame)
        await page.set_content(page_html_blank())
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080})
        await asyncio.sleep(0.6)

        d = Demo(page)
        starts = []
        t0 = time.time()
        for i, (_text, action) in enumerate(build_steps(d)):
            start = time.time()
            starts.append(start)
            print(f"[{start - t0:6.1f}s] step {i + 1:02d} ({durations[i]:.1f}s audio)", flush=True)
            if action:
                await action()
            wait = start + durations[i] + GAP - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
            else:
                print(f"    action ran {-wait:.1f}s past narration", flush=True)
        await asyncio.sleep(2.0)
        end_ts = time.time()
        await cdp.send("Page.stopScreencast")
        await browser.close()
    return frames, starts, end_ts


def page_html_blank():
    return page("")


def assemble(frames, starts, end_ts, wavs, final: Path):
    first = next((i for i, (ts, _) in enumerate(frames) if ts >= starts[0] - 0.05), 0)
    frames = frames[max(first - 1, 0):]
    origin = starts[0]
    lst = OUT / "frames.txt"
    with lst.open("w") as f:
        for i, (ts, path) in enumerate(frames):
            nxt = frames[i + 1][0] if i + 1 < len(frames) else end_ts
            dur = max(nxt - max(ts, origin), 0.001) if i == 0 else max(nxt - ts, 0.001)
            f.write(f"file '{path}'\nduration {dur:.4f}\n")
        f.write(f"file '{frames[-1][1]}'\n")

    inputs, filters = [], []
    for i, (wav, s) in enumerate(zip(wavs, starts)):
        inputs += ["-i", str(wav)]
        ms = int(max(s - origin, 0) * 1000)
        filters.append(f"[{i + 1}:a]adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(wavs)))
    filters.append(f"{mix}amix=inputs={len(wavs)}:normalize=0,apad[aout]")
    total = end_ts - origin
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), *inputs,
           "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]",
           "-vf", "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-tune", "stillimage",
           "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(final)]
    subprocess.run(cmd, check=True)
    print(f"wrote {final} ({int(total // 60)}:{int(total % 60):02d})")


async def main():
    ap = argparse.ArgumentParser(description="Record the narrated presentation video.")
    ap.add_argument("output", nargs="?", default=str(HERE / "forkcast_presentation.mp4"), help="output .mp4 path")
    ap.add_argument("--narration", metavar="DIR",
                    help="folder of recorded clips 01.wav, 02.wav, ... (wav/m4a/mp3); omit to use macOS `say`")
    args = ap.parse_args()
    final = Path(args.output).resolve()

    for folder in (FRAMES, AUDIO):
        folder.mkdir(parents=True, exist_ok=True)
        for f in folder.iterdir():
            f.unlink()
    lines = narration_lines()
    if args.narration:
        folder = Path(args.narration).resolve()
        clips = [find_clip(folder, i + 1) for i in range(len(lines))]
        missing = [i + 1 for i, c in enumerate(clips) if c is None]
        if missing:
            sys.exit(f"Missing clips in {folder} for lines: {missing}. Run record_narration.py first.")
        wavs, durs = zip(*(prepare_clip(i, c) for i, c in enumerate(clips)))
    else:
        wavs, durs = zip(*(tts(i, t) for i, t in enumerate(lines)))
    print(f"narration total: {sum(durs) + GAP * len(durs):.1f}s for {len(lines)} lines")

    prepare_stack()
    frames, starts, end_ts = await record(durs)
    print(f"captured {len(frames)} frames")
    assemble(frames, starts, end_ts, wavs, final)


if __name__ == "__main__":
    asyncio.run(main())
