import json
import os
import re
import time
import subprocess
from hermes_tools import tool_call, tool_describe

BASE_DIR = "/home/manitouabe8ich/walletrisk"
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
PROCESSED_FILE = os.path.join(REPORTS_DIR, "processed_message_ids.json")
SUBSCRIBERS_FILE = os.path.join(REPORTS_DIR, "subscribers.jsonl")

os.makedirs(REPORTS_DIR, exist_ok=True)

# Load processed IDs
if os.path.exists(PROCESSED_FILE):
    with open(PROCESSED_FILE, 'r') as f:
        processed_ids = set(json.load(f))
else:
    processed_ids = set()

# List messages
try:
    list_res = tool_call(
        name="mcp__agentmail__list_messages",
        arguments={"inboxId": "wallethygiene@agentmail.to"}
    )
    if not list_res or "messages" not in list_res:
        print("[CRON_FAILURE] Failed to list messages")
        exit(1)
    messages = list_res["messages"]
except Exception as e:
    print(f"[CRON_FAILURE] Exception listing messages: {e}")
    exit(1)

# Filter new and unread
new_messages = []
for msg in messages:
    msg_id = msg.get("id")
    if not msg_id or msg_id in processed_ids:
        continue
    # Assume unread if not marked as read (adjust based on actual API)
    if msg.get("read", False):
        continue
    new_messages.append(msg)

if not new_messages:
    print("No new orders.")
    exit(0)

summaries = []
for msg in new_messages:
    msg_id = msg.get("id")
    try:
        get_res = tool_call(
            name="mcp__agentmail__get_message",
            arguments={"id": msg_id}
        )
        if not get_res or "body" not in get_res:
            print(f"[CRON_FAILURE] Failed to get message {msg_id}")
            processed_ids.add(msg_id)
            continue
        body = get_res["body"]
        # Extract wallet
        wallet_match = re.search(r'(0x[a-fA-F0-9]{40}|[a-zA-Z0-9][a-zA-Z0-9\-]*\.eth)', body)
        if not wallet_match:
            # Reply asking for wallet
            tool_call(
                name="mcp__agentmail__reply_to_message",
                arguments={
                    "id": msg_id,
                    "body": "Could not find a valid wallet address (0x... or ENS) in your order. Please include your wallet address."
                }
            )
            processed_ids.add(msg_id)
            continue
        wallet = wallet_match.group(1)
        # Extract tx hash
        tx_match = re.search(r'0x[a-fA-F0-9]{64}', body)
        if not tx_match:
            tool_call(
                name="mcp__agentmail__reply_to_message",
                arguments={
                    "id": msg_id,
                    "body": "Could not find a valid transaction hash (0x followed by 64 hex characters) in your order."
                }
            )
            processed_ids.add(msg_id)
            continue
        tx_hash = tx_match.group(0)
        # Extract chain
        chain_match = re.search(r'Chain:\s*([a-zA-Z0-9]+)', body, re.IGNORECASE)
        chain = chain_match.group(1).lower() if chain_match else "ethereum"
        # Extract delivery email
        email_match = re.search(r'Delivery\s+email:\s*([^\s@]+@[^\s@]+\.[^\s@]+)', body, re.IGNORECASE)
        if email_match:
            delivery_email = email_match.group(1)
        else:
            # Fallback to sender
            sender = get_res.get("from", "")
            if sender and "@" in sender:
                delivery_email = sender
            else:
                tool_call(
                    name="mcp__agentmail__reply_to_message",
                    arguments={
                        "id": msg_id,
                        "body": "Could not find a delivery email address. Please include a 'Delivery email:' line."
                    }
                )
                processed_ids.add(msg_id)
                continue
        # Extract plan
        plan_match = re.search(r'Plan:\s*(monthly|yearly)', body, re.IGNORECASE)
        plan = plan_match.group(1).lower() if plan_match else "monthly"
        usd_amount = 9 if plan == "monthly" else 89

        # Verify payment
        verify_cmd = f"cd {BASE_DIR} && python3 scripts/verify_payment.py --chain {chain} --tx {tx_hash} --usd {usd_amount}"
        verify_result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True, timeout=30)
        if verify_result.returncode != 0:
            error_output = verify_result.stderr.strip() or verify_result.stdout.strip()
            tool_call(
                name="mcp__agentmail__reply_to_message",
                arguments={
                    "id": msg_id,
                    "body": f"Payment verification failed for transaction {tx_hash} on chain {chain}. "
                            f"Please double-check the tx hash and chain, or confirm the receiving address matches the published one.\n"
                            f"Error: {error_output}"
                }
            )
            processed_ids.add(msg_id)
            continue

        # Payment verified, run deep scan
        report_filename = f"report_{msg_id}_{int(time.time())}.md"
        report_path = os.path.join(REPORTS_DIR, report_filename)
        scan_cmd = f"cd {BASE_DIR} && timeout 500 python3 -m walletrisk {wallet} --deep --chain ethereum --chain base --chain polygon --chain arbitrum --chain optimism --chain gnosis -o {report_path}"
        scan_result = subprocess.run(scan_cmd, shell=True, capture_output=True, text=True, timeout=600)
        if not os.path.exists(report_path):
            tool_call(
                name="mcp__agentmail__reply_to_message",
                arguments={
                    "id": msg_id,
                    "body": "The deep scan failed to generate a report. Please try again later or contact support."
                }
            )
            processed_ids.add(msg_id)
            continue

        with open(report_path, 'r') as f:
            report_content = f.read()

        # Reply to order email
        renews = time.time() + (30 if plan == 'monthly' else 365) * 86400
        reply_body = f"""Thank you for your order.

Your wallet hygiene report is attached below.

{report_content}

Your Pro activation is confirmed. You will receive daily re-scans and email alerts on new approvals.
Renewal date: {time.strftime('%Y-%m-%d', time.localtime(renews))}.

Disclaimer: This report is for informational purposes only and does not constitute financial advice.
"""
        tool_call(
            name="mcp__agentmail__reply_to_message",
            arguments={
                "id": msg_id,
                "body": reply_body
            }
        )

        # Send to delivery email
        send_result = tool_call(
            name="mcp__agentmail__send_message",
            arguments={
                "to": delivery_email,
                "subject": "Your WalletHygiene Pro Report",
                "body": f"""Your wallet hygiene report is attached below.

{report_content}

You have been enrolled in WalletHygiene Pro monitoring. Daily re-scans will be performed and you will receive email alerts on new risky approvals.
Your subscription started today and renews on {time.strftime('%Y-%m-%d', time.localtime(renews))}.

Disclaimer: This report is for informational purposes only and does not constitute financial advice.
"""
            }
        )

        # Record subscription
        subscriber_record = {
            "email": delivery_email,
            "wallet": wallet,
            "plan": plan,
            "started": int(time.time()),
            "renews": int(renews),
            "last_report": int(time.time())
        }
        with open(SUBSCRIBERS_FILE, 'a') as f:
            f.write(json.dumps(subscriber_record) + "\n")

        processed_ids.add(msg_id)
        summaries.append(f"VERIFIED+DELIVERED: {wallet} ({plan}) to {delivery_email}")

    except Exception as e:
        print(f"[CRON_FAILURE] Error processing message {msg_id}: {e}")
        processed_ids.add(msg_id)
        continue

# Save processed IDs
with open(PROCESSED_FILE, 'w') as f:
    json.dump(list(processed_ids), f)

# Print summaries
for summary in summaries:
    print(summary)
