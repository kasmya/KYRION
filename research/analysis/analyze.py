"""
Research Data Analysis Script
Reads results.csv directly and generates statistics
"""
import csv
import statistics
from pathlib import Path

def load_csv(filepath):
    """Load results from CSV file, preserving filenames"""
    data = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Extract filename
            filename = row.get('file', 'unknown')
            # Convert numeric fields
            numeric = {}
            for key, value in row.items():
                if key == 'file':
                    continue
                # Handle empty strings
                if value == '':
                    numeric[key] = 0
                else:
                    try:
                        numeric[key] = int(float(value))
                    except ValueError:
                        numeric[key] = 0
            numeric['file'] = filename
            data.append(numeric)
    return data

def analyze_results(data):
    """Generate summary statistics"""
    if not data:
        return
    
    n = len(data)
    
    # Extract metrics
    trust = [d['trust_score'] for d in data]
    quality = [d['quality_score'] for d in data]
    halu_risk = [d['hallucination_risk'] for d in data]
    halu_imports = [d['hallucinated_imports'] for d in data]
    anti_patterns = [d['anti_patterns'] for d in data]
    dead_code = [d['dead_code'] for d in data]
    code_smells = [d['code_smells'] for d in data]
    issues = [d['total_issues'] for d in data]
    
    def stats(values):
        return {
            'mean': statistics.mean(values) if values else 0,
            'median': statistics.median(values) if values else 0,
            'min': min(values) if values else 0,
            'max': max(values) if values else 0,
            'std': statistics.stdev(values) if len(values) > 1 else 0
        }
    
    print("=" * 60)
    print("📊 RESEARCH DATA SUMMARY")
    print("=" * 60)
    print(f"Total samples: {n}")
    print()
    
    print("📈 AVERAGE SCORES:")
    print(f"  Trust Score:       {stats(trust)['mean']:.1f}/100")
    print(f"  Quality Score:     {stats(quality)['mean']:.1f}/100")
    print(f"  Hallucination Risk: {stats(halu_risk)['mean']:.1f}%")
    print()
    
    print("📋 ISSUE BREAKDOWN (totals):")
    print(f"  Hallucinated Imports: {sum(halu_imports)}")
    print(f"  Anti-Patterns:         {sum(anti_patterns)}")
    print(f"  Dead Code:             {sum(dead_code)}")
    print(f"  Code Smells:           {sum(code_smells)}")
    print()
    
    print("📊 RANGE ANALYSIS:")
    print(f"  Trust Score:       {stats(trust)['min']:.0f} - {stats(trust)['max']:.0f}")
    print(f"  Quality Score:     {stats(quality)['min']:.0f} - {stats(quality)['max']:.0f}")
    print(f"  Hallucination Risk: {stats(halu_risk)['min']:.0f}% - {stats(halu_risk)['max']:.0f}%")
    print(f"  Total Issues:      {stats(issues)['min']:.0f} - {stats(issues)['max']:.0f}")
    print()
    
    # Find best and worst
    best = max(data, key=lambda x: x['trust_score'])
    worst = min(data, key=lambda x: x['trust_score'])
    print("🏆 BEST PERFORMING:")
    print(f"  {best['file']}: Trust={best['trust_score']}, Quality={best['quality_score']}, Hallucination={best['hallucination_risk']}%")
    
    print("\n⚠️ WORST PERFORMING:")
    print(f"  {worst['file']}: Trust={worst['trust_score']}, Quality={worst['quality_score']}, Hallucination={worst['hallucination_risk']}%")
    
    print("\n" + "=" * 60)
    print("📋 DETAILED RESULTS BY SAMPLE")
    print("=" * 60)
    print(f"{'File':<35} | {'Trust':>5} | {'Quality':>5} | {'Halluc':>5} | {'Issues':>5}")
    print("-" * 70)
    
    for d in sorted(data, key=lambda x: x['trust_score'], reverse=True):
        name = d['file'][:33] + "..." if len(d['file']) > 35 else d['file']
        print(f"{name:<35} | {d['trust_score']:>4}  | {d['quality_score']:>4}  | {d['hallucination_risk']:>3}%  | {d['total_issues']:>4}")
    
    print("\n✅ Analysis complete!")

def main():
    csv_path = Path("research/data/results.csv")
    
    if not csv_path.exists():
        print("❌ No results.csv found!")
        print("   Run: python collect_data.py first")
        return
    
    data = load_csv(csv_path)
    analyze_results(data)

if __name__ == "__main__":
    main()
