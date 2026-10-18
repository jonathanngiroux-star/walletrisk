#!/usr/bin/env python3
import os
import sys
import json
import re
import subprocess
import time
import glob
from datetime import datetime, timedelta

# Set HERMES_RPC_SOCKET if not set
if 'HERMES_RPC_SOCKET' not in os.environ:
    home = os.environ.get('HOME', '/home/manitouabe8ich')
    scratch_dir = os.path.join(home, '.hermes', 'cache', 'scratch')
    kernel_dirs = glob.glob(os.path.join(scratch_dir, 'hermes_kernel_*'))
    if kernel_dirs:
        kernel_dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        for kd in kernel_dirs:
            socket_path = os.path.join(kd, 'hermes-rpc.sock')
            if os.path.exists(socket_path):
                os.environ['HERMES_RPC_SOCKET'] = socket_path
                break

BASE_DIR = "/home/manitouabe8ich/walletrisk"
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
PROCESSED_FILE = os.path.join(REPORTS_DIR, "processed_message_ids.json")
SUBSCRIBERS_FILE = os.path.join(REPORTS_DIR, "subscribers.jsonl")
CONFIG_FILE = os.path.join(BASE_DIR, "config", "payments.json")
VERIFICATION_SCRIPT = os.path.join(BASE_DIR, "scripts", "verify_payment.py")
HERMES_CONFIG = os.path.join(os.environ.get('HOME', '/home/manitouabe8ich'), '.hermes', 'profiles', 'business-05', 'config.yaml')

def get_agentmail_api_key():
    """Extract AGENTMAIL_API_KEY from Hermes config file."""
    try:
        with open(HERMES_CONFIG, 'r') as f:
            content = f.read()
        for line in content.split('\\n'):
            if 'AGENTMAIL_API_KEY:' in line:
                key = line.split('AGENTMAIL_API_KEY:', 1)[1].strip()
                if key.startswith('\"') and key.endswith('\"'):
                    key = key[1:-1]
                elif key.startswith(\"'\") and key.endswith(\"'\"):
                    key = key[1:-1]
                return key
    except Exception as e:
        print(f"Error reading API key: {e}", file=sys.stderr)
    return None

def agentmail_get(endpoint):
    """Make a GET request to AgentMail API using curl."""
    api_key = get_agentmail_api_key()
    if not api_key:
        raise Exception("AgentMail API key not found")
    url = f"https://api.agentmail.to{endpoint}"
    cmd = f'curl -s -H "Authorization: Bearer {api_key}" "{url}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise Exception(f"AgentMail API request failed: {result.stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # If not JSON, return the text
        return result.stdout

def agentmail_post(endpoint, data):
    """Make a POST request to AgentMail API using curl."""
    api_key = get_agentmail_api_key()
    if not api_key:
        raise Exception("AgentMail API key not found")
    url = f"https://api.agentmail.to{endpoint}"
    data_json = json.dumps(data)
    # We'll write the JSON to a temporary file to avoid escaping issues
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(data_json)
        temp_file = f.name
    try:
        cmd = f'curl -s -H "Authorization: Bearer {api_key}" -H "Content-Type: application/json" -d @{temp_file} "{url}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise Exception(f"AgentMail API request failed: {result.stderr}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout
    finally:
        os.unlink(temp_file)

def load_processed_ids():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, 'r') as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_processed_ids(ids):
    with open(PROCESSED_FILE, 'w') as f:
        json.dump(list(ids), f)

def append_subscriber(record):
    with open(SUBSCRIBERS_FILE, 'a') as f:
        f.write(json.dumps(record) + "\n")

def parse_order_email(email_content):
    lines = email_content.split('\\n')
    wallet = None
    tx_hash = None
    chain = "ethereum"
    delivery_email = None
    plan = "monthly"
    amount_usd = 9
    for line in lines:
        line = line.strip()
        if line.lower().startswith("wallet:"):
            wallet = line.split(":", 1)[1].strip()
        elif line.lower().startswith("tx hash:"):
            tx_hash = line.split(":", 1)[1].strip()
        elif line.lower().startswith("chain:"):
            chain = line.split(":", 1)[1].strip().lower()
        elif line.lower().startswith("delivery email:"):
            delivery_email = line.split(":", 1)[1].strip()
        elif line.lower().startswith("plan:"):
            plan_text = line.split(":", 1)[1].strip().lower()
            if "yearly" in plan_text:
                plan = "yearly"
                amount_usd = 89
            else:
                plan = "monthly"
                amount_usd = 9
    if not wallet or not tx_hash:
        return None, "Missing wallet or tx hash"
    if not delivery_email:
        return None, "Missing delivery email"
    return {
        "wallet": wallet,
        "tx_hash": tx_hash,
        "chain": chain,
        "delivery_email": delivery_email,
        "plan": plan,
        "amount_usd": amount_usd
    }, None

def verify_payment_chain(chain, tx_hash, usd_amount):
    cmd = [
        "python3", VERIFICATION_SCRIPT,
        "--chain", chain,
        "--tx", tx_hash,
        "--usd", str(usd_amount)
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stdout.strip()
    except Exception as e:
        return False, str(e)

def verify_payment_manual(chain, tx_hash, expected_address):
    explorer_urls = {
        "tron": f"https://tronscan.org/#/transaction/{tx_hash}",
        "stellar": f"https://stellar.expert/explorer/public/tx/{tx_hash}"
    }
    if chain not in explorer_urls:
        return False, f"Unsupported chain for manual verification: {chain}"
    url = explorer_urls[chain]
    try:
        # Use curl to fetch the page
        cmd = f"curl -s \"{url}\""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False, f"Failed to fetch explorer page: {result.stderr}"
        content = result.stdout
        if not content:
            return False, "Empty content from explorer"
        if "Transaction not found" in content or "No transaction" in content:
            return False, "Transaction not found on explorer"
        if expected_address.lower() in content.lower():
            return True, f"Manually verified via {url}: transaction found and recipient matches."
        else:
            return False, f"Recipient address mismatch. Expected {expected_address}, not found in explorer page."
    except Exception as e:
        return False, f"Manual verification error: {str(e)}"

def run_deep_scan(wallet_address, chains, order_id):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    output_file = os.path.join(REPORTS_DIR, f"{order_id}.md")
    chain_args = []
    for chain in chains:
        chain_args.extend(["--chain", chain])
    cmd = [
        "python3", "-m", "walletrisk", wallet_address,
        "--deep"
    ] + chain_args + [
        "-o", output_file
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=600
        )
        if os.path.exists(output_file):
            return True, output_file
        else:
            return False, result.stdout.strip()
    except Exception as e:
        return False, str(e)

def main():
    # Ensure reports directory exists
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # Load processed IDs
    processed_ids = load_processed_ids()
    
    # Load payment config
    try:
        with open(CONFIG_FILE, 'r') as f:
            payments_config = json.load(f)
    except Exception as e:
        print(f"Error loading payments config: {e}", file=sys.stderr)
        payments_config = {}
    
    # List messages in the inbox
    try:
        messages = agentmail_get(f"/api/inboxes/wallethygiene@agentmail.to/messages")
    except Exception as e:
        return f"[CRON_FAILURE]\nFailed to list messages: {str(e)}"
    
    if not isinstance(messages, list):
        return "[CRON_FAILURE]\nUnexpected messages format"
    
    # Filter new messages (not processed and unread)
    new_messages = []
    for msg in messages:
        msg_id = msg.get("messageId")
        if not msg_id:
            continue
        if msg_id in processed_ids:
            continue
        labels = msg.get("labels", [])
        if "unread" not in labels:
            continue
        new_messages.append(msg)
    
    if not new_messages:
        return "No new orders."
    
    order_results = []
    newly_processed_ids = set()
    
    for msg in new_messages:
        msg_id = msg.get("messageId")
        # Get full message
        try:
            message = agentmail_get(f"/api/messages/{msg_id}")
        except Exception as e:
            order_results.append(f"SKIPPED-ERROR: {msg_id} - Failed to get message: {str(e)}")
            newly_processed_ids.add(msg_id)
            continue
        
        if not message:
            order_results.append(f"SKIPPED-ERROR: {msg_id} - No message content")
            newly_processed_ids.add(msg_id)
            continue
        
        # Extract body
        body = message.get("body", "")
        if not body:
            # fallback to string representation
            body = json.dumps(message)
        
        if not body:
            order_results.append(f"SKIPPED-ERROR: {msg_id} - Empty email body")
            newly_processed_ids.add(msg_id)
            continue
        
        # Parse order
        order_data, error = parse_order_email(body)
        if error:
            order_results.append(f"SKIPPED-ERROR: {msg_id} - {error}")
            newly_processed_ids.add(msg_id)
            continue
        
        wallet = order_data["wallet"]
        tx_hash = order_data["tx_hash"]
        chain = order_data["chain"]
        delivery_email = order_data["delivery_email"]
        plan = order_data["plan"]
        amount_usd = order_data["amount_usd"]
        
        # Verify payment
        verified = False
        verification_note = ""
        if chain in ["ethereum", "base", "polygon", "arbitrum", "optimism", "gnosis"]:
            verified, verification_note = verify_payment_chain(chain, tx_hash, amount_usd)
        elif chain in ["tron", "stellar"]:
            expected_address = payments_config.get(chain)
            if not expected_address:
                order_results.append(f"REJECTED: {wallet} - No payment address configured for {chain}")
                newly_processed_ids.add(msg_id)
                continue
            verified, verification_note = verify_payment_manual(chain, tx_hash, expected_address)
        else:
            order_results.append(f"REJECTED: {wallet} - Unsupported chain: {chain}")
            newly_processed_ids.add(msg_id)
            continue
        
        if not verified:
            order_results.append(f"REJECTED: {wallet} - Payment verification failed: {verification_note}")
            newly_processed_ids.add(msg_id)
            continue
        
        # Payment verified - run deep scan
        chains_to_scan = ["ethereum", "base", "polygon", "arbitrum", "optimism", "gnosis"]
        scan_success, scan_result = run_deep_scan(wallet, chains_to_scan, msg_id)
        if not scan_success:
            order_results.append(f"REJECTED: {wallet} - Deep scan failed: {scan_result}")
            newly_processed_ids.add(msg_id)
            continue
        
        report_path = scan_result
        try:
            with open(report_path, 'r') as f:
                report_content = f.read()
        except Exception as e:
            order_results.append(f"REJECTED: {wallet} - Could not read report: {str(e)}")
            newly_processed_ids.add(msg_id)
            continue
        
        # Extract key sections (simplistic)
        grade_line = ""
        verdict_line = ""
        risk_breakdown = ""
        approvals_table = ""
        lines = report_content.split('\\n')
        in_approvals = False
        for line in lines:
            if line.startswith("Grade:"):
                grade_line = line.strip()
            elif line.startswith("Verdict:"):
                verdict_line = line.strip()
            elif line.startswith("Risk Breakdown:"):
                risk_breakdown = line.strip()
            elif line.startswith("| Token |"):
                in_approvals = True
            if in_approvals and line.startswith("|"):
                approvals_table += line + "\\n"
            elif in_approvals and not line.startswith("|"):
                in_approvals = False
        
        # Prepare reply email
        reply_subject = f"WalletHygiene Pro Activation - {wallet}"
        reply_body = f"""Thank you for your order.

Payment verified: {verification_note}

Your WalletHygiene Pro report is attached below.

{grade_line}
{verdict_line}
{risk_breakdown}

Approvals Summary:
{approvals_table}

Revoke Links per Chain:
- Ethereum: https://revoke.cash/address={wallet}/ethereum
- Base: https://revoke.cash/address={wallet}/base
- Polygon: https://revoke.cash/address={wallet}/polygon
- Arbitrum: https://revoke.cash/address={wallet}/arbitrum
- Optimism: https://revoke.cash/address={wallet}/optimism
- Gnosis: https://revoke.cash/address={wallet}/gnosis

Your Pro activation is now active.
Monitoring schedule: Daily re-scan with email alerts on new risky approvals.
Renewal date: {plan}ly ({'30 days' if plan == 'monthly' else '365 days'} from today).

Disclaimer: This report is for informational purposes only and does not constitute financial advice."""
        
        # Send reply to original message
        try:
            agentmail_post(f"/api/messages/{msg_id}/reply", {"body": reply_body})
        except Exception as e:
            order_results.append(f"REJECTED: {wallet} - Failed to send reply: {str(e)}")
            newly_processed_ids.add(msg_id)
            continue
        
        # Send report to delivery email
        try:
            agentmail_post("/api/messages", {
                "from": "wallethygiene@agentmail.to",
                "to": delivery_email,
                "subject": reply_subject,
                "body": reply_body
            })
        except Exception as e:
            order_results.append(f"REJECTED: {wallet} - Failed to send delivery email: {str(e)}")
            newly_processed_ids.add(msg_id)
            continue
        
        # Record subscription
        subscription_record = {
            "email": delivery_email,
            "wallet": wallet,
            "plan": plan,
            "started": int(time.time()),
            "renews": int(time.time()) + (30*86400 if plan == "monthly" else 365*86400),
            "last_report": int(time.time())
        }
        append_subscriber(subscription_record)
        
        order_results.append(f"VERIFIED+DELIVERED: {wallet} ({plan})")
        newly_processed_ids.add(msg_id)
    
    # Update processed IDs
    if newly_processed_ids:
        processed_ids.update(newly_processed_ids)
        save_processed_ids(processed_ids)
    
    # Return summary
    if not order_results:
        return "No new orders."
    return "\\n".join(order_results)

if __name__ == "__main__":
    print(main())