# Run and test the local interface

The app now has one browser address: `http://127.0.0.1:7861`.

## Start from a clean terminal

Run the web application in terminal 1:

```bash
source .venv/bin/activate
python app.py 2>&1 | tee -a data/logs/main-app.log
```

Run the LiveKit voice agent in terminal 2:

```bash
source .venv/bin/activate
python -m loose_ends.voice_agent start 2>&1 | tee -a data/logs/voice-agent.log
```

Then open `http://127.0.0.1:7861`. There is no port 7862 page and no embedded review application.

## First-use path

1. Open **Talk** and press **Start talking**.
2. Have a natural conversation and correct the companion when needed.
3. When the plan sounds right, say **“make a draft.”**
4. To refine it, keep speaking: for example, **“Actually, change the deadline to Friday.”** The same pending draft is revised.
5. Press **End conversation**. The app opens **Review** when the draft is ready.
6. Inspect the draft, select **Approve & add to board**, and track it from **Board**.

Talk intentionally contains no transcript or typed composer. You can use the persistent Talk, Review, and Board navigation at any time. If ending does not find a draft, return to the conversation and explicitly ask for one.

## Rebuild the browser assets after frontend changes

```bash
cd voice-ui
npm install
npm run build
cd ..
```

Restart `python app.py` after rebuilding. The LiveKit agent only needs a restart when its Python code or environment changes.

## Health and logs

```bash
curl http://127.0.0.1:7861/api/health
tail -f data/logs/main-app.log
tail -f data/logs/voice-agent.log
```

`ready: true` confirms the web process can see the Groq and LiveKit configuration. Agent registration still appears in `voice-agent.log`.

## Documentation preview

Open the repository in VS Code and press Ctrl+Shift+V on a Markdown file. Mermaid support may need to be enabled in the installed editor version. The SVGs under `docs/wireframes/` are retained as historical sketches; the browser application is the current UI reference.
