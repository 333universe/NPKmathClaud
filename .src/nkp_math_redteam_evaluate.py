# Run the newly written red-team test suite
import subprocess
print("Evaluating engine against Red-Team Set A and Set B...")
result = subprocess.run(["python", "nkp_math_redteam.py"], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("Errors:", result.stderr)
