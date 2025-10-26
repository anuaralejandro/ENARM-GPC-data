#!/usr/bin/env python3
"""
📊 VERIFICACIÓN FINAL DE CALIDAD DE GPCs

Muestra estadísticas detalladas de los resultados finales:
- Cobertura total (GER+GRR)
- Distribución de confianza
- Fuentes de datos (CENETEC, IMSS, cache, etc.)
- Coherencia de IDs
- Casos problemáticos
"""

import json
from pathlib import Path
from collections import Counter
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = REPO_ROOT / "data" / "gpc_links.json"


def extract_gpc_number(url: str) -> str:
    """Extrae número de GPC del URL."""
    import re
    if not url:
        return "N/A"
    
    # Patrón 1: guiasclinicas/XXXGER.pdf
    match = re.search(r'guiasclinicas/(\d+)(?:GER|GRR)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Patrón 2: IMSS-XXX-YY/ER.pdf
    match = re.search(r'(?:IMSS|SS|GPC)-(\d+)-\d+/', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    return "N/A"


def get_domain(url: str) -> str:
    """Extrae dominio del URL."""
    if not url:
        return "N/A"
    
    url_lower = url.lower()
    if "cenetec-difusion.com" in url_lower:
        return "CENETEC-difusion"
    elif "cenetec.salud.gob.mx" in url_lower:
        return "CENETEC-salud"
    elif "imss.gob.mx" in url_lower:
        return "IMSS"
    elif "salud.gob.mx" in url_lower:
        return "Salud"
    else:
        return "Otro"


def main():
    if not OUT_JSON.exists():
        print(f"❌ No se encontró {OUT_JSON}")
        return
    
    data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    
    print("\n" + "="*80)
    print("📊 VERIFICACIÓN FINAL DE CALIDAD DE GPCs")
    print("="*80 + "\n")
    
    # Estadísticas básicas
    total = len(data)
    with_ger = sum(1 for x in data if x.get('ger_url'))
    with_grr = sum(1 for x in data if x.get('grr_url'))
    complete = sum(1 for x in data if x.get('ger_url') and x.get('grr_url'))
    
    print("📈 COBERTURA GENERAL:")
    print(f"  - Total GPCs: {total}")
    print(f"  - Con GER: {with_ger}/{total} ({with_ger/total*100:.1f}%)")
    print(f"  - Con GRR: {with_grr}/{total} ({with_grr/total*100:.1f}%)")
    print(f"  - Completos (GER+GRR): {complete}/{total} ({complete/total*100:.1f}%)\n")
    
    # Distribución de confianza
    conf_ranges = {
        "95-100%": 0,
        "85-94%": 0,
        "70-84%": 0,
        "50-69%": 0,
        "<50%": 0
    }
    
    for item in data:
        ger_conf = item.get('ger_confidence', 0)
        grr_conf = item.get('grr_confidence', 0)
        avg_conf = (ger_conf + grr_conf) / 2 if ger_conf and grr_conf else (ger_conf or grr_conf or 0)
        
        if avg_conf >= 95:
            conf_ranges["95-100%"] += 1
        elif avg_conf >= 85:
            conf_ranges["85-94%"] += 1
        elif avg_conf >= 70:
            conf_ranges["70-84%"] += 1
        elif avg_conf >= 50:
            conf_ranges["50-69%"] += 1
        else:
            conf_ranges["<50%"] += 1
    
    print("🎯 DISTRIBUCIÓN DE CONFIANZA (promedio GER+GRR):")
    for range_name, count in conf_ranges.items():
        print(f"  - {range_name}: {count} GPCs ({count/total*100:.1f}%)")
    print()
    
    # Fuentes de datos
    ger_sources = Counter(x.get('ger_source', 'N/A') for x in data if x.get('ger_url'))
    grr_sources = Counter(x.get('grr_source', 'N/A') for x in data if x.get('grr_url'))
    
    print("📦 FUENTES DE DATOS - GER:")
    for source, count in ger_sources.most_common():
        print(f"  - {source}: {count} ({count/with_ger*100:.1f}%)")
    print()
    
    print("📦 FUENTES DE DATOS - GRR:")
    for source, count in grr_sources.most_common():
        print(f"  - {source}: {count} ({count/with_grr*100:.1f}%)")
    print()
    
    # Dominios
    ger_domains = Counter(get_domain(x.get('ger_url')) for x in data if x.get('ger_url'))
    grr_domains = Counter(get_domain(x.get('grr_url')) for x in data if x.get('grr_url'))
    
    print("🌐 DISTRIBUCIÓN POR DOMINIO - GER:")
    for domain, count in ger_domains.most_common():
        print(f"  - {domain}: {count} ({count/with_ger*100:.1f}%)")
    print()
    
    print("🌐 DISTRIBUCIÓN POR DOMINIO - GRR:")
    for domain, count in grr_domains.most_common():
        print(f"  - {domain}: {count} ({count/with_grr*100:.1f}%)")
    print()
    
    # Coherencia de IDs
    incoherent = []
    for item in data:
        ger_url = item.get('ger_url')
        grr_url = item.get('grr_url')
        
        if ger_url and grr_url:
            ger_num = extract_gpc_number(ger_url)
            grr_num = extract_gpc_number(grr_url)
            
            if ger_num != "N/A" and grr_num != "N/A" and ger_num != grr_num:
                incoherent.append({
                    'title': item['title'],
                    'ger_num': ger_num,
                    'grr_num': grr_num
                })
    
    coherent = complete - len(incoherent)
    print(f"🔗 COHERENCIA DE IDs (GER y GRR mismo número):")
    print(f"  - Coherentes: {coherent}/{complete} ({coherent/complete*100:.1f}%)")
    print(f"  - Incoherentes: {len(incoherent)}/{complete} ({len(incoherent)/complete*100:.1f}%)\n")
    
    if incoherent and len(incoherent) <= 20:
        print("⚠️  CASOS INCOHERENTES (top 20):")
        for case in incoherent[:20]:
            print(f"  - {case['title'][:60]}")
            print(f"    GER: {case['ger_num']} | GRR: {case['grr_num']}")
        print()
    
    # Casos de baja confianza
    low_conf = [x for x in data if 
                (x.get('ger_confidence', 100) < 70 or x.get('grr_confidence', 100) < 70) and
                (x.get('ger_url') or x.get('grr_url'))]
    
    if low_conf:
        print(f"⚠️  CONFIANZA BAJA (<70%): {len(low_conf)} GPCs")
        if len(low_conf) <= 10:
            for item in low_conf:
                print(f"  - {item['title'][:60]}")
                print(f"    GER: {item.get('ger_confidence', 0):.1f}% | GRR: {item.get('grr_confidence', 0):.1f}%")
        print()
    
    # Faltantes
    missing = [x for x in data if not x.get('ger_url') or not x.get('grr_url')]
    
    if missing:
        print(f"❌ FALTANTES: {len(missing)} GPCs")
        for item in missing[:10]:
            status = []
            if not item.get('ger_url'):
                status.append("GER falta")
            if not item.get('grr_url'):
                status.append("GRR falta")
            print(f"  - {item['title'][:60]} ({', '.join(status)})")
        print()
    
    # Resumen final
    print("="*80)
    print("✅ RESUMEN FINAL:")
    print(f"  - Cobertura: {complete}/{total} GPCs completos ({complete/total*100:.1f}%)")
    print(f"  - Calidad: {conf_ranges['95-100%'] + conf_ranges['85-94%']}/{total} con confianza ≥85% ({(conf_ranges['95-100%'] + conf_ranges['85-94%'])/total*100:.1f}%)")
    print(f"  - Coherencia: {coherent}/{complete} con IDs coherentes ({coherent/complete*100:.1f}%)")
    
    # Score final
    coverage_score = (complete / total) * 100
    quality_score = ((conf_ranges['95-100%'] + conf_ranges['85-94%']) / total) * 100
    coherence_score = (coherent / complete) * 100 if complete > 0 else 0
    final_score = (coverage_score + quality_score + coherence_score) / 3
    
    print(f"\n🏆 SCORE FINAL: {final_score:.1f}/100")
    
    if final_score >= 95:
        print("   🎉 ¡EXCELENTE! Calidad máxima alcanzada")
    elif final_score >= 85:
        print("   ✅ MUY BUENO - Calidad aceptable")
    elif final_score >= 75:
        print("   ⚠️  REGULAR - Considerar mejoras")
    else:
        print("   ❌ BAJO - Requiere atención")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
