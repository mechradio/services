import subprocess, datetime

def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'  # Prevent caching by the browser
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

def configure_manager_search():
    subprocess.run(["git", "clone", "https://github.com/ai-radio-official/services.url", "--depth", "1", "tmp/managerurl"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Manager url repo fetched", flush=True)

def search_manager_url():
    subprocess.run(["git", "pull"], check=True, cwd="tmp/managerurl", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open('tmp/managerurl/url', 'r') as file:
        return file.read().strip()
    
def today():
    return datetime.datetime.now().isoweekday()

def get_audio_duration(file_path):
    # Run ffprobe to get audio duration
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                             'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    duration = float(result.stdout)
    return duration