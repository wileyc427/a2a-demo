# A2A Demo — Solar Project Negotiation Pipeline

A multi-agent demo using the [A2A SDK](https://github.com/google-a2a/a2a-python). A Solar Developer and an Underwriter negotiate a utility-scale solar project across multiple turns, communicating as real professionals would.

## What it does

Given a solar development idea, the pipeline runs a dynamic multi-turn negotiation (up to 10 turns). The orchestrator alternates between agents, passing the conversation history each time. The negotiation ends early when either agent signals agreement or a definitive outcome.

```
Solar Negotiation Orchestrator    (pipeline root — sequential, max 10 turns)
  ├── Solar Developer             port 8001
  └── Underwriter                 port 8002
```

## Cost warning

Each demo run makes multiple API calls to Claude — one per turn, up to 10 turns. Based on real usage, **a single run costs approximately $0.09** using `claude-haiku-4-5`. Costs will be higher if you switch to a more capable model like Sonnet or Opus. These charges are billed directly to your Anthropic account. Monitor your usage at [console.anthropic.com](https://console.anthropic.com).

## Prerequisites

- Python 3.10+ — check with `python3 --version`
- An Anthropic API key — sign up at [console.anthropic.com](https://console.anthropic.com), then go to **API Keys** and click **Create Key**. Copy the key — it starts with `sk-ant-` and is only shown once.

## Getting the project

The easiest way is to download it as a ZIP file — no developer tools required:

1. Go to the project page on GitHub
2. Click the green **Code** button near the top right
3. Click **Download ZIP**
4. Unzip the downloaded file — this creates a folder called `a2a-demo` on your computer
5. Open a terminal and navigate into that folder:
   ```bash
   cd ~/Downloads/a2a-demo-main
   ```

That's it — you're ready to run the demo.

## Quickstart

**1. Open a terminal and navigate to the project folder.** If you downloaded the ZIP, it will typically be in your Downloads folder:

```bash
cd ~/Downloads/a2a-demo-main
```

All commands below must be run from inside this folder.

**2. Write your project idea to `prompt.md`:**

```
prompt.md
─────────
150MW solar farm on brownfield land in West Texas
```

**3. Open two terminal windows.** In the first terminal, navigate to the project folder and start all services:

```bash
bash start.sh sk-ant-...
```

Leave this terminal running — it hosts the agents and prints progress as each turn completes. Do not close it.

**4. In your second terminal, navigate to the project folder and run the negotiation:**

```bash
python run_demo.py
```

This sends your idea to the orchestrator and waits. When all turns are complete, the full transcript is printed here and written to `transcript.md` in the project root.

## How it works

Each agent uses `claude-haiku-4-5`. The orchestrator passes the conversation history and a `[TURN:N of 10]` marker with each call so the model knows its position. When either agent judges the negotiation complete, it appends `[NEGOTIATION_COMPLETE]` to stop the loop early.

## How the orchestrator works

The orchestrator is the coordinator — it doesn't have opinions or generate responses itself, it just manages the conversation flow between the two agents.

Importantly, the orchestrator is **your code**. It lives in your codebase, you control it, and you decide the rules: which agents to call, in what order, how many turns to allow, and what to do with the results. **The agents themselves, however, can be owned and operated by anyone — they could be services you built, services a partner built, or third-party APIs exposed over the network.** Your orchestrator doesn't need to know or care how an agent works internally; it just sends a message and gets a response back.**For this example, the orchestrator and agents are all owned by one app, but again, this wouldn't be the case, necessarily, in a real scenario.**

Finally, even though all agents are managed by this demo, they all run on their own ports and act as true, individual agents.

When you submit an idea, the orchestrator:

1. Sends the idea to the Solar Developer and waits for a response
2. Takes that response and passes it — along with the original idea — to the Underwriter
3. Takes the Underwriter's response and passes the full conversation so far back to the Solar Developer
4. Keeps alternating like this, adding each new response to the history, until either agent ends the negotiation or 10 turns are reached

Each message sent to an agent includes everything said so far, plus a turn counter (`[TURN:1 of 10]`, `[TURN:2 of 10]`, etc.) so the agent knows how far into the negotiation it is. When an agent decides the negotiation is complete, it includes a `[NEGOTIATION_COMPLETE]` signal in its response and the orchestrator stops the loop.

## What's actually happening

You write down a solar project idea — say, "150MW solar farm on brownfield land in West Texas." From there, two AI agents take over and have a real back-and-forth conversation about it.

The first agent plays the role of a solar project developer. It reads your idea and responds the way an experienced developer would: proposing a specific project with a site, a capacity, a cost estimate, a timeline, and a plan for getting a power purchase agreement signed.

The second agent plays the role of a bank underwriter — the person at a lender who decides whether to finance a project. It reads the developer's proposal and responds the way a real credit professional would: asking hard questions about offtake contracts, interconnection costs, debt coverage ratios, and environmental studies.

The developer then responds to those concerns. The underwriter reviews the answers and either raises more issues or moves toward a conditional approval with financing terms. This goes back and forth — up to 10 rounds — until both sides reach an agreed deal or one side walks away.

Neither agent knows the other's responses in advance. Each one only sees what has been said so far and decides what to say next on its own. The conversation is capped at 10 turns total — if the agents haven't reached a conclusion by then, the negotiation stops automatically. In practice it usually wraps up sooner, because once a deal is agreed both agents signal that they're done and the conversation ends early. When it's over, the full exchange is saved to `transcript.md` so you can read it from start to finish.

## Navigating the project

If you're not a developer, here's what you actually need to care about — and what you can safely ignore.

**The two files you interact with:**

- `prompt.md` — this is where you write your idea. One or two sentences describing the solar project is enough. Change it between runs to try different scenarios.
- `transcript.md` — this is where the output goes. Open it after a run to read the full conversation between the two agents.

**The two files that control how the agents behave:**

- `agents/solar_developer/main.py` — contains the instructions given to the Solar Developer AI. Look for the `SYSTEM_PROMPT` block near the top. You can edit the text there to change how the developer personality behaves — more aggressive on leverage, more conservative on timelines, whatever you want.
- `agents/underwriter/main.py` — same thing for the Underwriter. Edit `SYSTEM_PROMPT` to make the bank tougher, more flexible, focused on different risk factors, etc.

**Everything else** — the orchestrator, `run_demo.py`, `start.sh`, `docker-compose.yml`, `requirements.txt` — is plumbing that makes the agents talk to each other. You don't need to touch any of it to run the demo or change how the agents behave.

## Project structure

```
prompt.md                          # Write your project idea here (you create this)
transcript.md                      # Full negotiation transcript (written after each run)
orchestrator/main.py               # Pipeline root — drives the negotiation loop
agents/solar_developer/main.py     # Solar Developer agent (port 8001)
agents/underwriter/main.py         # Underwriter agent (port 8002)
run_demo.py                        # Demo runner CLI
start.sh                           # Starts all services locally (accepts API key as $1)
Dockerfile                         # Single image used by all three services
docker-compose.yml                 # Runs all three services via Docker
requirements.txt                   # Python dependencies
```
