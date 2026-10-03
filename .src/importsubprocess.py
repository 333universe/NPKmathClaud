
import subprocess

# Re-run the final test benchmark seeds 100:120
print("Re-running benchmark on test seeds 100:120...")
res_bench = subprocess.run([
    "python", "nkp_math_bench.py",
    "--seeds", "100:120",
    "--out", "test_100_120.json"
], capture_output=True, text=True)
print(res_bench.stdout)
if res_bench.stderr:
    print("Errors:", res_bench.stderr)

# Print report
print("\n--- Final Benchmark Report ---")
res_report = subprocess.run([
    "python", "nkp_math_bench.py",
    "--report", "test_100_120.json"
], capture_output=True, text=True)
print(res_report.stdout)
if res_report.stderr:
    print("Errors:", res_report.stderr)
