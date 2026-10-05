"""
Part G: Real-Claims Test
Tests non-trivial mathematical claims and logs them inside the mathematical ledger.
"""
from nkp_math import NKPMath
from ledger import Ledger

def run_real_claims():
    print("--- Running Part G: Real-Claims Test ---")
    math_engine = NKPMath()
    ledger_engine = Ledger(difficulty=2)
    
    # Claim 1: Ramanujan's constant near-integer coincidence: e^(pi * sqrt(163))
    # Expected near-integer: 262537412640768743.99999999999925...
    ramanujan_expr = "exp(pi * sqrt(163))"
    v1 = math_engine.value(ramanujan_expr, "262537412640768744", source="RamanujanCoincidence")
    print(f"Ramanujan Constant Coincidence: {v1.status} ({v1.detail})")
    ledger_engine.add_transaction("RamanujanCoincidence", "Ledger", {"expr": ramanujan_expr}, v1.status)
    
    # Claim 2: Trigonometric Identity cos(x)^2 - sin(x)^2 = cos(2*x)
    v2 = math_engine.identity("cos(x)**2 - sin(x)**2", "cos(2*x)", source="TrigIdentity")
    print(f"Identity cos(x)^2 - sin(x)^2 = cos(2*x): {v2.status} ({v2.detail})")
    ledger_engine.add_transaction("TrigIdentity", "Ledger", {"lhs": "cos(x)**2 - sin(x)**2", "rhs": "cos(2*x)"}, v2.status)
    
    # Mine block to secure ledger history
    ledger_engine.mine_pending("Real_Claims_Miner_Node")
    print("\nReal-Claims logged inside ledger successfully.")

if __name__ == '__main__':
    run_real_claims()
