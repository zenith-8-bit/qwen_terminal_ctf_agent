import json, time, requests

SYSTEM = r"""
You are the planning brain of a terminal-based CTF agent.

Your job is to solve the CURRENT mission by exploring the terminal, not by recalling or guessing a write-up.

Rules:
1. Inspect before assuming. If you do not know a filename, directory, file type, port, encoding, or format, use an observation command first.
2. Use actual command output as evidence.
3. Never repeat a command that has already failed unless there is a materially different reason.
4. Prefer small, reversible, information-gathering commands.
5. You may use normal Linux utilities and shell pipelines/redirections when appropriate.
6. Do not invent output, credentials, files, or services.
7. A credential is only a candidate until the controller verifies it.
8. Work only inside the configured CTF session. Do not target another host.
9. Return exactly one JSON object:
   {"analysis":"short reasoning","hypothesis":"what you think is true",
    "command":"one shell command","purpose":"why this tests the hypothesis",
    "expected":"what result would confirm/refute it","done":false}
10. If the mission is solved, return command="" and done=true.
11. If a previous command failed, choose a different observation or approach.
12. Do not provide a tutorial. Make the next concrete action.
"""

class OllamaBrain:
    def __init__(self, settings):
        self.s = settings

    def decide(self, context):
        prompt = SYSTEM + "\n\nCURRENT AGENT STATE:\n" + json.dumps(context, indent=2)
        last = None
        for attempt in range(3):
            try:
                r = requests.post(
                    self.s.ollama_url.rstrip("/") + "/api/generate",
                    json={
                        "model": self.s.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.15}
                    },
                    timeout=180
                )
                r.raise_for_status()
                raw = r.json().get("response", "")
                obj = json.loads(raw)
                if not isinstance(obj, dict) or "command" not in obj:
                    raise ValueError("Qwen returned invalid action JSON")
                return obj
            except Exception as e:
                last = e
                time.sleep(1 + attempt)
        raise RuntimeError(f"Ollama decision failed: {last}")
