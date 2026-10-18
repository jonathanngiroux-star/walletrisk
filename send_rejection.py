from hermes_tools import tool_call

message_id = "<010001a145b52235-edbc0cc4-30be-4a3c-a160-95c55b90a74a-000000@email.amazonses.com>"
body = """Hello,

Thank you for your interest in WalletHygiene Pro.

We could not verify your payment for the following transaction:
- Chain: ethereum
- Transaction hash: 0xdefinitely-a-test-order-not-a-real-payment-1234
- Expected amount: $9

The transaction hash appears to be invalid or not found on the blockchain. Please double-check:
1. The transaction hash is correct (should be a 64-character hexadecimal string after '0x').
2. The chain is correct (default is ethereum).
3. The transaction is sent to the correct receiving address for ethereum (see our published addresses).
4. The transaction amount is exactly $9 (in USD equivalent).

If you believe this is an error, please contact us with the correct transaction details.

Best regards,
WalletHygiene Tool"""

result = tool_call([{
    "name": "mcp__agentmail__reply_to_message",
    "arguments": {
        "inboxId": "wallethygiene@agentmail.to",
        "messageId": message_id,
        "body": body
    }
}])
print(result)