requirements = [
    "--extra-index-url https://download.pytorch.org/whl/cpu",
    "torchvision~=0.17.0", 
    "diffusers~=0.25.1", 
    "transformers~=4.37.2", 
    "accelerate~=0.26.1", 
    "invisible-watermark~=0.2.0", 
    "omegaconf~=2.3.0", 
    "peft~=0.8.1",

    "python-socketio~=5.11.1"
]

import subprocess
print("| Installing required packages...", flush=True)
subprocess.run(["pip", "install"] + requirements, check=True)

import time
while True:
    time.sleep(60)