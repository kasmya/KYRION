"""
Model Comparison Analysis: Automatically detects and compares all models in results.csv
"""
import csv
import statistics
from pathlib import Path
import sys

def load_data():
    data = []
    with open('research/data/results.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data

def analyze_by_model(data):
    # Get all unique model names from the data
    models = sorted(set(r.get('model', 'other') for r in data))
    print("=" * 80)
    print(f"📊 MODEL COMPARISON ({len(models)} models)")
    print("=" * 80)
    print(f"Models found: {', '.join(models)}")
    print()
    
    # Filter data by model
    model_data = {}
    for model in models:
        model_data[model] = [r for r in data if r.get('model', '') == model]
    
    def stats(values):
        if not values:
            return {'mean': 0, 'median': 0, 'min': 0, 'max': 0, 'std': 0}
        nums = [float(v) for v in values]
        return {
            'mean': statistics.mean(nums),
            'median': statistics.median(nums),
            'min': min(nums),
            'max': max(nums),
            'std': statistics.stdev(nums) if len(nums) > 1 else 0
        }
    
    # Print sample count per model
    for model, samples in model_data.items():
        print(f"{model}: {len(samples)} samples")
    print()
    
    # Print average scores for each model
    print("📈 AVERAGE SCORES:")
    print(f"{'Model':<12} {'Trust':>6} {'Quality':>8} {'Halluc%':>8} {'Issues':>7}")
    print("-" * 50)
    
    # Sort models by trust score descending for better readability
    model_order = sorted(
        model_data.keys(),
        key=lambda m: stats([r['trust_score'] for r in model_data[m]])['mean'],
        reverse=True
    )
    
    for model in model_order:
        samples = model_data[model]
        s = stats([r['trust_score'] for r in samples])
        trust = s['mean']
        quality = stats([r['quality_score'] for r in samples])['mean']
        halu = stats([r['hallucination_risk'] for r in samples])['mean']
        issues = stats([r['total_issues'] for r in samples])['mean']
        print(f"{model:<12} {trust:>6.1f} {quality:>8.1f} {halu:>8.1f} {issues:>7.1f}")
    
    # Best and worst performing for each model
    print("\n" + "=" * 80)
    print("🏆 BEST & WORST PERFORMING PER MODEL")
    print("-" * 80)
    
    for model in model_order:
        samples = model_data[model]
        if not samples:
            continue
        best = max(samples, key=lambda x: float(x['trust_score']))
        worst = min(samples, key=lambda x: float(x['trust_score']))
        print(f"\n{model.upper()}:")
        print(f"  Best:  {best['file']} (Trust={best['trust_score']})")
        print(f"  Worst: {worst['file']} (Trust={worst['trust_score']})")

if __name__ == "__main__":
    data = load_data()
    analyze_by_model(data)
