import paramiko

class SSHExecutor:
    def __init__(self, settings):
        self.s = settings
        self.client = None

    def connect(self, user, password):
        self.close()
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(self.s.host, self.s.port, username=user, password=password,
                  timeout=self.s.timeout, auth_timeout=self.s.timeout,
                  banner_timeout=self.s.timeout, look_for_keys=False, allow_agent=False)
        self.client = c

    def run(self, command):
        if not self.client:
            raise RuntimeError("SSH is not connected")
        stdin, stdout, stderr = self.client.exec_command(command, timeout=self.s.timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        return out, err, code

    def close(self):
        if self.client:
            self.client.close()
        self.client = None
