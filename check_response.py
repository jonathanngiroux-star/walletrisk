import os, json, subprocess
HERMES_CONFIG = os.path.join(os.environ.get('HOME', '/home/manitouabe8ich'), '.hermes', 'profiles', 'business-05', 'config.yaml')
def get_key():
    try:
        with open(HERMES_CONFIG, 'r') as f:
            content = f.read()
        for line in content.split('\n'):
            if 'AGENTMAIL_API_KEY:' in line:
                key = line.split('AGENTMAIL_API_KEY:', 1)[1].strip()
                if key.startswith('"') and key.endswith('"'):
                    key = key[1:-1]
                elif key.startswith("'") and key.endswith("'"):
                    key = key[1:-1]
                return key
    except Exception as e:
        print(f'Error reading API key: {e}')
    return None
key = get_key()
if key:
    url = 'https://api.agentmail.to/api/inboxes/wallethygiene@agentmail.to/messages'
    cmd = ['curl', '-s', '-H', f'Authorization: Bearer {key}', url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    print('Status:', result.returncode)
    print('Response:')
    print(result.stdout)
    try:
        data = json.loads(result.stdout)
        print('\nParsed as JSON')
        print('Type:', type(data))
        if isinstance(data, dict):
            print('Dict keys:', list(data.keys()))
            for k, v in data.items():
                print(f'  {k}: {type(v)}')
                if isinstance(v, list):
                    print(f'    List length: {len(v)}')
        elif isinstance(data, list):
            print('List length:', len(data))
            if len(data) > 0:
                print('First item:', json.dumps(data[0], indent=2)[:200])
        else:
            print('Other type:', data)
    except Exception as e:
        print('\nFailed to parse JSON:', e)
else:
    print('No API key')
