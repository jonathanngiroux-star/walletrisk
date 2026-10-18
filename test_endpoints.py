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
if not key:
    print("No API key found")
    exit(1)
bases = ['https://api.agentmail.to', 'https://agentmail.to']
endpoints = [
    '/inboxes/wallethygiene@agentmail.to/messages',
    '/api/inboxes/wallethygiene@agentmail.to/messages',
    '/v1/inboxes/wallethygiene@agentmail.to/messages',
    '/inboxes/wallethygiene@agentmail.to',
    '/api/inboxes/wallethygiene@agentmail.to',
    '/v1/inboxes/wallethygiene@agentmail.to',
    '/messages/wallethygiene@agentmail.to',
    '/api/messages/wallethygiene@agentmail.to',
    '/v1/messages/wallethygiene@agentmail.to'
]
for base in bases:
    for ep in endpoints:
        url = base + ep
        cmd = ['curl', '-s', '-H', f'Authorization: Bearer {key}', url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f'SUCCESS: {base}{ep}')
            try:
                data = json.loads(result.stdout)
                print(f'  Type: {type(data)}')
                if isinstance(data, list):
                    print(f'  List length: {len(data)}')
                    if len(data) > 0:
                        print(f'  First item keys: {data[0].keys() if isinstance(data[0], dict) else "not dict"}')
                elif isinstance(data, dict):
                    print(f'  Dict keys: {data.keys()}')
            except Exception as e:
                print(f'  Not JSON: {result.stdout[:100]}')
            print()
