# In research/analysis/graphs.py
import matplotlib.pyplot as plt

#Graph 1: Trust Score Distribution
def plot_trust_distribution(scores):
    """Histogram of trust scores"""
    plt.hist(scores, bins=10, color='blue', alpha=0.7)
    plt.xlabel('Trust Score')
    plt.ylabel('Number of Samples')
    plt.title('Distribution of Trust Scores')
    plt.savefig('research/paper/images/trust_distribution.png')

#Graph 2: Hallucination Risk by LLM
def plot_hallucination_by_llm(data):
    """Box plot of hallucination risk by LLM"""
    import seaborn as sns
    sns.boxplot(x='llm', y='hallucination_risk', data=data)
    plt.title('Hallucination Risk by LLM')
    plt.savefig('research/paper/images/hallucination_by_llm.png')

#Graph 3: Quality Score vs Hallucination Risk
def plot_quality_vs_hallucination(data):
    """Scatter plot of quality vs hallucination"""
    plt.scatter(data['hallucination_risk'], data['quality_score'], alpha=0.7)
    plt.xlabel('Hallucination Risk (%)')
    plt.ylabel('Quality Score')
    plt.title('Quality Score vs Hallucination Risk')
    plt.savefig('research/paper/images/quality_vs_hallucination.png')

#Graph 4: Issue Type Breakdown
def plot_issue_breakdown(issues):
    """Pie chart of issue types"""
    labels = ['Hallucinated Imports', 'Anti-Patterns', 'Security Issues', 'Dead Code', 'Code Smells', 'Instruction Violations']
    sizes = [count for count in issues.values()]
    plt.pie(sizes, labels=labels, autopct='%1.1f%%')
    plt.title('Issue Type Breakdown')
    plt.savefig('research/paper/images/issue_breakdown.png')

#Graph 5: Instruction Adherence Distribution
def plot_instruction_adherence(scores):
    """Histogram of instruction adherence scores"""
    plt.hist(scores, bins=5, color='green', alpha=0.7)
    plt.xlabel('Instruction Adherence Score')
    plt.ylabel('Number of Samples')
    plt.title('Instruction Adherence Distribution')
    plt.savefig('research/paper/images/instruction_adherence.png')
