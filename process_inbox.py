#!/usr/bin/env python3
import sys
import os
import re
import json
import time
from datetime import datetime, timedelta

# Add hermes_tools path
hermes_tools_dir = None
for dirpath, dirnames, filenames in os.walk('/home/manitouabe8ich/.hermes/cache/scratch'):
    if 'hermes_tools.py' in filenames:
        hermes_tools_dir = dirpath
        break
if hermes_tools_dir:
    sys.path.insert(0, hermes_tools_dir)

from hermes_tools import _call

INBOX_ID = 'wallethygiene@agentmail.to'
BASE_DIR = '/home/manitouabe8ich/walletrisk'
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
PROCESSED_FILE = os.path.join(REPORTS_DIR, 'processed_message_ids.json')
SUBSCRIBERS_FILE = os.path.join(REPORTS_DIR, 'subscribers.jsonl')
CONFIG_FILE = os.path.join(BASE_DIR, 'config', 'payments.json')
VERIFICATION_SCRIPT = os.path.join(BASE_DIR, 'scripts', 'verify_payment.py')

def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, 'r') as f:
            processed_ids = set(json.load(f))
    else:
        processed_ids = set()
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            payments_config = json.load(f)
    except Exception as e:
        print(f'Error loading payments config: {e}', file=sys.stderr)
        payments_config = {}
    
    # List messages
    try:
        list_result = _call('mcp__agentmail__list_messages', {'inboxId': INBOX_ID})
    except Exception as e:
        return f'[CRON_FAILURE] Failed to list messages: {str(e)}'
    
    if not list_result or 'result' not in list_result:
        return '[CRON_FAILURE] No result from list_messages'
    
    messages = list_result['result']
    if not isinstance(messages, list):
        return '[CRON_FAILURE] Unexpected messages format'
    
    new_messages = []
    for msg in messages:
        msg_id = msg.get('id')
        if not msg_id:
            continue
        if msg_id in processed_ids:
            continue
        new_messages.append(msg)
    
    if not new_messages:
        return 'No new orders.'
    
    order_results = []
    newly_processed_ids = set()
    
    for msg in new_messages:
        msg_id = msg.get('id')
        try:
            get_result = _call('mcp__agentmail__get_message', {'inboxId': INBOX_ID, 'messageId': msg_id})
        except Exception as e:
            order_results.append(f'SKIPPED-ERROR: {msg_id} - Failed to get message: {str(e)}')
            newly_processed_ids.add(msg_id)
            continue
        
        if not get_result or 'result' not in get_result:
            order_results.append(f'SKIPPED-ERROR: {msg_id} - No message content')
            newly_processed_ids.add(msg_id)
            continue
        
        email_content = get_result['result']
        if isinstance(email_content, dict):
            body = email_content.get('body', '')
            if not body:
                body = json.dumps(email_content)
        else:
            body = str(email_content)
        
        if not body:
            order_results.append(f'SKIPPED-ERROR: {msg_id} - Empty email body')
            newly_processed_ids.add(msg_id)
            continue
        
        # Parse order
        wallet = None
        tx_hash = None
        chain = 'ethereum'
        delivery_email = None
        plan = 'monthly'
        amount_usd = 9
        for line in body.split('\\n'):
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
        
        if not wallet or not tx_hash:
            order_results.append(f'SKIPPED-ERROR: {msg_id} - Missing wallet or tx hash')
            newly_processed_ids.add(msg_id)
            continue
        if not delivery_email:
            order_results.append(f'SKIPPED-ERROR: {msg_id} - Missing delivery email')
            newly_processed_ids.add(msg_id)
            continue
        
        # Verify payment
        verified = False
        verification_note = ''
        if chain in ['ethereum', 'base', 'polygon', 'arbitrum', 'optimism', 'gnosis']:
            cmd = [
                'python3', VERIFICATION_SCRIPT,
                '--chain', chain,
                '--tx', tx_hash,
                '--usd', str(amount_usd)
            ]
            try:
                # Use terminal tool via _call? We cannot call terminal from _call? 
                # We can use the terminal function from hermes_tools if we import it.
                # Let's import terminal as well.
                from hermes_tools import terminal
                result = terminal(
                    command=f'cd {BASE_DIR} && ' + ' '.join(cmd),
                    timeout=60
                )
                if result['exit_code'] == 0:
                    verified = True
                    verification_note = result['output'].strip()
                else:
                    verified = False
                    verification_note = result['output'].strip()
            except Exception as e:
                verified = False
                verification_note = str(e)
        elif chain in ['tron', 'stellar']:
            expected_address = payments_config.get(chain)
            if not expected_address:
                order_results.append(f'REJECTED: {wallet} - No payment address configured for {chain}')
                newly_processed_ids.add(msg_id)
                continue
            # Manual verification via block explorer
            explorer_urls = {
                'tron': f'https://tronscan.org/#/transaction/{tx_hash}',
                'stellar': f'https://stellar.expert/explorer/public/tx/{tx_hash}'
            }
            if chain not in explorer_urls:
                order_results.append(f'REJECTED: {wallet} - Unsupported chain for manual verification: {chain}')
                newly_processed_ids.add(msg_id)
                continue
            url = explorer_urls[chain]
            try:
                from hermes_tools import web_extract
                extracted = web_extract([url], char_limit=20000)
                if not extracted or 'results' not in extracted or not extracted['results']:
                    order_results.append(f'REJECTED: {wallet} - Failed to fetch explorer page')
                    newly_processed_ids.add(msg_id)
                    continue
                content = extracted['results'][0].get('content', '')
                if not content:
                    order_results.append(f'REJECTED: {wallet} - Empty content from explorer')
                    newly_processed_ids.add(msg_id)
                    continue
                if 'Transaction not found' in content or 'No transaction' in content:
                    order_results.append(f'REJECTED: {wallet} - Transaction not found on explorer')
                    newly_processed_ids.add(msg_id)
                    continue
                if expected_address.lower() in content.lower():
                    verified = True
                    verification_note = f'Manually verified via {url}: transaction found and recipient matches.'
                else:
                    verified = False
                    verification_note = f'Recipient address mismatch. Expected {expected_address}, not found in explorer page.'
            except Exception as e:
                order_results.append(f'REJECTED: {wallet} - Manual verification error: {str(e)}')
                newly_processed_ids.add(msg_id)
                continue
        else:
            order_results.append(f'REJECTED: {wallet} - Unsupported chain: {chain}')
            newly_processed_ids.add(msg_id)
            continue
        
        if not verified:
            order_results.append(f'REJECTED: {wallet} - Payment verification failed: {verification_note}')
            newly_processed_ids.add(msg_id)
            continue
        
        # Payment verified - run deep scan
        chains_to_scan = ['ethereum', 'base', 'polygon', 'arbitrum', 'optimism', 'gnosis']
        scan_success = False
        scan_result = ''
        output_file = os.path.join(REPORTS_DIR, f'{msg_id}.md')
        chain_args = []
        for chain in chains_to_scan:
            chain_args.extend(['--chain', chain])
        cmd = [
            'python3', '-m', 'walletrisk', wallet,
            '--deep'
        ] + chain_args + [
            '-o', output_file
        ]
        try:
            from hermes_tools import terminal
            result = terminal(
                command=f'cd {BASE_DIR} && timeout 500 ' + ' '.join(cmd),
                timeout=600
            )
            if os.path.exists(output_file):
                scan_success = True
                scan_result = output_file
            else:
                scan_success = False
                scan_result = result.get('output', 'Scan produced no output')
        except Exception as e:
            scan_success = False
            scan_result = str(e)
        
        if not scan_success:
            order_results.append(f'REJECTED: {wallet} - Deep scan failed: {scan_result}')
            newly_processed_ids.add(msg_id)
            continue
        
        # Read report
        try:
            with open(scan_result, 'r') as f:
                report_content = f.read()
        except Exception as e:
            order_results.append(f'REJECTED: {wallet} - Could not read report: {str(e)}')
            newly_processed_ids.add(msg_id)
            continue
        
        # Extract key sections
        grade_line = ''
        verdict_line = ''
        risk_breakdown = ''
        approvals_table = ''
        lines = report_content.split('\\n')
        in_approvals = False
        for line in lines:
            if line.startswith('Grade:'):
                grade_line = line.strip()
            elif line.startswith('Verdict:'):
                verdict_line = line.strip()
            elif line.startswith('Risk Breakdown:'):
                risk_breakdown = line.strip()
            elif line.startswith('| Token |'):
                in_approvals = True
            if in_approvals and line.startswith('|'):
                approvals_table += line + '\\n'
            elif in_approvals and not line.startswith('|'):
                in_approvals = False
        
        # Prepare reply email
        reply_subject = f'WalletHygiene Pro Activation - {wallet}'
        reply_body = f'''Thank you for your order.

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

Disclaimer: This report is for informational purposes only and does not constitute financial advice.'''
        
        # Send reply to original message
        try:
            _call('mcp__agentmail__reply_to_message', {
                'id': msg_id,
                'body': reply_body
            })
        except Exception as e:
            order_results.append(f'REJECTED: {wallet} - Failed to send reply: {str(e)}')
            newly_processed_ids.add(msg_id)
            continue
        
        # Send report to delivery email
        try:
            _call('mcp__agentmail__send_message', {
                'to': delivery_email,
                'subject': reply_subject,
                'body': reply_body
            })
        except Exception as e:
            order_results.append(f'REJECTED: {wallet} - Failed to send delivery email: {str(e)}')
            newly_processed_ids.add(msg_id)
            continue
        
        # Record subscription
        subscription_record = {
            'email': delivery_email,
            'wallet': wallet,
            'plan': plan,
            'started': int(time.time()),
            'renews': int(time.time()) + (30*86400 if plan == 'monthly' else 365*86400),
            'last_report': int(time.time())
        }
        with open(SUBSCRIBERS_FILE, 'a') as f:
            f.write(json.dumps(subscription_record) + '\\n')
        
        order_results.append(f'VERIFIED+DELIVERED: {wallet} ({plan})')
        newly_processed_ids.add(msg_id)
    
    # Update processed IDs
    if newly_processed_ids:
        processed_ids.update(newly_processed_ids)
        with open(PROCESSED_FILE, 'w') as f:
            json.dump(list(processed_ids), f)
    
    if not order_results:
        return 'No new orders.'
    return '\\n'.join(order_results)

if __name__ == '__main__':
    print(main())