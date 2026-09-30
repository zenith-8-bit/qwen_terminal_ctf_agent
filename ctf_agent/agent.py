import re
import time
from rich.console import Console
from rich.panel import Panel

from .ssh import SSHExecutor
from .ollama import OllamaBrain
from .state import State
from .policy import validate_command, normalize


class Agent:
    """General terminal CTF agent with optional Bandit-style level progression.

    Qwen chooses the terminal actions. The controller only manages execution,
    credential verification, and (when enabled) moving to the next account.
    """

    def __init__(self, settings):
        self.s = settings
        self.console = Console()
        self.state = State()
        self.brain = OllamaBrain(settings)
        self.ssh = SSHExecutor(settings)

    def candidate_tokens(self, text):
        # Detector only. A token becomes a credential only after verification.
        patterns = [
            r'(?i)(?:password|passwd|pass|credential|token|secret)\s*(?:is|=|:)\s*[\'"]?([A-Za-z0-9_./+=:@$%?~,-]{8,})',
            r'\b[A-Za-z0-9+/=_-]{20,64}\b',
        ]
        found = []
        for pattern in patterns:
            found.extend(re.findall(pattern, text))
        return list(dict.fromkeys(found))

    @staticmethod
    def level_number(user):
        m = re.fullmatch(r"bandit(\d+)", user or "")
        return int(m.group(1)) if m else None

    @staticmethod
    def level_user(level):
        return f"bandit{level}"

    def build_context(self, mission, user, step, observations, failed):
        level = self.level_number(user)
        return {
            "mission": mission,
            "target": {
                "host": self.s.host,
                "port": self.s.port,
                "user": user,
                "level": level,
            },
            "step": step,
            "recent_observations": observations[-10:],
            "failed_or_rejected_commands": failed[-12:],
            "commands_already_attempted": sorted(self.state.seen_commands())[-40:],
            "controller_note": (
                "No solution database is supplied. Discover facts from the terminal. "
                "A credential is only a candidate until the controller verifies it. "
                "Do not assume the challenge solution from memory."
            ),
        }

    def verify(self, username, password):
        if not username or not password:
            return False

        test = SSHExecutor(self.s)
        try:
            test.connect(username, password)
            test.close()
            return True
        except Exception:
            test.close()
            return False

    def _connect(self, user, password, level, mission, event_kind="level_start"):
        self.ssh.close()
        self.ssh = SSHExecutor(self.s)
        self.ssh.connect(user, password)
        self.state.update(
            user=user,
            level=level,
            status="connected",
            mission=mission,
            step=0,
            candidate="",
            command="",
            output="",
        )
        self.state.event(
            0,
            event_kind,
            {"user": user, "level": level, "mission": mission},
        )

    def solve_level(self, user, password, mission, level, max_steps, verify_next=True):
        """Explore one level and return a verified next-level credential.

        Returns:
            (credential, next_user) on success, or (None, None) otherwise.
        """
        observations = []
        failed = []

        try:
            self._connect(user, password, level, mission)

            self.console.print(
                f"[cyan]Level {level}: connected to "
                f"{self.s.host}:{self.s.port} as {user}[/cyan]"
            )

            for step in range(1, max_steps + 1):
                self.state.update(step=step, status="thinking", level=level, user=user)

                context = self.build_context(
                    mission, user, step, observations, failed
                )
                action = self.brain.decide(context)

                analysis = str(action.get("analysis", ""))
                hypothesis = str(action.get("hypothesis", ""))
                command = str(action.get("command", "")).strip()
                done = bool(action.get("done", False))

                self.state.update(
                    plan=analysis,
                    hypothesis=hypothesis,
                    command=command,
                    status="thinking",
                )
                self.state.event(step, "decision", action)

                if done or not command:
                    self.state.update(status="agent_stopped")
                    self.console.print(
                        Panel(
                            analysis or "Agent declared the mission complete.",
                            title=f"Level {level}: stopped",
                        )
                    )
                    return None, None

                ok, reason = validate_command(command)
                norm = normalize(command)

                if not ok:
                    failed.append({"command": command, "reason": reason})
                    self.state.event(
                        step,
                        "rejected_command",
                        {"command": command, "reason": reason},
                    )
                    self.state.update(status="rejected", output=reason)
                    continue

                seen = {normalize(x) for x in self.state.seen_commands()}
                if norm in seen:
                    reason = "duplicate command already attempted"
                    failed.append({"command": command, "reason": reason})
                    self.state.event(
                        step, "duplicate_command", {"command": command}
                    )
                    self.state.update(status="replanning", output=reason)
                    continue

                self.state.update(command=command, status="executing", output="")
                self.state.event(step, "command", {"command": command})

                try:
                    out, err, code = self.ssh.run(command)
                    combined = out
                    if err:
                        combined += "\n[stderr]\n" + err
                    combined = combined[-self.s.max_output:]
                except Exception as exc:
                    combined = f"EXECUTION ERROR: {exc}"
                    code = -1

                observations.append(
                    {
                        "command": command,
                        "exit_code": code,
                        "output": combined,
                    }
                )

                low = combined.lower()
                if (
                    code != 0
                    or "not found" in low
                    or "no such file" in low
                    or "permission denied" in low
                ):
                    failed.append(
                        {"command": command, "reason": combined[-2000:]}
                    )

                self.state.update(status="observed", output=combined)
                self.state.event(
                    step,
                    "output",
                    {
                        "command": command,
                        "exit_code": code,
                        "output": combined,
                    },
                )

                self.console.print(
                    Panel(
                        f"[bold]Level {level} · Step {step}[/bold]  $ {command}\n\n"
                        f"{combined[-6000:]}",
                        title=hypothesis[:80] or "terminal observation",
                    )
                )

                # Candidate discovery is deliberately separated from verification.
                candidates = self.candidate_tokens(combined)
                next_level = level + 1
                next_user = self.level_user(next_level) if verify_next else None

                for candidate in candidates:
                    self.state.update(candidate=candidate, status="candidate")
                    self.state.event(
                        step,
                        "candidate",
                        {"candidate": candidate, "target_user": next_user},
                    )

                    if verify_next and next_user and self.verify(next_user, candidate):
                        self.state.update(
                            status="verified",
                            candidate=candidate,
                            level=level,
                        )
                        self.state.event(
                            step,
                            "verified_credential",
                            {
                                "username": next_user,
                                "source_level": level,
                            },
                        )
                        self.console.print(
                            f"[green]✓ Verified credential for "
                            f"{next_user}[/green]"
                        )
                        return candidate, next_user

                time.sleep(0.15)

            self.state.update(status="max_steps", level=level)
            self.state.event(max_steps, "max_steps", {"level": level})
            return None, None

        except Exception as exc:
            self.state.update(status="level_error", output=str(exc), level=level)
            self.state.event(
                self.state.snapshot().get("step", 0),
                "level_error",
                {"level": level, "error": str(exc)},
            )
            self.console.print(
                Panel(str(exc), title=f"Level {level}: error")
            )
            return None, None
        finally:
            self.ssh.close()

    def run(
        self,
        user,
        password,
        mission,
        verify_user=None,
        max_steps=40,
        start_level=None,
        end_level=None,
    ):
        """Run one level or automatically progress through Bandit levels.

        If start_level/end_level are supplied, users must be banditN accounts.
        The first level uses the supplied starting password. Every subsequent
        level is entered with the credential Qwen discovered and the controller
        successfully verified against bandit(N+1).
        """
        start = start_level
        end = end_level

        if start is None and end is None:
            level = self.level_number(user)
            if level is not None:
                start = level
                end = level
            else:
                start = None
                end = None

        if (start is not None) != (end is not None):
            raise ValueError("--start-level and --end-level must be supplied together")

        if start is None:
            # Backward-compatible single-level/general CTF mode.
            self.state.update(
                user=user,
                level=user,
                status="connecting",
                mission=mission,
                step=0,
            )
            self.state.event(
                0,
                "session_start",
                {"user": user, "mission": mission},
            )

            credential, next_user = self.solve_level(
                user, password, mission, user, max_steps
            )

            # In general mode --verify-user can define the verification target.
            if credential and verify_user:
                if self.verify(verify_user, credential):
                    self.state.update(
                        status="verified",
                        candidate=credential,
                    )
                    self.state.event(
                        self.state.snapshot().get("step", 0),
                        "verified_credential",
                        {"username": verify_user},
                    )
                    self.console.print(
                        f"[green]Verified credential for {verify_user}[/green]"
                    )
                    return credential
            return credential

        if not re.fullmatch(r"bandit\d+", user):
            raise ValueError(
                "Automatic level progression requires a banditN starting user."
            )
        if self.level_number(user) != start:
            raise ValueError(
                f"Starting user {user} does not match --start-level {start}."
            )
        if end < start:
            raise ValueError("--end-level must be >= --start-level")

        current_user = user
        current_password = password

        self.state.update(
            user=current_user,
            level=start,
            status="progression_start",
            mission=mission,
            step=0,
        )
        self.state.event(
            0,
            "progression_start",
            {"start_level": start, "end_level": end},
        )

        for level in range(start, end + 1):
            # Final level only needs to be explored; there is no next account
            # required for completion.
            if level == end:
                final_mission = (
                    f"{mission} This is the final requested level ({level}). "
                    "Determine whether the mission is complete using terminal evidence."
                )
                self.console.print(
                    f"[bold magenta]→ Exploring final requested level {level} "
                    f"as {current_user}[/bold magenta]"
                )

                result, _ = self.solve_level(
                    current_user,
                    current_password,
                    final_mission,
                    level,
                    max_steps,
                    verify_next=False,
                )
                if result:
                    self.state.update(
                        status="completed",
                        level=level,
                        user=current_user,
                        candidate=result,
                    )
                    self.state.event(
                        self.state.snapshot().get("step", 0),
                        "progression_complete",
                        {"level": level, "user": current_user},
                    )
                else:
                    self.state.update(status="final_level_finished", level=level)
                return result

            next_user = self.level_user(level + 1)
            level_mission = (
                f"{mission} You are currently on Bandit level {level}. "
                f"Your immediate progression target is the credential accepted "
                f"by {next_user}. Explore the terminal and discover it from evidence; "
                "do not guess it."
            )

            self.console.print(
                f"\n[bold magenta]→ Level {level}/{end}: {current_user} "
                f"→ discover credential for {next_user}[/bold magenta]"
            )
            self.state.update(
                level=level,
                user=current_user,
                status="exploring_level",
                mission=level_mission,
                step=0,
            )
            self.state.event(
                0,
                "level_progression",
                {
                    "level": level,
                    "user": current_user,
                    "target_user": next_user,
                },
            )

            credential, verified_user = self.solve_level(
                current_user,
                current_password,
                level_mission,
                level,
                max_steps,
            )

            if not credential or verified_user != next_user:
                self.state.update(
                    status="progression_stopped",
                    level=level,
                    user=current_user,
                )
                self.state.event(
                    self.state.snapshot().get("step", 0),
                    "progression_stopped",
                    {
                        "level": level,
                        "target_user": next_user,
                        "reason": "No verified next-level credential",
                    },
                )
                self.console.print(
                    f"[yellow]Stopped at level {level}; no verified credential "
                    f"for {next_user}.[/yellow]"
                )
                return None

            # The credential was verified by a real SSH login, so it becomes
            # the password for the next level without needing to expose it
            # in the event log.
            current_password = credential
            current_user = next_user

            self.state.update(
                level=level + 1,
                user=current_user,
                status="transitioning",
                candidate="",
                command="",
                output="",
                step=0,
            )
            self.state.event(
                0,
                "credential_transition",
                {
                    "from_level": level,
                    "to_level": level + 1,
                    "username": current_user,
                    "credential_verified": True,
                },
            )
            self.console.print(
                f"[green]✓ Advancing to {current_user}[/green]"
            )

        return None
