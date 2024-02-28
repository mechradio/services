import re, time, os, requests

# Paths, but looking from downloader.py
log_path = "tmp/localhost.run.log"
# Some other variables
token = os.environ.get('AWS_TOKEN', 'abc')

# Regular expression pattern to search for
pattern = r'(https?:\/\/.*?\.life)'

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
def notify_downloader(url):
    data = {
        'url': url,
        'token': token
    }
    r = requests.post('http://127.0.0.1:8000/changeUrl', data=data)
    if r.ok: print("[HELPER] Downloader received url change info", flush=True)
    else: print("[HELPER] Failed to notify downloader about url change", flush=True)

# Loop
while True:
    result = fetch_until_pattern_found()
    # If result found
    if(result): notify_downloader(result)
    else: time.sleep(1)
