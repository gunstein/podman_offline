import subprocess
from pathlib import Path

REAL_RUN = subprocess.run
SOURCE = Path(__file__).resolve().parents[2] / "deployment/deploy.py"
DRIVER = Path(__file__).with_name("retry_driver.py")


def service(owner, operation="restart"):
    command = ["systemctl", "--user", operation]
    if operation == "is-active":
        command.append("--quiet")
    return command + ["myproduct-" + owner + ".service"]
