#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess

INBOX_ID = "wallethygiene@agentmail.to"
BASE_DIR = "/home/manitouabe8ich/walletrisk"
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
PROCESSED_FILE = os.path.join(REPORTS_DIR, "processed_message_ids.json")
SUBSCRIBERS_FILE = os.path.join(REPORTS_DIR, "subscribers.jsonl")
CONFIG_FILE = os.path.join(BASE_DIR, "config", "payments.json")
VERIFICATION_SCRIPT = os.path.join(BASE_DIR, "scripts", "verify_payment.py")
API_KEY = "am_us_3a0d9f7e9747b30704f9d44d9a1dacf2d0f64b5fb503be234ca9c9281e6b3865"

def terminal_subprocess(command, timeout=None, workdir=None):
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir or BASE_DIR
        )
        return {
            "output": result.stdout + result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"output": "Timeout expired", "exit_code": -1}
    except Exception as e:
        return {"output": str(e), "exit_code": -1}

def read_file_simple(path):
    try:
        with open(path, 'r') as f:
            return f.read()
    except Exception as e:
        return None

def write_file_simple(path, content):
    try:
        with open(path, 'w') as f:
            f.write(content)
        return True
    except Exception as e:
        return False

def web_extract_simple(url):
    cmd = f'curl -s -L --max-time 30 "{url}"'
    result = terminal_subprocess(cmd, timeout=30)
    if result["exit_code"] == 0:
        return result["output"]
    else:
        return None

def make_agentmail_request(method, endpoint, data=None):
    url = f"https://api.agentmail.to{endpoint}"
    headers = [
        f'Authorization: Bearer {API_KEY}',
        'Content-Type: application/json'
    ]
    if method == "GET":
        cmd_parts = ['curl', '-s']
        for h in headers:
            cmd_parts.extend(['-H', h])
        cmd_parts.append(url)
        cmd = ' '.join(cmd_parts)
    elif method == "POST":
        data_json = json.dumps(data) if data else '{}'
        cmd_parts = ['curl', '-s', '-X', 'POST']
        for h in headers:
            cmd_parts.extend(['-H', h])
        cmd_parts.extend(['-d', data_json])
        cmd_parts.append(url)
        cmd = ' '.join(cmd_parts)
    else:
        raise Exception(f"Unsupported method: {method}")
    result = terminal_subprocess(cmd, timeout=30)
    if result["exit_code"] != 0:
        raise Exception(f"API request failed: {result.get('output', '')}")
    try:
        return json.loads(result["output"])
    except json.JSONDecodeError:
        return result["output"]

def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    processed_ids = set()
    if os.path.exists(PROCESSED_FILE):
        content = read_file_simple(PROCESSED_FILE)
        if content is not None:
            try:
                processed_ids = set(json.loads(content))
            except Exception as e:
                print(f"Error loading processed IDs: {e}", file=sys.stderr)
                processed_ids = set()
    else:
        processed_ids = set()
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            payments_config = json.load(f)
    except Exception as e:
        print(f"Error loading payments config: {e}", file=sys.stderr)
        payments_config = {}
    
    try:
        messages = make_agentmail_request("GET", f"/api/inboxes/{INBOX_ID}/messages")
    except Exception as e:
        return f"[CRON_FAILURE]\nFailed to list messages: {str(e)}"
    
    if not isinstance(messages, list):
        return "[CRON_FAILURE]\nUnexpected messages format"
    
    new_messages = []
    for msg in messages:
        msg_id = msg.get("id")
        if not msg_id:
            continue
        if msg_id in processed_ids:
            continue
        new_messages.append(msg)
    
    if not new_messages:
        return "No new orders."
    
    order_results = []
    newly_processed_ids = set()
    
    for msg in new_messages:
        msg_id = msg.get("id")
        try:
            message = make_agentmail_request("GET", f"/api/messages/{msg_id}")
        except Exception as e:
            order_results.append(f"SKIPPED-ERROR: {msg_id} - Failed to get message: {str(e)}")
            newly_processed_ids.add(msg_id)
            continue
        
        if not message:
            order_results.append(f"SKIPPED-ERROR: {msg_id} - No message content")
            newly_processed_ids.add(msg_id)
            continue
        
        body = message.get("body", "")
        if not body:
            body = json.dumps(message)
        
        if not body:
            order_results.append(f"SKIPPED-ERROR: {msg_id} - Empty email body")
            newly_processed_ids.add(msg_id)
            continue
        
        order_data, error = parse_order_email(body)
        if error:
            order_results.append(f"SKIPPED-ERROR: {msg_id} - {error}")
            newly_processed_ids.add(msg_id)
            continue
        
        wallet = order_data["wallet"]
        tx_hash = order_data["tx_hash"]
        chain = order_data["chain"].lower()
        delivery_email = order_data["delivery_email"]
        plan = order_data["plan"]
        amount_usd = order_data["amount_usd"]
        
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
        
        grade_line = ""
        verdict_line = ""
        risk_breakdown = ""
        approvals_table = ""
        lines = report_content.split('\n')
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
                approvals_table += line + "\n"
            elif in_approvals and not line.startswith("|"):
                in_approvals = False
        
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
- Ethereum: https://revoke.cash/address/{wallet}/ethereum
- Base: https://revoke.cash/address/{wallet}/base
- Polygon: https://revoke.cash/address/{wallet}/polygon
- Arbitrum: https://revoke.cash/address/{wallet}/arbitrum
- Optimism: https://revoke.cash/address/{wallet}/optimism
- Gnosis: https://revoke.cash/address/{wallet}/gnosis

Your Pro activation is now active.
Monitoring schedule: Daily re-scan with email alerts on new risky approvals.
Renewal date: {plan}ly ({'30 days' if plan == 'monthly' else '365 days'} from today).

Disclaimer: This report is for informational purposes only and does not constitute financial advice."""
        
        try:
            make_agentmail_request("POST", f"/api/messages/{msg_id}/reply", {"body": reply_body})
        except Exception as e:
            order_results.append(f"REJECTED: {wallet} - Failed to send reply: {str(e)}")
            newly_processed_ids.add(msg_id)
            continue
        
        try:
            make_agentmail_request("POST", "/api/messages", {
                "to": delivery_email,
                "subject": reply_subject,
                "body": reply_body
            })
        except Exception as e:
            order_results.append(f"REJECTED: {wallet} - Failed to send delivery email: {str(e)}")
            newly_processed_ids.add(msg_id)
            continue
        
        subscription_record = {
            "email": delivery_email,
            "wallet": wallet,
            "plan": plan,
            "started": int(time.time()),
            "renews": int(time.time()) + (30*86400 if plan == "monthly" else 365*86400),
            "last_report": int(time.time())
        }
        with open(SUBSCRIBERS_FILE, 'a') as f:
            f.write(json.dumps(subscription_record) + "\n")
        
        order_results.append(f"VERIFIED+DELIVERED: {wallet} ({plan})")
        newly_processed_ids.add(msg_id)
    
    if newly_processed_ids:
        processed_ids.update(newly_processed_ids)
        write_file_simple(PROCESSED_FILE, json.dumps(list(processed_ids)))
    
    if not order_results:
        return "No new orders."
    return "\n".join(order_results)

def parse_order_email(email_content):
    lines = email_content.split('\n')
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
        result = terminal_subprocess(
            f"cd {BASE_DIR} && {' '.join(cmd)}",
            timeout=60
        )
        if result["exit_code"] == 0:
            return True, result["output"].strip()
        else:
            return False, result["output"].strip()
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
        extracted = web_extract_simple(url)
        if extracted is None:
            return False, "Failed to fetch explorer page"
        if not extracted:
            return False, "Empty content from explorer"
        if "Transaction not found" in extracted or "No transaction" in extracted:
            return False, "Transaction not found on explorer"
        if expected_address.lower() in extracted.lower():
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
        result = terminal_subprocess(
            f"cd {BASE_DIR} && timeout 500 {' '.join(cmd)}",
            timeout=600
        )
        if os.path.exists(output_file):
            return True, output_file
        else:
            return False, result.get("output", "Scan produced no output")
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    print(main())