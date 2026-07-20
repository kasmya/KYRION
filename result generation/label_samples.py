import os
import pandas as pd

# Path to your sample folders
sample_dirs = [
    'research/samples/deepseek',
    'research/samples/copilot',
    'research/samples/gemini'
]

# Collect all .py files (adjust if you have other extensions)
files = []
for d in sample_dirs:
    if os.path.exists(d):
        for f in os.listdir(d):
            if f.endswith('.py'):
                files.append(os.path.join(d, f))

# Limit to 30–40 files (take first 35 for speed, or random)
files = files[:35]  # you can change this

labels = []
for f in files:
    print(f"\n📄 File: {f}")
    with open(f, 'r', encoding='utf-8', errors='ignore') as file:
        content = file.read()
        # Show first 30 lines to keep terminal readable
        lines = content.splitlines()[:30]
        print('\n'.join(lines))
        if len(content.splitlines()) > 30:
            print("... (truncated)")
    
    while True:
        ans = input("Is this hallucinated? (1 = yes, 0 = no, s = skip): ").strip().lower()
        if ans in ('1', '0'):
            labels.append({'sample_file': os.path.basename(f), 'label': int(ans)})
            break
        elif ans == 's':
            labels.append({'sample_file': os.path.basename(f), 'label': None})
            break
        else:
            print("Please enter 1, 0, or s.")

# Save labels, skipping skipped ones
df = pd.DataFrame(labels)
df = df.dropna(subset=['label'])
df.to_csv('benchmark_labels.csv', index=False)
print(f"\n✅ Saved {len(df)} labels to benchmark_labels.csv")

