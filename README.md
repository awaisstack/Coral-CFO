# CFO Agent — Subscription Audit

A lightweight tool to analyze company subscriptions, generate cancellation recommendations, and provide AI-assisted next steps. Built using a Python microservice, Coral Studio orchestration, and a live dashboard.

---

## Features
- Reads CSV subscription data and computes usage, cost, and recency scores.  
- Identifies subscriptions to **cancel** or **keep** with reasoning.  
- Generates **AI-assisted explanations and next steps** using Gemini API (optional).  
- Streams logs in real-time to a **dashboard** via WebSocket.  

---

## Prerequisites
1. [Coral Studio](https://coral.ai) (must be installed and imported in a separate Visual Studio instance).  
2. Python 3.10+ with packages:  
```bash
pip install pandas websockets python-dotenv



