"""Launch the portal's local dependency processes without opening windows."""

import os
import subprocess


def start_background_process(command, *, cwd, env=None):
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def start_powershell_service(script_path, *, cwd, script_args=()):
    return start_background_process(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            script_path,
            *script_args,
        ],
        cwd=cwd,
    )
