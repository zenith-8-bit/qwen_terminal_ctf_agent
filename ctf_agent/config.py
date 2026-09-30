import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass
class Settings:
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    host: str = os.getenv("CTF_HOST", "bandit.labs.overthewire.org")
    port: int = int(os.getenv("CTF_PORT", "2220"))
    user: str = os.getenv("CTF_USER", "bandit0")
    password: str = os.getenv("CTF_PASSWORD", "bandit0")
    mission: str = os.getenv("CTF_MISSION", "Explore the current CTF environment and find the credential needed to advance.")
    max_steps: int = int(os.getenv("MAX_STEPS", "40"))
    timeout: int = int(os.getenv("COMMAND_TIMEOUT", "20"))
    max_output: int = int(os.getenv("MAX_COMMAND_OUTPUT", "12000"))
    web_host: str = os.getenv("WEB_HOST", "127.0.0.1")
    web_port: int = int(os.getenv("WEB_PORT", "8787"))
