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
    bases = [
        'https://api.agentmail.to',
        'https://agentmail.to'
    ]
    for base in bases:
        endpoints = [
            '/inboxes',
            '/api/inboxes',
            '/v1/inboxes',
            f'/inboxes/wallethygiene@agentmail.to',
            f'/api/inboxes/wallethygiene@agentmail.to',
            f'/v1/inboxes/wallethygiene@agentmail.to',
            f'/inboxes/wallethygiene@agentmail.to/messages',
            f'/api/inboxes/wallethygiene@agentmail.to/messages',
            f'/v1/inboxes/wallethygiene@agentmail.to/messages'
        ]
        for ep in endpoints:
            url = base + ep
            cmd = ['curl', '-s', '-H', f'Authorization: Bearer {key}', url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            print(f'{base}{ep}: {result.returncode}')
            if result.returncode == 0 and result.stdout.strip():
                print(f'  Response: {result.stdout[:200]}')
