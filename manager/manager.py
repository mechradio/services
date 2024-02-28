from flask import Flask, request, Response
from flask_cors import CORS
from flask_socketio import SocketIO
from threading import Thread
import sys, os, time
sys.path.insert(0, '..')
from helper import add_no_cache_headers

token = os.environ.get('AWS_TOKEN', 'abc')

# Create Flask CORS-enabled server
app = Flask(__name__)
CORS(app)

# Create SocketIO server
socketio = SocketIO(app, cors_allowed_origins="*")

# Get current version
with open('version.txt', 'r') as f:
    version = f.read()

# 0 -> offline, 1 -> online, 2 -> busy
modules = {
    "manager": {"status": 1, "url": None, "sid": None, "version": version},
    "radio": {"status": 0, "url": None, "sid": None, "version": None},
    "downloader": {"status": 0, "url": None, "sid": None, "version": None}
}

# Radio helper
radio = {
    "queue": None
}
def counter():
    while True:
        if isinstance(radio.get("queue"), list):   
            radio["queue"][0]["time"] += 1
            time.sleep(1)
Thread(target=counter, daemon=True).start()

def format_status(statuses):
    formatted_statuses = {
        module_name: {
            "status": module_info.get("status", 0),
            "url": module_info.get("url", None),
            "version": module_info.get("version", None)
        }
        for module_name, module_info in statuses.items()
    }
    return formatted_statuses

connectedClients = {}

# Blank request template
@app.route('/<path:num>')
def main(num):
    return add_no_cache_headers(Response("Online, reached /" + num))

# On someone connection
@socketio.on('connect')
def connect():
    # If data sender is one of modules, set its state to online
    sender = request.headers.get('sender', 0)
    if sender: 
        for mod in modules:
            if mod == sender: 
                # Authorize
                t = request.headers.get('token')
                if t != token: return print("Unauthorized", flush=True)
                modules[mod]["status"] = 1
                modules[mod]["sid"] = request.sid
                # Send new services status to all clients
                print(f"The module '{sender}' has connected.", flush=True)
                return socketio.emit('status', format_status(modules))

    # If sender is connecting client
    ajdi = request.headers.get('id')
    connectedClients[ajdi] = request.sid
    # Send services status to connected client
    socketio.emit('status', format_status(modules), to=request.sid)
    # Send info abt connected clients to all modules
    socketio.emit('clients', connectedClients)
    print(f"A new client with ID '{ajdi}' has connected.", flush=True)
    socketio.emit('radio', radio["queue"], to=request.sid)

# On someone disconnect
@socketio.on('disconnect')
def disconnect():
    sid = request.sid

    # If data sender is one of clients, delete him
    for ajdi, value in connectedClients.items():
        if value == sid:
            del connectedClients[ajdi]
            # Update info abt connected clients to all modules
            socketio.emit('clients', connectedClients)
            print(f"A client with ID '{ajdi}' has disconnected.", flush=True)
            break
    
    # If data sender is one of modules, set its state to offline
    for module_name, module_info in modules.items():
        # Found module with sid, so it disconnected :(
        if module_info["sid"] == sid:
            module_info["status"] = 0
            module_info["sid"] = None
            print(f"The module '{module_name}' with SID '{sid}' has disconnected.", flush=True)
            # Update statuses
            socketio.emit('status', format_status(modules))
            return 

# Manager URL is changing
@socketio.on('changeUrl')
def internal(data):
    # Authorize
    t = data['token']
    if t != token: return

    # Change URL action
    modules["manager"]["url"] = data.get('url')
    modules["manager"]["status"] = 1
    # Emit change to all connected devices
    print(f"Changing url to: {modules['manager']['url']}", flush=True)
    socketio.emit('status', format_status(modules))

# Downloader wants something
@socketio.on('downloader')
def downloader(data):
    # Authorize
    t = data['token']
    if t != token: return

    # URL update action
    url = data.get('url', 0)
    if(url):
        modules["downloader"]["url"] = url

    # Version update action
    version = data.get('version', 0)
    if(version):
        modules["downloader"]["version"] = version
    
    # Status update action
    status = data.get('status', 0)
    if(status):
        modules["downloader"]["status"] = status
    
    # Emit change to all connected devices
    if(url or version or status):
        print(f"Changing downloader status to: {modules['downloader']['status']}", flush=True)
        socketio.emit('status', format_status(modules))


# Radio wants something
@socketio.on('radio')
def radioo(data):
    # Authorize
    t = data['token']
    if t != token: return

    # URL update action
    url = data.get('url', 0)
    if(url):
        modules["radio"]["url"] = url
        # Emit change to all connected devices
        print(f"Changing radio url to: {modules['radio']['url']}", flush=True)
        socketio.emit('status', format_status(modules))
    
    # Version update action
    version = data.get('version', 0)
    if(version):
        modules["radio"]["version"] = version
        # Emit change to all connected devices
        print(f"Changing radio version to: {modules['radio']['version']}", flush=True)
        socketio.emit('status', format_status(modules))
    
    if "action" in data:
        if data["action"] == "queueUpd":
            print("Radio requested queue update", flush=True)
            # Queue update action
            queue = data.get('queue', 0)
            if(queue):
                radio["queue"] = queue
                # Emit change to all connected devices
                socketio.emit('radio', queue)

if __name__ == '__main__':
    socketio.run(app, use_reloader=False, host='0.0.0.0', port=8000, allow_unsafe_werkzeug=True) # type: ignore