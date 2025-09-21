🤖 Coral CFO — Autonomous Subscription Audit Agent
Coral CFO is an autonomous AI agent built on Coral Server that analyzes recurring subscriptions and turns messy billing data into immediate, actionable finance recommendations.
What it does

Ingests subscription data (CSV)
Normalizes & scores each subscription (keep vs cancel)
Produces prioritized cancellation / negotiation recommendations
Optionally augments suggestions with LLM-generated, JSON-formatted next steps
Streams live logs and results to a lightweight web dashboard


🔧 Project layout
project-root/
├── coral-server/           # Coral Protocol server + agents (Java/Kotlin)
│   └── ...                # run with ./gradlew run
└── website/               # Flask + static dashboard
    ├── microser.py        # Python microservice (creates session on Coral)
    ├── index.html         # Frontend dashboard (streams logs)
    └── session-template.json

🚀 Quick start

Make sure you run each step in a separate terminal / VS Code window.

1) Start Coral Server
bashcd coral-server
./gradlew run
This launches Coral on: http://127.0.0.1:5555
2) Start the website microservice
bashcd website
python microser.py
This starts the Flask app at: http://127.0.0.1:5000
3) Open the dashboard
Open your browser and go to: http://127.0.0.1:5000
You should see:

✅ Connection status to the Coral CFO agent
📊 First 5 transactions
🔎 Scored subscriptions (keep vs cancel)
❌ Cancellation recommendations
🤖 AI suggested actions (if LLM enabled)
📌 Suggested next steps

🧠 How it works (high level)

Frontend requests /search from microser.py.
microser.py posts a session template to Coral (/api/v1/sessions) and returns the session id.
Frontend opens a WebSocket to Coral debug logs for that session (live stream).
The CFO agent (executable runtime inside Coral) reads subscriptions.csv, runs deterministic heuristics, and optionally calls an LLM for human-friendly next steps.
The agent emits logs — frontend parses them and displays realtime recommendations.

🛠️ Tech stack

Coral Protocol — agent runtime & orchestration
Java / Kotlin — Coral server runtime
Python (Flask) — microser.py to create sessions and bootstrap the frontend
HTML / JavaScript / CSS — lightweight real-time dashboard
Pandas — CSV parsing & heuristics (agent code)

✅ Troubleshooting

Blank dashboard / "Disconnected"

Ensure Coral Server is running (http://127.0.0.1:5555).
Ensure you started microser.py (Flask) on port 5000.
Open DevTools (Console & Network). Look for WebSocket errors or the /search POST response.
If session IDs change after Coral restart, refresh the dashboard — it will request a new session.


304 / cached page

304 is normal caching behavior. Force-reload (Shift+Refresh) only to ensure you have the latest client when debugging.


LLM explanations missing

LLM augmentation runs only if the agent has network access / API key configured (Gemini in your code).
The agent will still produce heuristic recommendations if LLM is unavailable.



📌 Notes & next steps

This repo is a hackathon demo and a blueprint — not yet production hardened.
Future improvements: S3 / direct billing connectors, user CSV upload, registry-based remote agents, authentication, persistent sessions and audit logs.

🙋 Contact / Author
Muhammad Awais
https://www.linkedin.com/in/awaisstack/
