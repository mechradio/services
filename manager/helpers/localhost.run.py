import re, time, os, json, subprocess, socketio, requests

# Paths, but looking from manager.py
log_path = "tmp/localhost.run.log"
aws_urlPath = "helpers/awsfun.url"
url_repo_path = 'tmp/url'

# Some other variables
token = os.environ.get('AWS_TOKEN', 'abc')

# Regular expression pattern to search for
pattern = r'(https?:\/\/.*?\.life)'

# Initialize socketio connection to manager
sio = socketio.Client()

# Function to fetch the file and search for the pattern
used = []
def fetch_until_pattern_found():
    # Loop until new url found
    result = False
    while not result:
        try:
            # Open the localhost.run log file
            with open(log_path, "r") as file:
                content = file.read()
            # Pop used urls
            for link in used:
                content = content.replace(link, "")

            # Look for new url
            matches = re.findall(pattern, content)
            if matches:
                # Append to used and return url
                used.append(matches[0])
                result = matches[0]
        except: pass
        time.sleep(1)
    # if found, return new url
    return result

# Give info to mr. manager
def notify_manager(url):
    data = {
        'url': url,
        'token': token
    }
    sio.emit('changeUrl', data)
    print("[HELPER] Manager received url change info", flush=True)

# Append the url to server.url repository and push, required for other modules to connect
def push_to_github(url):
    with open(os.path.join(url_repo_path, 'url'), "w") as file:
        file.write(url + "\n")

    subprocess.run(f"cd {url_repo_path} && git add .", shell=True)
    subprocess.run(f"cd {url_repo_path} && git commit -m 'Add {url}'", shell=True)
    subprocess.run(f"cd {url_repo_path} && git push", shell=True)

# Push update to AWS, so web clients can connect
def push_to_aws(url):
    with open(aws_urlPath, "r") as file:
        content = file.read()

    body_data = {'url': url}
    headers = {
        'authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    r = requests.post(content + '/urlPush', headers=headers, data=json.dumps(body_data))
    if r.ok: print(f"Successfully pushed {url} to AWS", flush=True)
    else: print(f"Failed to push {url} to AWS", flush=True)

sio.connect('http://127.0.0.1:8000', retry=True)

# Loop
while True:
    result = fetch_until_pattern_found()
    # If result found
    if(result):
        notify_manager(result)
        push_to_github(result)
        push_to_aws(result)
    else: time.sleep(1)
