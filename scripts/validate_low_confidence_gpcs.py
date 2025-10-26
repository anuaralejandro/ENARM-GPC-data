#!/usr/bin/env python3
"""
🔍 VALIDACIÓN AI PARA GPCs CON BAJA CONFIANZA (<85%) Y FALTANTES

Este script:
1. Lee gpc_links.json
2. Identifica GPCs con:
   - Confianza <85% (ger_confidence o grr_confidence)
   - URLs faltantes (ger_url o grr_url == None)
3. Re-valida con AI + OCR (GPU)
4. Busca de nuevo si validación falla
5. Actualiza JSON/CSV/MD con resultados mejorados

Estrategia de validación:
- Descarga PDF
- OCR + AI classification
- Si confianza sube a ≥85% → mantener
- Si confianza sigue baja → buscar alternativas
- Si faltante → buscar con estrategias ultra-flexibles
"""

from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.find_gpc_links import (
    GPCLinkResult,
    SearchProvider,
    GoogleCSEProvider,
    SerperProvider,
    SerpAPIProvider,
    SemanticValidator,
    download_pdf,
    get_domain_priority,
    classify_url_type,
    write_outputs,
    load_imss_catalog,
)

from scripts.find_gpc_links_second_pass import (
    search_flexible,
    find_in_imss_catalog_by_year,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = REPO_ROOT / "data" / "gpc_links.json"


def choose_provider() -> SearchProvider:
    """Same as other scripts."""
    import os
    g_key = os.environ.get("GOOGLE_API_KEY")
    g_cse = os.environ.get("GOOGLE_CSE_ID")
    serpapi_key = os.environ.get("SERPAPI_API_KEY")
    serper_key = os.environ.get("SERPER_API_KEY")
    
    if g_key and g_cse:
        return GoogleCSEProvider(g_key, g_cse)
    if serpapi_key:
        return SerpAPIProvider(serpapi_key)
    if serper_key:
        return SerperProvider(serper_key)
    
    raise RuntimeError("No search provider configured.")


def validate_existing_url(url: str, expected_title: str, expected_type: str, 
                          validator: SemanticValidator) -> tuple[bool, float, str]:
    """
    Re-valida un URL existente con AI.
    
    Returns: (es_válido, confianza, tipo_detectado)
    """
    if not url:
        return (False, 0.0, "UNKNOWN")
    
    # Descargar PDF
    pdf_bytes = download_pdf(url)
    if not pdf_bytes or len(pdf_bytes) < 1000:
        return (False, 0.0, "UNKNOWN")
    
    # Validar con AI
    url_type = classify_url_type(url)
    is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
        pdf_bytes, expected_title, expected_type, url_type
    )
    
    return (is_valid, confidence, detected_type)


def search_ultra_flexible(title: str, doc_type: str, provider: SearchProvider, 
                          validator: SemanticValidator) -> Optional[str]:
    """
    Búsqueda ULTRA FLEXIBLE para casos difíciles.
    
    Estrategias adicionales:
    - Búsqueda sin filetype:pdf (algunos PDFs no indexados correctamente)
    - Búsqueda solo con enfermedad (sin "diagnóstico", "tratamiento")
    - Búsqueda en Google académico
    """
    doc_keywords = {
        "GER": '"Guía de Evidencias" OR GER OR ER',
        "GRR": '"Guía de Referencia" OR GRR OR RR'
    }
    
    # Extraer solo el nombre de la enfermedad
    # Ej: "Diagnóstico de neumonía" → "neumonía"
    disease_only = title.lower()
    for prefix in ['diagnóstico', 'tratamiento', 'manejo', 'prevención', 'de la', 'de', 'del']:
        disease_only = disease_only.replace(prefix, '')
    disease_only = ' '.join(disease_only.split())  # Limpiar espacios
    
    ultra_strategies = [
        # Sin filetype (algunos PDFs mal indexados)
        f'{title} {doc_keywords[doc_type]} site:cenetec-difusion.com',
        f'{title} {doc_keywords[doc_type]} site:cenetec.salud.gob.mx',
        
        # Solo enfermedad
        f'{disease_only} {doc_keywords[doc_type]} filetype:pdf site:cenetec-difusion.com',
        f'{disease_only} {doc_keywords[doc_type]} filetype:pdf site:imss.gob.mx',
        
        # Búsqueda muy amplia
        f'GPC {disease_only} {doc_type} filetype:pdf site:.mx',
        f'guía práctica clínica {disease_only} {doc_type} site:.mx',
    ]
    
    print(f"  🔍 Búsqueda ULTRA-FLEXIBLE: {len(ultra_strategies)} estrategias")
    
    for i, query in enumerate(ultra_strategies, 1):
        try:
            results = provider.search(query, num=15)  # Más resultados
            
            if not results:
                continue
            
            print(f"    [{i}] {len(results)} resultados")
            
            # Validar candidatos con threshold MUY bajo (25%)
            candidates = []
            
            for result in results:
                url = result.get("link", "")
                
                if not url:
                    continue
                
                # Permitir URLs que no terminen en .pdf pero contengan .pdf
                if ".pdf" not in url.lower():
                    continue
                
                if ".mx" not in url.lower() and "cenetec" not in url.lower():
                    continue
                
                url_type = classify_url_type(url)
                if url_type and url_type != doc_type:
                    continue
                
                # Descargar
                pdf_bytes = download_pdf(url)
                if not pdf_bytes or len(pdf_bytes) < 1000:
                    continue
                
                # Validación MUY permisiva (25% threshold)
                is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
                    pdf_bytes, title, doc_type, url_type
                )
                
                if title_sim >= 0.25 and detected_type == doc_type:
                    domain_priority = get_domain_priority(url)
                    candidates.append((domain_priority, confidence, url))
            
            if candidates:
                candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
                best_priority, best_conf, best_url = candidates[0]
                print(f"    ✅ ENCONTRADO: {best_url[-60:]} (domain={best_priority}, conf={best_conf:.1%})")
                return best_url
        
        except Exception as e:
            print(f"    ❌ Error: {e}")
            continue
    
    return None


def process_validation(args) -> None:
    """
    Procesa validación y búsqueda de GPCs con baja confianza y faltantes.
    """
    # Cargar resultados
    if not OUT_JSON.exists():
        print(f"❌ No se encontró {OUT_JSON}")
        return
    
    rows = []
    try:
        existing_data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        for item in existing_data:
            result = GPCLinkResult(
                title=item.get('title', ''),
                query_ger=item.get('query_ger', ''),
                query_grr=item.get('query_grr', ''),
                ger_url=item.get('ger_url'),
                grr_url=item.get('grr_url'),
                ger_source=item.get('ger_source'),
                grr_source=item.get('grr_source'),
                ger_status=item.get('ger_status'),
                grr_status=item.get('grr_status'),
                ger_confidence=float(item.get('ger_confidence', 0.0) or 0.0),
                grr_confidence=float(item.get('grr_confidence', 0.0) or 0.0),
            )
            rows.append(result)
    except Exception as e:
        print(f"❌ Error cargando {OUT_JSON}: {e}")
        return
    
    # Filtrar casos problemáticos
    low_confidence = []
    missing = []
    
    for row in rows:
        # Faltantes
        if not row.ger_url or not row.grr_url:
            missing.append(row)
            continue
        
        # Baja confianza
        if row.ger_confidence < args.min_confidence or row.grr_confidence < args.min_confidence:
            low_confidence.append(row)
    
    print(f"\n📊 ANÁLISIS INICIAL:")
    print(f"  - Total GPCs: {len(rows)}")
    print(f"  - Confianza baja (<{args.min_confidence}%): {len(low_confidence)}")
    print(f"  - Faltantes: {len(missing)}")
    print(f"  - Total a procesar: {len(low_confidence) + len(missing)}")
    
    if not low_confidence and not missing:
        print("✅ No hay GPCs para validar/buscar. Todo perfecto!")
        return
    
    # Inicializar
    provider = choose_provider()
    validator = SemanticValidator(
        args.embedding_model,
        args.embedding_device,
        args.embedding_batch_size,
        enable_classification=True
    )
    
    if not validator.ensure_loaded():
        print("❌ No se pudo cargar modelo AI")
        return
    
    print(f"✅ Modelo cargado en {validator._actual_device}\n")
    
    imss_catalog = load_imss_catalog()
    
    updated_count = 0
    
    # PARTE 1: Re-validar baja confianza
    if low_confidence:
        print(f"\n{'='*80}")
        print(f"PARTE 1: RE-VALIDAR {len(low_confidence)} GPCs CON BAJA CONFIANZA")
        print(f"{'='*80}\n")
        
        for idx, row in enumerate(low_confidence, 1):
            print(f"\n[{idx}/{len(low_confidence)}] {row.title}")
            print(f"  Confianza actual: GER={row.ger_confidence:.1f}%, GRR={row.grr_confidence:.1f}%")
            
            # Re-validar GER
            if row.ger_url and row.ger_confidence < args.min_confidence:
                print(f"  🔍 Re-validando GER...")
                is_valid, new_conf, detected_type = validate_existing_url(
                    row.ger_url, row.title, "GER", validator
                )
                
                if is_valid and new_conf >= args.min_confidence / 100:
                    row.ger_confidence = new_conf * 100
                    print(f"    ✅ Confianza mejorada: {new_conf*100:.1f}%")
                    updated_count += 1
                else:
                    print(f"    ⚠️  Validación falla, buscando alternativa...")
                    new_url = search_ultra_flexible(row.title, "GER", provider, validator)
                    if new_url:
                        row.ger_url = new_url
                        row.ger_source = "validation_replacement"
                        row.ger_confidence = 70.0
                        print(f"    ✅ Reemplazado: {new_url[-50:]}")
                        updated_count += 1
            
            # Re-validar GRR
            if row.grr_url and row.grr_confidence < args.min_confidence:
                print(f"  🔍 Re-validando GRR...")
                is_valid, new_conf, detected_type = validate_existing_url(
                    row.grr_url, row.title, "GRR", validator
                )
                
                if is_valid and new_conf >= args.min_confidence / 100:
                    row.grr_confidence = new_conf * 100
                    print(f"    ✅ Confianza mejorada: {new_conf*100:.1f}%")
                    updated_count += 1
                else:
                    print(f"    ⚠️  Validación falla, buscando alternativa...")
                    new_url = search_ultra_flexible(row.title, "GRR", provider, validator)
                    if new_url:
                        row.grr_url = new_url
                        row.grr_source = "validation_replacement"
                        row.grr_confidence = 70.0
                        print(f"    ✅ Reemplazado: {new_url[-50:]}")
                        updated_count += 1
            
            # Guardar progreso
            write_outputs(rows, incremental=True)
            time.sleep(args.sleep)
    
    # PARTE 2: Buscar faltantes
    if missing:
        print(f"\n{'='*80}")
        print(f"PARTE 2: BUSCAR {len(missing)} GPCs FALTANTES")
        print(f"{'='*80}\n")
        
        for idx, row in enumerate(missing, 1):
            print(f"\n[{idx}/{len(missing)}] {row.title}")
            
            needs_ger = not row.ger_url
            needs_grr = not row.grr_url
            
            if needs_ger:
                print(f"  🔍 Búsqueda ULTRA-FLEXIBLE: GER")
                url = search_ultra_flexible(row.title, "GER", provider, validator)
                if url:
                    row.ger_url = url
                    row.ger_source = "ultra_flexible_search"
                    row.ger_confidence = 60.0
                    updated_count += 1
                    needs_ger = False
                else:
                    # Fallback: IMSS catalog
                    if imss_catalog:
                        imss_match = find_in_imss_catalog_by_year(row.title, imss_catalog, max_age_years=args.max_age)
                        if imss_match and imss_match.get('ger_url'):
                            row.ger_url = imss_match['ger_url']
                            row.ger_source = "IMSS_catalog_last_resort"
                            row.ger_confidence = 65.0
                            print(f"    💾 IMSS catalog: {row.ger_url[-50:]}")
                            updated_count += 1
                            needs_ger = False
            
            if needs_grr:
                print(f"  🔍 Búsqueda ULTRA-FLEXIBLE: GRR")
                url = search_ultra_flexible(row.title, "GRR", provider, validator)
                if url:
                    row.grr_url = url
                    row.grr_source = "ultra_flexible_search"
                    row.grr_confidence = 60.0
                    updated_count += 1
                    needs_grr = False
                else:
                    # Fallback: IMSS catalog
                    if imss_catalog:
                        imss_match = find_in_imss_catalog_by_year(row.title, imss_catalog, max_age_years=args.max_age)
                        if imss_match and imss_match.get('grr_url'):
                            row.grr_url = imss_match['grr_url']
                            row.grr_source = "IMSS_catalog_last_resort"
                            row.grr_confidence = 65.0
                            print(f"    💾 IMSS catalog: {row.grr_url[-50:]}")
                            updated_count += 1
                            needs_grr = False
            
            if needs_ger or needs_grr:
                print(f"    ❌ No encontrado (búsqueda exhaustiva completada)")
            
            # Guardar progreso
            write_outputs(rows, incremental=True)
            time.sleep(args.sleep)
    
    print(f"\n{'='*80}")
    print(f"✅ VALIDACIÓN COMPLETADA")
    print(f"📊 {updated_count} GPCs actualizados/mejorados")
    print(f"💾 Resultados guardados en: {OUT_JSON}")
    
    # Estadísticas finales
    complete = sum(1 for r in rows if r.ger_url and r.grr_url)
    high_conf = sum(1 for r in rows if r.ger_confidence >= args.min_confidence and r.grr_confidence >= args.min_confidence)
    
    print(f"\n📈 ESTADÍSTICAS FINALES:")
    print(f"  - GPCs completos (GER+GRR): {complete}/{len(rows)} ({complete/len(rows)*100:.1f}%)")
    print(f"  - Confianza alta (≥{args.min_confidence}%): {high_conf}/{len(rows)} ({high_conf/len(rows)*100:.1f}%)")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="🔍 Validación AI para GPCs con baja confianza y faltantes"
    )
    parser.add_argument("--min-confidence", type=float, default=85.0, 
                        help="Umbral mínimo de confianza (default: 85%%)")
    parser.add_argument("--sleep", type=float, default=1.0, 
                        help="Segundos entre búsquedas")
    parser.add_argument("--max-age", type=int, default=10, 
                        help="Máxima antigüedad IMSS (años) para último recurso")
    parser.add_argument("--embedding-model", default="paraphrase-multilingual-mpnet-base-v2")
    parser.add_argument("--embedding-device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--embedding-batch-size", type=int, default=32)
    
    args = parser.parse_args(argv)
    
    process_validation(args)
    
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
