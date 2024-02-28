requirements = [
    "audiocraft~=1.12.0", 

    "python-socketio~=5.11.1"
]

import subprocess
print("| Installing required packages...", flush=True)
subprocess.run(["pip", "install"] + requirements, check=True)

import time
while True:
    time.sleep(60)

# TODO