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
    print('Response text:', result.stdout)
    try:
        data = json.loads(result.stdout)
        print('Parsed JSON:', type(data))
        print('Content:', json.dumps(data, indent=2)[:500])
    except Exception as e:
        print('Failed to parse JSON:', e)
