#!/usr/bin/env python3
import json
import re
import sys

def extract_order_details(message_json):
    try:
        msg = json.loads(message_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON"}

    # Try to get the full text body from available fields
    body = msg.get("text", "")
    if not body:
        body = msg.get("extractedText", "")
    if not body:
        # Try to get the text/plain body
        parts = msg.get("parts", [])
        for part in parts:
            if part.get("mimeType") == "text/plain":
                body = part.get("body", "")
                break
    if not body:
        # Try the preview (may be truncated)
        preview = msg.get("preview", "")
        if preview:
            body = preview
    if not body:
        # Last resort: snippet
        body = msg.get("snippet", "")

    # Extract wallet: 0x followed by 40 hex chars, or .eth name
    wallet_match = re.search(r'0x[a-fA-F0-9]{40}|[a-zA-Z0-9][a-zA-Z0-9\-]*\.eth', body)
    wallet = wallet_match.group(0) if wallet_match else None

    # Extract tx hash: 0x followed by 64 hex chars
    tx_match = re.search(r'0x[a-fA-F0-9]{64}', body)
    tx_hash = tx_match.group(0) if tx_match else None

    # Extract chain: look for known chain names
    chain_pattern = r'\b(ethereum|base|polygon|arbitrum|optimism|gnosis|tron|stellar|bitcoin|solana)\b'
    chain_match = re.search(chain_pattern, body, re.IGNORECASE)
    chain = chain_match.group(0).lower() if chain_match else "ethereum"

    # Extract delivery email: standard email pattern
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', body)
    delivery_email = email_match.group(0) if email_match else None

    # Extract plan: $9 or $89 or monthly/yearly
    plan_match = re.search(r'\$9|\$89|monthly|yearly', body, re.IGNORECASE)
    plan_str = plan_match.group(0).lower() if plan_match else "monthly"
    if plan_str in ["$9", "monthly"]:
        plan = "monthly"
        usd_amount = 9
    elif plan_str in ["$89", "yearly"]:
        plan = "yearly"
        usd_amount = 89
    else:
        plan = "monthly"
        usd_amount = 9

    # Validate required fields
    missing = []
    if not wallet:
        missing.append("wallet")
    if not tx_hash:
        missing.append("tx hash")
    if not delivery_email:
        missing.append("delivery email")

    if missing:
        return {"error": f"Missing fields: {', '.join(missing)}"}

    return {
        "wallet": wallet,
        "tx_hash": tx_hash,
        "chain": chain,
        "delivery_email": delivery_email,
        "plan": plan,
        "usd_amount": usd_amount
    }

if __name__ == "__main__":
    # Read JSON from stdin
    input_json = sys.stdin.read()
    result = extract_order_details(input_json)
    print(json.dumps(result))