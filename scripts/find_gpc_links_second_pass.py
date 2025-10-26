#!/usr/bin/env python3
"""
🔄 SEGUNDO PASE: Buscar GPCs faltantes con estrategias alternativas.

Estrategias:
1. Búsqueda más flexible (sin site: restriction tan estricta)
2. Validar año en catálogo IMSS (solo usar si es del año actual/anterior)
3. Búsqueda con título simplificado (quitar palabras complejas)
4. Búsqueda con términos médicos clave (extraer diagnóstico principal)
5. Si NADA funciona, marcar como "no encontrado" definitivo

Requisitos:
- Ejecutar DESPUÉS de find_gpc_links.py (primer pase)
- Lee gpc_links.json y busca solo las faltantes (None en ger_url o grr_url)
- Guarda resultados en el mismo archivo (actualiza)
"""

from __future__ import annotations
import argparse
import csv
import datetime
import difflib
import hashlib
import io
import json
import os
import re
import sys
import time
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import requests

# Add parent directory to path to import from main script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import pytesseract
    from PIL import Image
    import fitz  # PyMuPDF
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data"
OUT_JSON = OUT_DIR / "gpc_links.json"
OUT_CSV = OUT_DIR / "gpc_links.csv"
OUT_MD = REPO_ROOT / "docs" / "gpc_links_summary.md"
PDF_CACHE_DIR = OUT_DIR / ".pdf_cache"

# Import from main script
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
    normalize_text,
    load_imss_catalog,
    write_outputs,
)


def choose_provider() -> SearchProvider:
    """Same as main script but prioritize Google CSE."""
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


def simplify_title(title: str) -> str:
    """
    Simplifica título para búsqueda más flexible.
    
    Ejemplo:
    - "Diagnóstico y tratamiento de la neumonía adquirida en la comunidad" 
      → "neumonía adquirida comunidad"
    """
    # Quitar palabras comunes
    stop_words = [
        'diagnóstico', 'tratamiento', 'manejo', 'prevención', 'detección',
        'de', 'del', 'la', 'el', 'en', 'por', 'para', 'con', 'y', 'o',
        'a', 'ante', 'bajo', 'cabe', 'desde', 'entre', 'hacia', 'hasta',
        'mediante', 'según', 'sin', 'sobre', 'tras'
    ]
    
    words = title.lower().split()
    filtered = [w for w in words if w not in stop_words and len(w) > 3]
    
    return ' '.join(filtered[:5])  # Max 5 palabras clave


def extract_key_medical_terms(title: str) -> List[str]:
    """
    Extrae términos médicos clave del título.
    
    Ejemplo:
    - "Tratamiento de diabetes mellitus tipo 2" → ["diabetes", "mellitus"]
    """
    # Palabras médicas importantes (no stop words)
    medical_pattern = r'\b([a-záéíóúñ]{5,})\b'
    matches = re.findall(medical_pattern, title.lower())
    
    # Filtrar stop words médicas
    stop_medical = ['tratamiento', 'diagnóstico', 'manejo', 'prevención']
    
    return [m for m in matches if m not in stop_medical][:3]


def get_gpc_year_from_catalog(entry: Dict[str, Any]) -> Optional[int]:
    """
    Extrae año de publicación de una entrada del catálogo IMSS.
    
    Busca en:
    1. Campo 'year' (si existe)
    2. Número de GPC (formato: XXX-YY donde YY es año)
    3. URL (buscar /20XX/ o _20XX_)
    """
    # Campo directo
    if 'year' in entry:
        try:
            return int(entry['year'])
        except (ValueError, TypeError):
            pass
    
    # Extraer de número GPC (ej: IMSS-031-08 → 2008)
    if 'gpc_number' in entry:
        match = re.search(r'-(\d{2})$', entry['gpc_number'])
        if match:
            year_suffix = int(match.group(1))
            # Asumir 20XX si YY > 90, sino 19XX
            return 2000 + year_suffix if year_suffix <= 25 else 1900 + year_suffix
    
    # Extraer de URL
    for url_key in ['ger_url', 'grr_url']:
        url = entry.get(url_key, '')
        if url:
            # Buscar /20XX/ o _20XX_
            match = re.search(r'[/_](20\d{2})[/_]', url)
            if match:
                return int(match.group(1))
    
    return None


def is_recent_gpc(entry: Dict[str, Any], max_age_years: int = 5) -> bool:
    """
    Verifica si un GPC del catálogo IMSS es suficientemente reciente.
    
    Args:
        entry: Entrada del catálogo IMSS
        max_age_years: Máxima antigüedad permitida (default: 5 años)
    
    Returns: True si es reciente o no se puede determinar año
    """
    year = get_gpc_year_from_catalog(entry)
    
    if year is None:
        # Si no podemos determinar el año, aceptar (beneficio de la duda)
        return True
    
    current_year = datetime.datetime.now().year
    age = current_year - year
    
    return age <= max_age_years


def find_in_imss_catalog_by_year(title: str, imss_catalog: List[Dict[str, Any]], max_age_years: int = 5) -> Optional[Dict[str, Any]]:
    """
    Busca en catálogo IMSS filtrando por año.
    
    Args:
        title: Título del GPC
        imss_catalog: Catálogo IMSS
        max_age_years: Máxima antigüedad (años)
    
    Returns: Mejor match reciente o None
    """
    title_norm = normalize_text(title)
    
    candidates = []
    
    for entry in imss_catalog:
        # Filtrar por año primero
        if not is_recent_gpc(entry, max_age_years):
            continue
        
        entry_title = entry.get('title', '')
        if not entry_title:
            continue
        
        entry_norm = normalize_text(entry_title)
        
        # Similitud
        score = difflib.SequenceMatcher(None, title_norm, entry_norm).ratio()
        
        if score >= 0.65:  # Threshold más bajo para segundo pase
            year = get_gpc_year_from_catalog(entry) or 9999
            candidates.append((score, year, entry))
    
    if not candidates:
        return None
    
    # Ordenar por similitud primero, luego por año (más reciente)
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    
    return candidates[0][2]


def search_flexible(title: str, doc_type: str, provider: SearchProvider, validator: SemanticValidator) -> Optional[str]:
    """
    🔍 Búsqueda MÁS FLEXIBLE para segundo pase.
    
    ⚠️ PRIORIDAD CENETEC SIEMPRE (incluso en segundo pase):
    1. Buscar en CENETEC con estrategias alternativas
    2. Si no hay en CENETEC, buscar en IMSS
    3. Si no hay en IMSS, buscar en cualquier .mx
    4. Validación más permisiva (30% threshold)
    """
    doc_keywords = {
        "GER": '"Guía de Evidencias" OR GER OR ER',
        "GRR": '"Guía de Referencia" OR GRR OR RR'
    }
    
    # 🔥 ESTRATEGIA: Buscar en cada dominio por prioridad
    domain_strategies = [
        # PRIORIDAD 1: CENETEC (siempre primero)
        [
            f'{title} {doc_keywords[doc_type]} filetype:pdf site:cenetec-difusion.com',
            f'{simplify_title(title)} {doc_keywords[doc_type]} filetype:pdf site:cenetec-difusion.com',
            f'{" ".join(extract_key_medical_terms(title))} {doc_keywords[doc_type]} filetype:pdf site:cenetec-difusion.com',
            f'{title} {doc_keywords[doc_type]} filetype:pdf site:cenetec.salud.gob.mx',
            f'{simplify_title(title)} {doc_keywords[doc_type]} filetype:pdf site:cenetec.salud.gob.mx',
        ],
        
        # PRIORIDAD 2: IMSS (solo si CENETEC no tiene)
        [
            f'{title} {doc_keywords[doc_type]} filetype:pdf site:imss.gob.mx',
            f'{simplify_title(title)} {doc_keywords[doc_type]} filetype:pdf site:imss.gob.mx',
            f'{" ".join(extract_key_medical_terms(title))} {doc_keywords[doc_type]} filetype:pdf site:imss.gob.mx',
        ],
        
        # PRIORIDAD 3: Cualquier .mx (último recurso)
        [
            f'{title} {doc_keywords[doc_type]} filetype:pdf site:.mx',
            f'{simplify_title(title)} {doc_keywords[doc_type]} filetype:pdf site:.mx',
        ],
    ]
    
    domain_names = ["CENETEC", "IMSS", ".mx"]
    
    # Buscar por prioridad de dominio
    for domain_idx, strategies in enumerate(domain_strategies):
        print(f"  � [{domain_names[domain_idx]}] Probando {len(strategies)} estrategias...")
        
        for i, query in enumerate(strategies, 1):
            try:
                results = provider.search(query, num=10)
                
                if not results:
                    continue
                
                print(f"    [{i}] {len(results)} resultados")
                
                # Validar candidatos (ordenar por prioridad de dominio)
                candidates = []
                
                for result in results:
                    url = result.get("link", "")
                    
                    if not url or not url.lower().endswith(".pdf"):
                        continue
                    
                    # Filtro de dominio permitido
                    if ".mx" not in url.lower() and "cenetec" not in url.lower():
                        continue
                    
                    url_type = classify_url_type(url)
                    if url_type and url_type != doc_type:
                        continue
                    
                    # Descargar y validar
                    pdf_bytes = download_pdf(url)
                    if not pdf_bytes or len(pdf_bytes) < 1000:
                        continue
                    
                    # Validación más permisiva (30% threshold)
                    is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
                        pdf_bytes, title, doc_type, url_type
                    )
                    
                    # Umbral más bajo para segundo pase
                    if title_sim >= 0.30 and detected_type == doc_type:
                        domain_priority = get_domain_priority(url)
                        candidates.append((domain_priority, confidence, url))
                
                # Si hay candidatos, retornar el mejor (por dominio primero)
                if candidates:
                    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
                    best_priority, best_conf, best_url = candidates[0]
                    print(f"    ✅ ENCONTRADO: {best_url[-60:]} (domain={best_priority}, conf={best_conf:.1%})")
                    return best_url
            
            except Exception as e:
                print(f"    ❌ Error estrategia {i}: {e}")
                continue
        
        # Si encontramos algo en este dominio, no buscar en dominios de menor prioridad
        # (pero si no encontramos nada, continuar al siguiente dominio)
    
    return None


def process_missing_gpcs(args) -> None:
    """
    Procesa GPCs faltantes del primer pase.
    """
    # Cargar resultados del primer pase
    if not OUT_JSON.exists():
        print(f"❌ No se encontró {OUT_JSON}")
        print("Ejecuta primero: python scripts/find_gpc_links.py --use-smart-validation")
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
    
    # Filtrar faltantes
    missing = []
    for row in rows:
        needs_ger = not row.ger_url
        needs_grr = not row.grr_url
        
        if needs_ger or needs_grr:
            missing.append((row, needs_ger, needs_grr))
    
    if not missing:
        print("✅ No hay GPCs faltantes. Todo completo!")
        return
    
    print(f"\n🔍 SEGUNDO PASE: {len(missing)} GPCs con documentos faltantes")
    print("=" * 80)
    
    # Inicializar provider y validator
    provider = choose_provider()
    
    validator = SemanticValidator(
        args.embedding_model,
        args.embedding_device,
        args.embedding_batch_size,
        enable_classification=True
    )
    
    if not validator.ensure_loaded():
        print("❌ No se pudo cargar el modelo de validación")
        return
    
    print(f"✅ Modelo cargado en {validator._actual_device}\n")
    
    # Cargar catálogo IMSS
    imss_catalog = load_imss_catalog()
    if imss_catalog:
        print(f"📦 Catálogo IMSS: {len(imss_catalog)} GPCs disponibles\n")
    
    # Procesar faltantes
    updated_count = 0
    
    for idx, (row, needs_ger, needs_grr) in enumerate(missing, 1):
        print(f"\n[{idx}/{len(missing)}] {row.title}")
        
        # 🔥 PRIORIDAD CENETEC SIEMPRE: Buscar en web primero
        # Si encontramos en CENETEC, nunca usar IMSS catalog
        
        if needs_ger:
            print(f"  🔍 Búsqueda flexible: GER")
            url = search_flexible(row.title, "GER", provider, validator)
            if url:
                row.ger_url = url
                row.ger_source = "flexible_search"
                row.ger_confidence = 65.0
                updated_count += 1
                needs_ger = False
            else:
                print(f"    ❌ GER no encontrado en web")
        
        if needs_grr:
            print(f"  🔍 Búsqueda flexible: GRR")
            url = search_flexible(row.title, "GRR", provider, validator)
            if url:
                row.grr_url = url
                row.grr_source = "flexible_search"
                row.grr_confidence = 65.0
                updated_count += 1
                needs_grr = False
            else:
                print(f"    ❌ GRR no encontrado en web")
        
        # FALLBACK: IMSS catalog SOLO si no encontramos en web (solo si es reciente)
        if (needs_ger or needs_grr) and imss_catalog:
            imss_match = find_in_imss_catalog_by_year(row.title, imss_catalog, max_age_years=args.max_age)
            
            if imss_match:
                year = get_gpc_year_from_catalog(imss_match)
                year_str = f"año {year}" if year else "año desconocido"
                print(f"  📚 IMSS catalog fallback ({year_str})")
                
                if needs_ger and imss_match.get('ger_url'):
                    row.ger_url = imss_match['ger_url']
                    row.ger_source = "IMSS_catalog_fallback"
                    row.ger_confidence = 70.0
                    print(f"    ✅ GER: {row.ger_url[-50:]}")
                    updated_count += 1
                    needs_ger = False
                
                if needs_grr and imss_match.get('grr_url'):
                    row.grr_url = imss_match['grr_url']
                    row.grr_source = "IMSS_catalog_fallback"
                    row.grr_confidence = 70.0
                    print(f"    ✅ GRR: {row.grr_url[-50:]}")
                    updated_count += 1
                    needs_grr = False
        
        # Resultado final
        if needs_ger and needs_grr:
            print(f"    ❌ Ambos faltantes (búsqueda exhaustiva completada)")
        elif needs_ger:
            print(f"    ⚠️  Solo GER faltante")
        elif needs_grr:
            print(f"    ⚠️  Solo GRR faltante")
        
        # Guardar progreso incremental
        write_outputs(rows, incremental=True)
        
        # Sleep para no saturar API
        time.sleep(args.sleep)
    
    print(f"\n{'=' * 80}")
    print(f"✅ SEGUNDO PASE COMPLETADO")
    print(f"📊 {updated_count} documentos adicionales encontrados")
    print(f"💾 Resultados guardados en: {OUT_JSON}")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="🔄 Segundo pase: buscar GPCs faltantes con estrategias alternativas"
    )
    parser.add_argument("--sleep", type=float, default=1.0, help="Segundos entre búsquedas")
    parser.add_argument("--max-age", type=int, default=5, help="Máxima antigüedad de GPCs IMSS (años)")
    parser.add_argument("--embedding-model", default="paraphrase-multilingual-mpnet-base-v2")
    parser.add_argument("--embedding-device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--embedding-batch-size", type=int, default=32)
    
    args = parser.parse_args(argv)
    
    process_missing_gpcs(args)
    
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
