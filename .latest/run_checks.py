"""
Run Checks: Validates assertions through our NKPMath engine and logs transactions inside the secure cryptographic ledger.
"""
import sys
from nkp_math import NKPMath
from ledger import Ledger
from sieve import prime_sieve

def run_suite():
    print("--- Executing Mathematical Claim Verification Gate ---")
    math_engine = NKPMath()
    ledger_engine = Ledger(difficulty=2)
    
    # Test algebraic identity
    v1 = math_engine.identity("sin(x)**2 + cos(x)**2", "1", source="IdentityChecker")
    print(f"Identity sin^2(x) + cos^2(x) = 1: {v1.status} ({v1.detail})")
    ledger_engine.add_transaction("IdentityChecker", "Ledger", {"lhs": "sin(x)**2+cos(x)**2", "rhs": "1"}, v1.status)
    
    # Test numerical verification
    v2 = math_engine.value("pi", "3.141592653589793", source="ValueChecker")
    print(f"Value verification of Pi: {v2.status} ({v2.detail})")
    ledger_engine.add_transaction("ValueChecker", "Ledger", {"expr": "pi", "val": "3.141592653589793"}, v2.status)
    
    # Check prime distribution claims (Sieve component validation)
    primes_under_50 = prime_sieve(50)
    primes_count = len(primes_under_50)
    expected_count = 15  # 15 primes below 50
    sieve_status = "VERIFIED" if primes_count == expected_count else "REFUTED"
    print(f"Primes under 50 count claim: {sieve_status} (Found {primes_count}, expected {expected_count})")
    ledger_engine.add_transaction("SieveChecker", "Ledger", {"limit": 50, "expected": expected_count}, sieve_status)
    
    # Execute Block Mining sequence on pending operations
    success = ledger_engine.mine_pending("Validation_Miner_Node")
    if success and v1.accepted and v2.accepted and sieve_status == "VERIFIED":
        print("\nRESULT: ALL PASS")
    else:
        print("\nRESULT: FAIL - Validation errors identified")
        sys.exit(1)

if __name__ == '__main__':
    run_suite()
