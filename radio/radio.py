from flask import Flask, Response, request, send_from_directory, abort
from flask_cors import CORS
from threading import Thread
import sys, os, time, random, string, requests, tarfile, socketio, subprocess
sys.path.insert(0, '..')
from helper import add_no_cache_headers, configure_manager_search, search_manager_url, today, get_audio_duration
app = Flask(__name__)
CORS(app)
sio = socketio.Client()
token = os.environ.get('AWS_TOKEN', 'abc')

# Read version
with open("version.txt", "r") as file:
    version = file.read()
# Get url for yt list
with open('helpers/ytlist.url', 'r') as file:
    ytlist_url = file.read().strip()

ffmpeg_opts = [
    '-c:a', 'libmp3lame',           # Audio codec
    '-b:a', '192k',                 # Audio bitrate
    '-ar', '44100',                 # Audio sample rate
    '-ac', '2',                     # Audio channels (stereo)
    '-preset', 'fast',              # Encoding preset for fast encoding
    '-f', 'mp3',                    # Output format MP3,
]

queue = []
alreadyPlayed = []
radio = {
    "ffmpeg_processes": {},
    "playID": 0
}

connectedClients = {}
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
            try: sio.connect(new_url, headers={'token': token, 'sender': "radio"})  # Connect with the new URL
            except: pass
            current_url = new_url
        time.sleep(5)  # Wait for 5 seconds before checking again
Thread(target=check_and_connect, daemon=True).start()

def create_queue_change_args(q): 
    que = {
        "action": "queueUpd",
        "queue": [
            {
                'title': track.get("title", ""),
                'author': track.get("author", ""),
                'duration': track.get("duration", ""),
                'thumbnail': track.get("thumbnail", "")
            }
            for track in q
            if track.get("title") and track.get("author")
        ]     
    }
    que["queue"][0]["time"] = q[0].get("time", 0)
    que["queue"][0]["additional"] = q[0].get("additional", {})
    return que

# FFMpeg process starter
def start_ffmpeg_process():
    global radio
    # Start ffmpeg process
    command = [
        'ffmpeg',
        '-re',                          # Read data from input at native frame rate
        '-ss', str(queue[0]["time"]),      # Start from given time
        '-i', str(queue[0]["fpath"]),      # Input file
    ]
    command.extend(ffmpeg_opts)
    command.append('-')  # Output to stdout
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=128)

# Stream generator (including previous terminations)
def generate_audio(session_id):
    global radio
    def restart(terminate=False):
        if session_id in radio["ffmpeg_processes"]: 
            if radio["ffmpeg_processes"][session_id] == 'terminated':
                del radio["ffmpeg_processes"][session_id]
                return
            
            if terminate:
                if len(radio['ffmpeg_processes'][session_id]) > 1:
                    print("Terminating ffmpeg process for id '" + session_id + "' for media '" + radio["ffmpeg_processes"][session_id][0]["file"] + "'...", flush=True)
                    radio['ffmpeg_processes'][session_id][0]["process"].terminate()
                    del radio["ffmpeg_processes"][session_id][0]
                    return radio["ffmpeg_processes"][session_id][0]["process"]
                elif len(radio["ffmpeg_processes"][session_id]) == 1:
                    return radio["ffmpeg_processes"][session_id][0]["process"]
                else: return False

        else:
            radio["ffmpeg_processes"][session_id] = []

        if not terminate and isinstance(queue[0]["fpath"], str):
            print("Starting new ffmpeg process for id '" + session_id + "' for media '" + queue[0]["fpath"] + "'...", flush=True)       
            ffmpeg_process = start_ffmpeg_process()
            process_json = {
                "process": ffmpeg_process, 
                "file": queue[0]["fpath"]
            }
            radio["ffmpeg_processes"][session_id].append(process_json)
            return ffmpeg_process
        else: return False

    currentlyplaying = radio["playID"]
    data = None
    ffmpeg_process = restart()

    while True:
        if radio["playID"] != currentlyplaying:
            currentlyplaying = radio["playID"]
            restart()

        try: data = ffmpeg_process.stdout.read(128) # type: ignore
        except:pass

        if not data:
            ffmpeg_process = restart(True)
            if not ffmpeg_process:
                time.sleep(1)
                return

        else:
            yield data

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
    emit('radio', {'url': url, 'version': version, 'token': token})
    print("Forwarded URL to manager.")
    return Response("OK")

# Someone requested audio stream
@app.route('/listen')
def listen():
    global radio
    session_id = request.args.get('id')
    if session_id not in connectedClients:
        return "Not connected to manager, not authorized", 403  # Return forbidden status if user is not connected via WebSocket
    # Return audio stream
    return add_no_cache_headers(Response(generate_audio(session_id), mimetype='audio/mpeg'))

@app.route('/tmp/<path:filename>')
def serve_file(filename):
    if not filename.endswith('.mp3'): 
        directory = os.path.abspath(os.path.join('.', 'tmp'))
        return send_from_directory(directory, filename)
    else:
        # Return a 404 error if the file is not avaiable
        abort(404)

# Handle connection changes
@sio.on('clients')
def handle_new_clients(c):
    global connectedClients
    connectedClients = c

    # Check if any clients with ffmpeg process active disconnected
    for session_id in list(radio["ffmpeg_processes"].keys()):
        if session_id not in connectedClients:
            for process in radio['ffmpeg_processes'][session_id]:
                if isinstance(process, dict) and "file" in process and "process" in process:
                    print("Terminating ffmpeg process for id '" + session_id + "' for media '" + process["file"] + "'...", flush=True)
                    process["process"].terminate()
            radio["ffmpeg_processes"][session_id] = 'terminated'

# Handle modules changes
@sio.on('status')
def handle_modules_status(s):
    global modules
    modules = s

# Terminate on stop player request
@app.route('/stopPlayer', methods=['POST'])
def handle_music_stop():
    session_id = request.headers.get('id')
    if session_id in radio["ffmpeg_processes"]:
        for process in radio['ffmpeg_processes'][session_id]:
            if isinstance(process, dict) and "file" in process and "process" in process:
                print("Terminating ffmpeg process for id '" + session_id + "' for media '" + process["file"] + "'...", flush=True)
                process["process"].terminate()
        radio["ffmpeg_processes"][session_id] = 'terminated'
    return Response("OK")

# Downloader wants to push new song
@app.route('/uploadSong', methods=['POST'])
def dwnldInProgress():
    getToken = request.headers.get("Authorization")
    if getToken != token: return
    if 'file' not in request.files: return
    file = request.files['file']
    filename = file.filename
    file.save(filename)
    with tarfile.open(filename, 'r') as tar:
        tar.extractall()
    os.remove(filename)
    return 'File uploaded successfully', 200

forceChange = False; firstLaunchReady = False; downloadErr = -1; downloading = False; indexChanged = 0

@app.route('/uploadCompleted', methods=['POST'])
def on_dwnld_completed():
    getToken = request.headers.get("Authorization")
    if getToken != token: return Response("Invalid token", status=403)
    args = request.json

    global firstLaunchReady, downloadErr, downloading, indexChanged
    i = args["i"]
    if(indexChanged): i = i - indexChanged
    if(args.get("ERR")): 
        print("Failed to download track", flush=True)
        downloadErr = i
        downloading = False
        return Response("OK")
    
    queue[i]["fpath"] = os.path.join('tmp', args["fp"] + '.' + args["ext"])
    queue[i]["title"] = args["t"]
    queue[i]["author"] = args["a"]
    queue[i]["duration"] = get_audio_duration(queue[i]["fpath"])
    queue[i]["time"] = 0
    if args.get('thunb'): queue[i]["thumbnail"] = os.path.join('tmp',args["fp"] + '.' + args["thunb"])
    else: queue[i]["thumbnail"] = None
    print("Downloaded and added to queue track " + args["t"] + ", id: " + args["fp"], flush=True)
    firstLaunchReady = True; downloading = False
    a = create_queue_change_args(queue)
    a["token"] = token
    emit('radio', a)
    return Response("OK")

@app.route('/getQueue')
def get_queue():
    session_id = request.headers.get('id')
    if session_id not in connectedClients:
        return "Not connected to manager, not authorized", 403  # Return forbidden status if user is not connected via WebSocket

    return create_queue_change_args(queue)

def ai_radio_streamer():
    global forceChange, firstLaunchReady, downloadErr, downloading, indexChanged
    def addToQueue():
        response = requests.get(ytlist_url)
        if response.ok:
            tracksList = response.json()
        else: return

        weighted_choices = []
        for entry in tracksList:
            if isinstance(entry, str):
                url = entry
                multiplier = 1
                setting = None
            else:
                url = entry[0]
                multiplier = entry[1].get("m", 1)
                setting = {key: value for key, value in entry[1].items() if key != "m"}
                if 'dm' in entry[1]:
                    day, additional_multiplier = map(int, entry[1]['dm'].split(';'))
                    if day == today():
                        multiplier *= additional_multiplier
            weighted_choices.extend([(url, setting)] * multiplier)

        if len(weighted_choices) < 1: return
        else:
            if(len(alreadyPlayed) > len(tracksList)/3): alreadyPlayed.pop(0)
            def shuffle():
                random.shuffle(weighted_choices)
                chosen_url, setting = random.choice(weighted_choices)
                if not setting: setting = {}
                return chosen_url, setting
           
            chosen_url, setting = shuffle()
            while chosen_url in alreadyPlayed: 
                chosen_url, setting = shuffle()

            queue.append({"url": chosen_url, "additional": setting})
            alreadyPlayed.append(chosen_url)

    addToQueue()

    def try_to_dwnld():
        args = [queue[0]['url'], "/uploadSong", "/uploadCompleted", 0]
        if modules.get("downloader") and modules["downloader"].get("status") == 1 and modules["downloader"].get("url"):
            print("Waiting for downloader to finish...", flush=True)
            requests.post(modules["downloader"]["url"] + "/radioDownload", json=args, headers={'Authorization': token})
        else:
            # If downloader not yet connected abort
            print("Waiting for downloader...", flush=True)
            time.sleep(2)
            return try_to_dwnld()
    try_to_dwnld()

    while not firstLaunchReady:
        time.sleep(1)
    while firstLaunchReady:
        # Pre-adding & fetching next songs
        if len(queue) < 4:
            addToQueue()

        # Error downloading
        if downloadErr > -1:
            queue.pop(downloadErr)
            print(f"Popped from queue errored track ({downloadErr})", flush=True)
            downloadErr = -1

        # Request download
        if modules["downloader"]["status"] == 1 and modules["downloader"].get("url") and not downloading:
            for track in queue:
                if "url" in track and not "fpath" in track:       
                    indexChanged = 0
                    downloading = True
                    args = [track['url'], "/uploadSong", "/uploadCompleted", queue.index(track)]
                    requests.post(modules["downloader"]["url"] + "/radioDownload", json=args, headers={'Authorization': token})

        # Change radio playing title
        if forceChange:
            forceChange = False
            toRemove = [queue[0]["fpath"]]
            if(queue[0]["thumbnail"]):
                toRemove.append(queue[0]["thumbnail"])
            if len(toRemove) > 0: 
                for el in toRemove:
                    if(os.path.exists(el)): 
                        os.remove(el)

            queue.pop(0)
            radio["playID"] = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            indexChanged += 1

            a = create_queue_change_args(queue)
            a["token"] = token
            emit('radio', a)

        # Increment time by 0.1 second
        queue[0]["time"] += 0.1

        # Send force signal to ensure audio playback
        if queue[0]["time"] >= queue[0]["duration"]-0.1 and not forceChange:
            forceChange = True

        time.sleep(0.1)
    
Thread(target=ai_radio_streamer,daemon=True).start()

if __name__ == '__main__':
    app.run(use_reloader=False, host='0.0.0.0', port=8000, threaded=True)
