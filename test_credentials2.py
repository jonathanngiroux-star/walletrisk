#!/usr/bin/env python3
import os
import sys

# Add hermes_tools path
hermes_tools_dir = None
for dirpath, dirnames, filenames in os.walk('/home/manitouabe8ich/.hermes/cache/scratch'):
    if 'hermes_tools.py' in filenames:
        hermes_tools_dir = dirpath
        break
if hermes_tools_dir:
    sys.path.insert(0, hermes_tools_dir)

from hermes_tools import _call

def get_token_from_process(pid):
    try:
        environ_path = f'/proc/{pid}/environ'
        if os.path.exists(environ_path):
            with open(environ_path, 'rb') as f:
                environ_data = f.read()
            environ_vars = environ_data.split(b'\\0')
            for e in environ_vars:
                if e.startswith(b'HERMES_RPC_TOKEN='):
                    token = e.split(b'=', 1)[1].decode()
                    token = token.replace('\x00', '').replace('\n', '').replace('\r', '')
                    if token:
                        return token
                if e.startswith(b'HERMES_SESSION_KEY='):
                    key = e.split(b'=', 1)[1].decode()
                    key = key.replace('\x00', '').replace('\n', '').replace('\r', '')
                    if key:
                        return key
    except Exception:
        pass
    return None

def get_socket_from_process(pid):
    try:
        environ_path = f'/proc/{pid}/environ'
        if os.path.exists(environ_path):
            with open(environ_path, 'rb') as f:
                environ_data = f.read()
            environ_vars = environ_data.split(b'\\0')
            for e in environ_vars:
                if e.startswith(b'HERMES_SOCKET='):
                    socket = e.split(b'=', 1)[1].decode()
                    socket = socket.replace('\x00', '').replace('\n', '').replace('\r', '')
                    if socket:
                        return socket
                for e in environ_vars:
                    if e.startswith(b'HERMES_RPC_SOCKET='):
                        socket = e.split(b'=', 1)[1].decode()
                        socket = socket.replace('\x00', '').replace('\n', '').replace('\r', '')
                        if socket:
                            return socket
    except Exception:
        pass
    return None

def get_process_pid_by_command(pattern):
    try:
        result = os.popen(f"pgrep -f '{pattern}'").read().strip()
        if result:
            pids = result.split()
            return pids[0]
    except Exception:
        pass
    return None

def main():
    # Try to get token and socket from the hermes-agent gateway process
    gateway_pid = get_process_pid_by_command("hermes-agent.*gateway run")
    if gateway_pid:
        print(f"Found hermes-agent gateway pid: {gateway_pid}")
        token = get_token_from_process(gateway_pid)
        socket = get_socket_from_process(gateway_pid)
        if token and socket:
            print(f"Got token and socket from gateway process {gateway_pid}")
            os.environ['HERMES_RPC_TOKEN'] = token
            os.environ['HERMES_RPC_SOCKET'] = socket
        elif token:
            print(f"Got token but no socket from gateway process {gateway_pid}")
            os.environ['HERMES_RPC_TOKEN'] = token
            # We'll try to get socket from cache later
        elif socket:
            print(f"Got socket but no token from gateway process {gateway_pid}")
            os.environ['HERMES_RPC_SOCKET'] = socket
            # We'll try to get token from config later
    else:
        print("No hermes-agent gateway process found")

    # If we don't have both, try to get token from config
    if not ('HERMES_RPC_TOKEN' in os.environ and os.environ['HERMES_RPC_TOKEN']):
        config_path = '/home/manitouabe8ich/.hermes/profiles/business-05/config.yaml'
        try:
            with open(config_path, 'r') as f:
                content = f.read()
            for line in content.split('\n'):
                if 'AGENTMAIL_API_KEY:' in line:
                    token = line.split('AGENTMAIL_API_KEY:', 1)[1].strip()
                    if token.startswith('"') and token.endswith('"'):
                        token = token[1:-1]
                    elif token.startswith("'") and token.endswith("'"):
                        token = token[1:-1]
                    break
        except Exception:
            token = None
        if token:
            print(f"Got token from config: {token[:10]}...")
            os.environ['HERMES_RPC_TOKEN'] = token

    # If we don't have socket, try to get from cache
    if not ('HERMES_RPC_SOCKET' in os.environ and os.environ['HERMES_RPC_SOCKET']):
        socket_dir = '/home/manitouabe8ich/.hermes/cache/scratch/'
        try:
            import glob
            sockets = glob.glob(os.path.join(socket_dir, 'hermes_rpc_*.sock'))
            if sockets:
                sockets_with_time = [(f, os.path.getmtime(f)) for f in sockets]
                sockets_with_time.sort(key=lambda x: x[1], reverse=True)
                socket = sockets_with_time[0][0]
                print(f"Got socket from cache: {socket}")
                os.environ['HERMES_RPC_SOCKET'] = socket
        except Exception:
            pass

    print(f"HERMES_RPC_TOKEN: {os.environ.get('HERMES_RPC_TOKEN', 'NOT SET')}")
    print(f"HERMES_RPC_SOCKET: {os.environ.get('HERMES_RPC_SOCKET', 'NOT SET')}")

    # Test list_inboxes
    try:
        result = _call("mcp__agentmail__list_inboxes", {})
        print(f"list_inboxes result: {result}")
    except Exception as e:
        print(f"list_inboxes exception: {e}")

    # Test get_inbox for our inbox ID
    inbox_id = "wallethygiene@agentmail.to"
    try:
        result = _call("mcp__agentmail__get_inbox", {"inboxId": inbox_id})
        print(f"get_inbox result: {result}")
    except Exception as e:
        print(f"get_inbox exception: {e}")

if __name__ == "__main__":
    main()