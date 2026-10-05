"""
Ledger: Simple block/transaction cryptographic ledger simulation for mathematical assertion histories.
"""
import hashlib
import json
import time
from typing import Any, Dict, List

class Block:
    def __init__(self, index: int, transactions: List[Dict[str, Any]], previous_hash: str):
        self.index = index
        self.timestamp = time.time()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.nonce = 0
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        block_string = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce
        }, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()

    def mine(self, difficulty: int) -> str:
        target = "0" * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.compute_hash()
        return self.hash

class Ledger:
    def __init__(self, difficulty: int = 2):
        self.chain: List[Block] = []
        self.difficulty = difficulty
        self.pending_transactions: List[Dict[str, Any]] = []
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_block = Block(0, [{"info": "Genesis Block"}], "0")
        genesis_block.mine(self.difficulty)
        self.chain.append(genesis_block)

    def add_transaction(self, sender: str, recipient: str, claim: Dict[str, Any], verdict: str):
        self.pending_transactions.append({
            "sender": sender,
            "recipient": recipient,
            "claim": claim,
            "verdict": verdict,
            "time": time.time()
        })

    def mine_pending(self, miner_address: str):
        if not self.pending_transactions:
            return False
        last_block = self.chain[-1]
        new_block = Block(
            index=last_block.index + 1,
            transactions=self.pending_transactions,
            previous_hash=last_block.hash
        )
        new_block.mine(self.difficulty)
        self.chain.append(new_block)
        self.pending_transactions = [{"reward_to": miner_address, "amount": 1.0}]
        return True

if __name__ == '__main__':
    ledger = Ledger(difficulty=2)
    ledger.add_transaction("Alice", "System", {"identity": "sin(x)^2 + cos(x)^2 = 1"}, "PROVED")
    success = ledger.mine_pending("Miner1")
    assert success
    assert len(ledger.chain) == 2
    print(f"Ledger generated. Blocks count: {len(ledger.chain)}")
    print(f"Latest block hash: {ledger.chain[-1].hash}")
