#!/usr/bin/env python3
import sys
import re
import json

def parse_order_email(text):
    wallet = None
    tx_hash = None
    chain = "ethereum"
    delivery_email = None
    plan = "monthly"
    amount_usd = 9

    for line in text.split('\\n'):
        line = line.strip()
        if line.lower().startswith('wallet:'):
            wallet = line.split(':', 1)[1].strip()
        elif line.lower().startswith('tx hash:'):
            tx_hash = line.split(':', 1)[1].strip()
        elif line.lower().startswith('chain:'):
            chain = line.split(':', 1)[1].strip().lower()
        elif line.lower().startswith('delivery email:'):
            delivery_email = line.split(':', 1)[1].strip()
        elif line.lower().startswith('plan:'):
            plan_text = line.split(':', 1)[1].strip().lower()
            if 'yearly' in plan_text:
                plan = 'yearly'
                amount_usd = 89
            else:
                plan = 'monthly'
                amount_usd = 9

    return {
        "wallet": wallet,
        "tx_hash": tx_hash,
        "chain": chain,
        "delivery_email": delivery_email,
        "plan": plan,
        "amount_usd": amount_usd
    }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: parse_email.py <email_body>", file=sys.stderr)
        sys.exit(1)
    body = sys.argv[1]
    result = parse_order_email(body)
    print(json.dumps(result))