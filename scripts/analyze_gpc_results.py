#!/usr/bin/env python3
"""
Quick validation script for GPC links results
Analiza data/gpc_links.json y muestra estadísticas
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

def load_results(json_path: Path) -> List[Dict[str, Any]]:
    """Load GPC links results"""
    if not json_path.exists():
        print(f"❌ File not found: {json_path}")
        print("   Run find_gpc_links.py first to generate results.")
        sys.exit(1)
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"❌ Error loading JSON: {e}")
        sys.exit(1)

def analyze_results(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze GPC links results"""
    total = len(data)
    
    # Count completeness
    has_ger = sum(1 for x in data if x.get('ger_url'))
    has_grr = sum(1 for x in data if x.get('grr_url'))
    has_both = sum(1 for x in data if x.get('ger_url') and x.get('grr_url'))
    missing = sum(1 for x in data if not (x.get('ger_url') and x.get('grr_url')))
    
    # Confidence scores
    ger_confs = [x.get('ger_confidence', 0.0) for x in data if x.get('ger_url')]
    grr_confs = [x.get('grr_confidence', 0.0) for x in data if x.get('grr_url')]
    
    avg_ger_conf = sum(ger_confs) / len(ger_confs) if ger_confs else 0.0
    avg_grr_conf = sum(grr_confs) / len(grr_confs) if grr_confs else 0.0
    
    # High confidence (>0.7)
    high_ger = sum(1 for c in ger_confs if c > 0.7)
    high_grr = sum(1 for c in grr_confs if c > 0.7)
    
    # Low confidence (<0.5)
    low_ger = sum(1 for c in ger_confs if c < 0.5)
    low_grr = sum(1 for c in grr_confs if c < 0.5)
    
    # Semantic scores (if available)
    ger_sems = [x.get('ger_semantic_score', 0.0) for x in data if x.get('ger_semantic_score')]
    grr_sems = [x.get('grr_semantic_score', 0.0) for x in data if x.get('grr_semantic_score')]
    
    avg_ger_sem = sum(ger_sems) / len(ger_sems) if ger_sems else None
    avg_grr_sem = sum(grr_sems) / len(grr_sems) if grr_sems else None
    
    # Domain distribution
    domains: Dict[str, int] = {}
    for x in data:
        for url_key in ['ger_url', 'grr_url']:
            url = x.get(url_key)
            if url:
                # Extract domain
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                domains[domain] = domains.get(domain, 0) + 1
    
    return {
        'total': total,
        'has_ger': has_ger,
        'has_grr': has_grr,
        'has_both': has_both,
        'missing': missing,
        'avg_ger_conf': avg_ger_conf,
        'avg_grr_conf': avg_grr_conf,
        'high_ger': high_ger,
        'high_grr': high_grr,
        'low_ger': low_ger,
        'low_grr': low_grr,
        'avg_ger_sem': avg_ger_sem,
        'avg_grr_sem': avg_grr_sem,
        'domains': domains
    }

def print_report(stats: Dict[str, Any], data: List[Dict[str, Any]]):
    """Print analysis report"""
    print("=" * 70)
    print("GPC Links Results Analysis")
    print("=" * 70)
    
    # Completeness
    print("\n📊 Completeness:")
    print(f"  Total GPCs: {stats['total']}")
    print(f"  ✅ Both GER + GRR: {stats['has_both']} ({stats['has_both']/stats['total']*100:.1f}%)")
    print(f"  📄 Has GER only: {stats['has_ger'] - stats['has_both']}")
    print(f"  📄 Has GRR only: {stats['has_grr'] - stats['has_both']}")
    print(f"  ❌ Missing both: {stats['missing']} ({stats['missing']/stats['total']*100:.1f}%)")
    
    # Confidence
    print("\n🎯 Confidence Scores:")
    print(f"  GER average: {stats['avg_ger_conf']:.2f}")
    print(f"    High (>0.7): {stats['high_ger']} ({stats['high_ger']/max(stats['has_ger'], 1)*100:.1f}%)")
    print(f"    Low (<0.5): {stats['low_ger']} ({stats['low_ger']/max(stats['has_ger'], 1)*100:.1f}%)")
    print(f"  GRR average: {stats['avg_grr_conf']:.2f}")
    print(f"    High (>0.7): {stats['high_grr']} ({stats['high_grr']/max(stats['has_grr'], 1)*100:.1f}%)")
    print(f"    Low (<0.5): {stats['low_grr']} ({stats['low_grr']/max(stats['has_grr'], 1)*100:.1f}%)")
    
    # Semantic scores (if available)
    if stats['avg_ger_sem'] is not None or stats['avg_grr_sem'] is not None:
        print("\n🧠 Semantic Similarity (GPU validation):")
        if stats['avg_ger_sem']:
            print(f"  GER average: {stats['avg_ger_sem']:.2f}")
        if stats['avg_grr_sem']:
            print(f"  GRR average: {stats['avg_grr_sem']:.2f}")
    else:
        print("\n🧠 Semantic Similarity: Not available (run with --use-embeddings)")
    
    # Domain distribution
    print("\n🌐 Domain Distribution:")
    sorted_domains = sorted(stats['domains'].items(), key=lambda x: x[1], reverse=True)
    for domain, count in sorted_domains[:10]:
        print(f"  {domain}: {count}")
    if len(sorted_domains) > 10:
        print(f"  ... and {len(sorted_domains) - 10} more")
    
    # Missing details
    if stats['missing'] > 0:
        print(f"\n❌ Missing GPCs ({stats['missing']}):")
        missing_gpcs = [x['title'] for x in data if not (x.get('ger_url') and x.get('grr_url'))]
        for i, title in enumerate(missing_gpcs[:10], 1):
            has_ger = "✓ GER" if any(x['title'] == title and x.get('ger_url') for x in data) else "✗ GER"
            has_grr = "✓ GRR" if any(x['title'] == title and x.get('grr_url') for x in data) else "✗ GRR"
            print(f"  {i}. {title}")
            print(f"     {has_ger} | {has_grr}")
        if len(missing_gpcs) > 10:
            print(f"  ... and {len(missing_gpcs) - 10} more")
    
    # Quality assessment
    print("\n📈 Quality Assessment:")
    completeness = stats['has_both'] / stats['total'] * 100
    avg_confidence = (stats['avg_ger_conf'] + stats['avg_grr_conf']) / 2
    
    if completeness >= 90 and avg_confidence >= 0.7:
        grade = "A+ 🌟"
        assessment = "Excellent! Most GPCs found with high confidence."
    elif completeness >= 80 and avg_confidence >= 0.6:
        grade = "A"
        assessment = "Very good. Minor gaps to fill."
    elif completeness >= 70 and avg_confidence >= 0.5:
        grade = "B"
        assessment = "Good. Some GPCs missing or low confidence."
    elif completeness >= 60:
        grade = "C"
        assessment = "Fair. Consider re-running with more search results."
    else:
        grade = "D"
        assessment = "Poor. Many GPCs missing. Check API keys and connectivity."
    
    print(f"  Overall Grade: {grade}")
    print(f"  {assessment}")
    
    # Recommendations
    print("\n💡 Recommendations:")
    if stats['missing'] > 0:
        print(f"  • Run with --only-missing to update {stats['missing']} incomplete GPCs")
    if stats['low_ger'] + stats['low_grr'] > stats['total'] * 0.2:
        print("  • Many low confidence scores. Try:")
        print("    - Increase --max-results (e.g., 4 or 5)")
        print("    - Lower --min-title-match (e.g., 0.4)")
        print("    - Enable --use-embeddings for better validation")
    if not (stats['avg_ger_sem'] or stats['avg_grr_sem']):
        print("  • GPU validation not used. Consider:")
        print("    - Add --use-embeddings --embedding-device cuda for higher accuracy")
    if completeness >= 95:
        print("  • ✅ Dataset is nearly complete! Great job!")
    
    print("\n" + "=" * 70)

def main():
    # Find data file
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    json_path = repo_root / "data" / "gpc_links.json"
    
    print(f"Loading results from: {json_path}")
    data = load_results(json_path)
    print(f"✅ Loaded {len(data)} GPCs")
    
    stats = analyze_results(data)
    print_report(stats, data)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
