from flask import Flask, Response, request
from flask_cors import CORS
from threading import Thread
from youtube_title_parse import get_artist_title
import sys, os, yt_dlp, random, string, subprocess, socketio, time, requests, shutil, tarfile
sys.path.insert(0, '..')
from helper import configure_manager_search, search_manager_url

app = Flask(__name__)
CORS(app)
token = os.environ.get('AWS_TOKEN', 'abc')
sio = socketio.Client()

# Read version
with open("version.txt", "r") as file:
    version = file.read()

modules = {}

# Configure searching for manager
configure_manager_search()
def check_and_connect():
    current_url = None
    while True:
        new_url = search_manager_url()  # Your function to search for a new URL
        
        if new_url != current_url or not sio.connected:
            if current_url:
                sio.disconnect()  # Disconnect if already connected
            print(f"Connecting to manager, to url {new_url}...", flush=True)
            try: sio.connect(new_url, headers={'token': token, 'sender': "downloader"})  # Connect with the new URL
            except: pass
            current_url = new_url
        time.sleep(5)  # Wait for 5 seconds before checking again
Thread(target=check_and_connect, daemon=True).start()

def emit(endpoint, data):
    if sio.connected: sio.emit(endpoint, data)
    else:
        time.sleep(2)
        emit(endpoint, data)

# Localhost run process sent new url
@app.route('/changeUrl', methods=['POST'])
def changeUrl():
    d = request.form # Access data sent in POST
    if d.get('token', 0) != token: return print("Invalid token")
    url = d.get('url')
    # Forward it to manager
    emit('downloader', {'url': url, 'version': version, 'token': token})
    print("Forwarded URL to manager.")
    return Response("OK")

# Handle modules changes
@sio.on('status')
def handle_modules_status(s):
    global modules
    modules = s

@app.route('/radioDownload', methods=['POST'])
def radioDownload():
    getToken = request.headers.get("Authorization")
    if getToken != token: return
    args = request.json
    Thread(target=downloadFromYt, args=(args[0], args[1], args[2], args[3], 'radio')).start()
    return Response("OK")

def downloadFromYt(url, uploadEndpoint, uploadCompletedEndpoint, queueIndex, uploadUrl):
    emit('downloader', {'status': 2, 'token': token})
    ERR=0; title=None; artist=None; fpath=None; ext=None; thunb=None
    try:
        ext = 'mp3'
        working_dir = 'tmp/' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '/'
        fpath = working_dir + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        os.makedirs(working_dir, exist_ok=True)

        ydl_opts = {
            'format': 'bestaudio/best',
            'download_options': '-N 16',
            'outtmpl': fpath,  # Save with the title as filename
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': ext,  # Save as .mp3 file
                'preferredquality': '192',
            },
            { 'key': 'SponsorBlock' }, 
            {
                'key': 'ModifyChapters',
                'remove_sponsor_segments': [
                    'filler',
                    'interaction',
                    'intro',
                    'music_offtopic',
                    'outro',
                    'preview',
                    'selfpromo',
                    'sponsor'
                ],
            }],
            'writethumbnail': True,  # Write thumbnail
            'merge_output_format': ext,  # Merge into .wav file
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
        
        filename = fpath + '.' + ext
        os.rename(filename, filename + '.' + 'tmp')
        print("[info] Running silence cutter...", flush=True)
        subprocess.run(f'ffmpeg -hide_banner -loglevel error -i {filename + "." + "tmp"} -af silenceremove=start_periods=1:start_duration=1:start_threshold=-60dB:detection=peak,aformat=dblp,areverse,silenceremove=start_periods=1:start_duration=1:start_threshold=-60dB:detection=peak,aformat=dblp,areverse {filename}', shell=True)
        os.remove(filename + '.' + 'tmp')

        try:
            artist, title = get_artist_title(info_dict.get('title', None)) # type: ignore
        except:
            artist = info_dict.get('uploader', None) # type: ignore
            title = info_dict.get('title', None) # type: ignore
            
        if(os.path.exists(fpath + '.' + 'webp')):
            thunb = 'webp'
        elif(os.path.exists(fpath + '.' + 'jpg')):
            thunb = 'jpg'
        elif(os.path.exists(fpath + '.' + 'png')):
            thunb = 'png'
        else:
            thunb = None

        url = f'{uploadUrl}/{uploadEndpoint}'
        headers = {'Authorization': token}
        
        tar = os.path.join('tmp', ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '.tar')
        with tarfile.open(tar, 'w') as t:
            t.add(working_dir, arcname='tmp')
        
        with open(tar, 'rb') as t:
            files = {'file': t}
            # Ensure url is always up-to-date
            url = url.replace('radio', modules["radio"]["url"])
            resp = requests.post(url, files=files, headers=headers)
        
        shutil.rmtree(working_dir)
        os.remove(tar)
        
        if resp.status_code == 200:
            print("Request successful")
        else:
            print("Request failed with status code:", resp.status_code)

    except Exception as e:
        ERR = 1
        print(e)

    fpath = fpath.split('/')[2]

    # Title, author, filepath, extension, thumbnail
    args = {
        't': title,
        'a': artist,
        'fp': fpath,
        'ext': ext,
        'thunb': thunb,
        'ERR': ERR,
        'i': queueIndex
    }
    url = f'{uploadUrl}/{uploadCompletedEndpoint}'.replace('radio', modules["radio"]["url"])
    requests.post(url, json=args, headers=headers)

    if not ERR: print(f'Sent {title} to server.', flush=True)
    else: print(f'Failed to send {title} to server.', flush=True)
    emit('downloader', {'status': 1, 'token': token})
    return