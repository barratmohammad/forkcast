# ForkCast: 5-minute capstone presentation script

This is the narration for `forkcast_presentation.mp4`. The numbers match the clips that
`record_narration.py` records (`narration/01.wav`, `02.wav`, ...), so you can redo any single line.
For a live presentation, read the same lines while you click through the app.

**To make the video in your own voice:**

```bash
docker compose up -d                                # in the project root; the video drives the running app
cd presentation
.venv/bin/python record_narration.py --test-mic     # check the mic first
.venv/bin/python record_narration.py                # record each line (Enter to start/stop)
.venv/bin/python make_demo.py --narration narration
```

First-time setup of the recording environment (already done on this Mac):

```bash
cd presentation && uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/playwright install chromium
```

Before recording, `make_demo.py` resets the `demo` account through the API (a fresh vegan
"Grandma's Lentil Soup", no meal plans) and warms up the model.

**Demo inputs:** diet filter *Vegetarian* · question *"I have chickpeas, spinach and rice. What can I
make tonight?"* · off-topic *"Explain quantum computing"* · edit: add *bacon, 4 rashers* · meal plan
on-hand: *chickpeas, spinach, rice*.

## Intro (~15 s)

**01.** Hi! This is my capstone: ForkCast, an AI recipe assistant. You tell it what you've got and what you can't eat, and it finds real recipes, answers with sources, and plans your week. It's FastAPI, ChromaDB, Ollama and Streamlit, and the whole thing starts with one docker compose up.

## 1. Live demo (~2 min)

**02.** Here's the app, running in Docker. I'll log in. The backend checks my password against a bcrypt hash and gives me a JWT, and every request after this carries it.

**03.** The sidebar shows live health checks for the API, the AI model, and the search index, with all 790 recipes embedded. I'll turn on the vegetarian filter. It applies to chat, search, and meal plans.

**04.** Let me ask: I have chickpeas, spinach and rice. What can I make tonight? The backend embeds my question, ChromaDB finds the closest vegetarian recipes, and the local Llama model answers using only those.

**05.** The answer cites recipe numbers, and the backend checks every citation against what was actually retrieved, so the model can't point to a recipe it wasn't given. Opening a source shows the full recipe and how closely it matched.

**06.** Now something off-topic: explain quantum computing.

**07.** Nothing in the collection is close enough, so the guardrail says so honestly, in under a second. The language model is never even called.

**08.** Next, a CRUD operation on my own recipe: Grandma's lentil soup. When I saved it, ForkCast read the ingredients and tagged it vegan, vegetarian, gluten-free, and dairy-free.

**09.** I'll edit it and add a row: bacon, four rashers. Auto-detect is on, so the tags will be worked out again from the new ingredients.

**10.** I save, and it's no longer vegan or vegetarian. The update also re-indexes the recipe, so it drops out of vegetarian searches straight away.

**11.** Last, the meal planner. I tell it what's already in my kitchen. The model can only pick from recipes the search actually found. Any recipe number it makes up is thrown away.

**12.** And the shopping list is built in plain Python from the real ingredients, leaving out what I already have. I can download it as a checklist.

## 2. Architecture (~1 min)

**13.** Here's the architecture. Two containers. The Streamlit frontend only talks to the FastAPI backend, over HTTP with the JWT, using the service name backend, not localhost.

**14.** The backend keeps users, recipes, diet tags and meal plans in SQLite through SQLAlchemy: six related tables, including a many-to-many between recipes and tags. ChromaDB runs embedded, and both live in one Docker volume, so the data survives restarts.

**15.** Ollama runs natively on my Mac, because Docker on a Mac can't use the GPU. The backend reaches it through host dot docker dot internal. Every endpoint validates with Pydantic, and 81 tests run without the model, using a fake client.

**16.** docker compose up builds both images and starts the backend first. The frontend waits for its health check. On the very first start, the backend loads the recipes and indexes them in the background, and if Ollama isn't running yet, it retries every thirty seconds until it is.

## 3. Hardest problem (~1 min)

**17.** The hardest problem was making the guardrail trustworthy. My first threshold, 0.5, was a guess. With the real model, 'how do I change a car tire' slipped through.

**18.** To diagnose it, I wrote a small script that sends twenty real questions to the search endpoint, and prints how far each one is from its closest recipe. Here are some of the results.

**19.** So I measured instead of guessing. Cooking questions scored between 0.19 and 0.39, and off-topic ones between 0.42 and 0.53. So the cut-off is 0.41, right in the gap.

**20.** Live testing caught two more things. The small model writes its citations in parentheses, so I made the parser accept both styles.

**21.** And my diet tagger found fourteen recipes that TheMealDB labels vegetarian, but that actually contain chicken stock, lard, or bacon.

## 4. What I'd improve (~1 min)

**22.** With more time, I'd add four things. First, streaming. Right now you wait three to six seconds for the whole answer. Streaming would show the first words almost instantly.

**23.** Second, hybrid search: keyword search next to the vectors, plus a reranker, so exact ingredient names like harissa always match, even when the meaning search misses them.

**24.** Third, nutrition estimates, shared meal plans, and PostgreSQL with an admin role, so it can grow into a real multi-user app.

**25.** And fourth, an evaluation set: thirty questions with the recipes they should find, run on every push, so a change to the prompt or the threshold can't quietly make the answers worse.

**26.** Thanks for watching!
