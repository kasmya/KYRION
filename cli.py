#!/usr/bin/env python3
"""
AI Auditor - Command Line Interface
"""
import sys
import argparse
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print

from hallucination import detect_hallucinations
from instruction import audit_instruction_adherence
from quality import analyze_code_quality
from exporters import to_json
from report import generate_report

console = Console()


def eprint(*args, **kwargs):
    """Print to stderr (so it doesn't pollute JSON output)"""
    print(*args, file=sys.stderr, **kwargs)


def display_results(results, verbose=False):
    """Display audit results in a formatted way"""
    
    # Header
    print(Panel.fit(
        "[bold blue]AI Auditor Report[/bold blue]",
        border_style="blue"
    ))
    
    # Summary Table
    table = Table(title="Audit Results")
    table.add_column("Tool", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="yellow")
    
    total_issues = 0
    
    for tool_name, tool_result in results.items():
        if "error" in str(tool_result):
            status = "⚠️ Error"
            details = str(tool_result.get("error", "Unknown"))[:50]
            table.add_row(tool_name, status, details)
            continue
        
        if isinstance(tool_result, dict):
            # Instruction adherence
            if "violations" in tool_result:
                violations = tool_result.get("violations", [])
                score = tool_result.get("score", 0)
                mode = tool_result.get("mode", "unknown")
                total_issues += len(violations)
                
                if violations:
                    status = f"⚠️ {len(violations)} violations"
                    details = f"Score: {score}/100 ({mode})"
                else:
                    status = f"✅ Score: {score}/100"
                    details = f"All instructions followed ({mode})"
            
            # Quality analysis
            elif "score" in tool_result and "security_issues" in tool_result:
                score = tool_result.get("score", 0)
                num_issues = tool_result.get("total_issues", 0)
                total_issues += num_issues
                if num_issues > 0:
                    status = f"⚠️ {num_issues} issues"
                    details = f"Score: {score}/100"
                else:
                    status = f"✅ Score: {score}/100"
                    details = "No quality issues"
            
            # Hallucination / dependency results
            elif "issues" in tool_result:
                issues = tool_result.get("issues", [])
                total_issues += len(issues)
                if issues:
                    status = f"⚠️ {len(issues)} issues"
                    details = issues[0][:50] + ("..." if len(issues) > 1 else "")
                else:
                    status = "✅ Clean"
                    details = "No issues found"
            else:
                status = "✅ Complete"
                details = f"{len(tool_result)} items"
        else:
            status = "✅ Complete"
            details = str(tool_result)[:50]
        
        table.add_row(tool_name, status, details)
    
    console.print(table)
    
    # Mode info
    if 'instruction_adherence' in results:
        mode = results['instruction_adherence'].get('mode', 'unknown')
        if mode == 'pattern-matching':
            console.print("\n[dim]💡 Using FREE pattern matching for instruction adherence[/dim]")
    
    # Summary
    print(f"\n[bold]Total Issues Found: [yellow]{total_issues}[/yellow][/bold]")
    
    # Verbose output
    if verbose:
        print("\n[bold cyan]Detailed Results:[/bold cyan]")
        for tool_name, tool_result in results.items():
            print(f"\n[cyan]{tool_name}:[/cyan]")
            if isinstance(tool_result, dict):
                for key, value in tool_result.items():
                    if key != "error" and key != "status":
                        if isinstance(value, list):
                            print(f"  {key}:")
                            if value:
                                for item in value:
                                    print(f"    • {item}")
                            else:
                                print("    None")
                        elif isinstance(value, dict):
                            print(f"  {key}:")
                            for sub_key, sub_value in value.items():
                                print(f"    {sub_key}: {sub_value}")
                        else:
                            print(f"  {key}: {value}")
            else:
                print(f"  {tool_result}")
    
    return total_issues


def main():
    """Entry point for CLI"""
    parser = argparse.ArgumentParser(
        description="AI Auditor - Verify AI-generated code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Text report (default)
  python cli.py code.py
  
  # Text report with verbose output
  python cli.py code.py -v
  
  # With instructions
  python cli.py code.py --prompt "Write code" --instructions "Use type hints" "Add docstring"
  
  # JSON output (for CI/CD) - CLEAN, no progress messages
  python cli.py code.py --format json
  python cli.py code.py --format json > report.json
  
  # HTML output
  python cli.py code.py --format html > report.html
        """
    )
    parser.add_argument("file", help="Path to AI-generated code file")
    parser.add_argument("--prompt", help="Original prompt (optional)", default="")
    parser.add_argument("--instructions", "-i", nargs="+", help="Custom instructions to check", default=[])
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--format", choices=["text", "json", "html"], default="text", help="Output format (text, json, or html)")
    
    args = parser.parse_args()
    
    # Read file
    try:
        with open(args.file, 'r') as f:
            code = f.read()
    except FileNotFoundError:
        eprint(f"❌ File not found: {args.file}")
        eprint("\n💡 Did you mean one of these?")
        eprint("  python cli.py examples/sample_ai_code.py")
        eprint("  python cli.py examples/good_response.py")
        eprint("  python cli.py examples/bad_response.py")
        eprint("  python cli.py examples/my_chatgpt_code.py")
        eprint("  python cli.py examples/ai_api_client.py")
        eprint("\nOr create your own file:")
        eprint("  nano my_code.py")
        return 1
    except PermissionError:
        eprint(f"❌ Permission denied: {args.file}")
        eprint(f"💡 Try: chmod +r {args.file}")
        return 1
    except IsADirectoryError:
        eprint(f"❌ {args.file} is a directory, not a file")
        eprint("💡 Please specify a file, not a folder")
        return 1
    except Exception as e:
        eprint(f"❌ Error reading file: {e}")
        eprint("💡 Check that the file contains valid text")
        return 1
    
    # Show header (skip if JSON or HTML output)
    if args.format not in ["json", "html"]:
        print(Panel.fit(
            "[bold blue]AI Auditor[/bold blue]\n"
            f"[dim]Scanning: {args.file}[/dim]",
            border_style="blue"
        ))
        
        if args.prompt:
            console.print(f"[dim]Prompt: {args.prompt}[/dim]")
        if args.instructions:
            console.print(f"[dim]Instructions: {', '.join(args.instructions)}[/dim]")
            console.print("[dim]Mode: FREE pattern matching[/dim]")
        print()
    
    # Run audits (skip progress if JSON or HTML output)
    if args.format not in ["json", "html"]:
        eprint("[yellow]⏳ Running audits...[/yellow]\n")
    results = {}
    
    # 1. Hallucination Detection
    try:
        results['hallucination'] = detect_hallucinations(code)
    except Exception as e:
        results['hallucination'] = {"error": str(e)}
        eprint(f"❌ Hallucination detection failed: {e}")
    
    # 2. Instruction Adherence
    if args.prompt and args.instructions:
        if args.format not in ["json", "html"]:
            eprint("📋 Checking instruction adherence (FREE pattern matching)...")
        try:
            results['instruction_adherence'] = audit_instruction_adherence(
                args.prompt, code, args.instructions
            )
        except Exception as e:
            results['instruction_adherence'] = {"error": str(e)}
            eprint(f"❌ Instruction adherence failed: {e}")
    elif args.instructions and not args.prompt:
        console.print("[yellow]⚠️  Instructions provided but no prompt. Use --prompt to enable instruction adherence.[/yellow]")
    
    # 3. Code Quality Analysis
    try:
        results['quality'] = analyze_code_quality(code)
    except Exception as e:
        results['quality'] = {"error": str(e)}
        eprint(f"❌ Quality analysis failed: {e}")
    
    # Calculate trust score
    halu_llm = results.get('hallucination', {}).get('llmauditor', {})
    halu_risk = halu_llm.get('hallucination', {}).get('risk_score_pct', 0)
    instr_score = results.get('instruction_adherence', {}).get('score', 0)
    qual_score = results.get('quality', {}).get('score', 0)
    
    halu_score = max(0, 100 - halu_risk) if halu_risk else 70
    trust_score = int((halu_score + instr_score + qual_score) / 3)
    trust_score = max(0, min(100, trust_score))
    results['trust_score'] = trust_score
    
    # === FORMAT OUTPUT ===
    
    # JSON output (clean, no progress)
    if args.format == "json":
        print(to_json(results))
        return 0
    
    # HTML output (clean, no progress)
    if args.format == "html":
        from exporters import to_html
        html_output = to_html(results)
        print(html_output)
        return 0
    
    # Text report (default)
    report = generate_report(results, args.file)
    print(report)
    
    total_issues = results.get('quality', {}).get('total_issues', 0)
    total_issues += len(results.get('hallucination', {}).get('dependency_check', {}).get('hallucinated_imports', []))
    total_issues += len(results.get('instruction_adherence', {}).get('violations', []))
    
    if total_issues > 0:
        print(f"\n[yellow]⚠️  Found {total_issues} issues that need review.[/yellow]")
        return 1
    else:
        print("\n[green]✅ No issues found![/green]")
        return 0


if __name__ == "__main__":
    sys.exit(main())
