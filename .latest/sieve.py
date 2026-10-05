"""
Sieve: A basic prime sieve and utility library to support our mathematical ledger operations.
"""
import math

def prime_sieve(limit: int):
    """Return a list of primes up to limit using the Sieve of Eratosthenes."""
    if limit < 2:
        return []
    sieve = [True] * (limit + 1)
    sieve[0] = sieve[1] = False
    for i in range(2, int(math.isqrt(limit)) + 1):
        if sieve[i]:
            for j in range(i*i, limit + 1, i):
                sieve[j] = False
    return [i for i, is_prime in enumerate(sieve) if is_prime]

if __name__ == '__main__':
    primes = prime_sieve(30)
    print(f"Primes up to 30: {primes}")
    assert primes == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
