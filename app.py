import argparse
from ctf_agent.config import Settings
from ctf_agent.agent import Agent
from ctf_agent.web import create_app


def main():
    p = argparse.ArgumentParser(
        description="General Ollama/Qwen terminal CTF agent"
    )
    sub = p.add_subparsers(dest="mode", required=True)

    run = sub.add_parser("run")
    run.add_argument("--user", default=None, help="Starting SSH username")
    run.add_argument("--password", default=None, help="Starting SSH password")
    run.add_argument("--password-file", default=None)
    run.add_argument("--mission", default=None)
    run.add_argument(
        "--verify-user",
        default=None,
        help="Single-level compatibility mode: verify a candidate against this user",
    )
    run.add_argument(
        "--start-level",
        type=int,
        default=None,
        help="Start Bandit level for automatic progression",
    )
    run.add_argument(
        "--end-level",
        type=int,
        default=None,
        help="Final Bandit level for automatic progression",
    )
    run.add_argument("--max-steps", type=int, default=None)

    sub.add_parser("web")
    args = p.parse_args()

    s = Settings()

    if args.mode == "web":
        create_app(s).run(s.web_host, s.web_port, debug=False)
        return

    password = args.password
    if args.password_file:
        with open(args.password_file, encoding="utf-8") as f:
            password = f.read().strip()

    start_level = args.start_level
    end_level = args.end_level

    if (start_level is None) != (end_level is None):
        p.error("--start-level and --end-level must be supplied together")

    if start_level is not None:
        user = args.user or f"bandit{start_level}"
        if user != f"bandit{start_level}":
            p.error(
                f"--user must be bandit{start_level} when automatic progression is enabled"
            )
    else:
        user = args.user or s.user

    password = password if password is not None else s.password
    mission = args.mission or s.mission
    max_steps = args.max_steps or s.max_steps

    agent = Agent(s)
    agent.run(
        user=user,
        password=password,
        mission=mission,
        verify_user=args.verify_user,
        max_steps=max_steps,
        start_level=start_level,
        end_level=end_level,
    )


if __name__ == "__main__":
    main()
