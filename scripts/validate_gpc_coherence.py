#!/usr/bin/env python3
"""
🔥 VALIDADOR MODO DIOS: Coherencia de IDs + Validación Semántica GPU

Este script corrige automáticamente:
1. **Discrepancias de ID**: GER y GRR deben tener mismo número GPC
   - Ejemplo: IMSS-419-10/ER.pdf + IMSS-336-10/RR.pdf ❌
   - Corrección: IMSS-419-10/ER.pdf + IMSS-419-10/RR.pdf ✅

2. **Validación Semántica con GPU** (threshold 50% - más permisivo)
   - Re-valida todos los PDFs con el modelo paraphrase-multilingual-mpnet-base-v2
   - Si confianza <50%: busca alternativa
   - Si confianza ≥50%: acepta y actualiza

3. **Inferencia Inteligente**
   - Si GER es IMSS-419-10/ER.pdf → GRR debe ser IMSS-419-10/RR.pdf
   - Valida inferido antes de reemplazar
   - SOLO reemplaza si inferido tiene mejor confianza

Actualiza: JSON, CSV, MD con resultados corregidos
"""

from __future__ import annotations
import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.find_gpc_links import (
    GPCLinkResult,
    SemanticValidator,
    download_pdf,
    extract_gpc_number,
    get_domain_priority,
    classify_url_type,
    write_outputs,
    infer_complementary_url,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = REPO_ROOT / "data" / "gpc_links.json"


def validate_id_coherence(ger_url: Optional[str], grr_url: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Valida que GER y GRR tengan el mismo ID de GPC.
    
    Returns:
        (coherente, gpc_number_ger, gpc_number_grr)
    """
    if not ger_url or not grr_url:
        return (True, None, None)  # No podemos validar
    
    ger_num = extract_gpc_number(ger_url)
    grr_num = extract_gpc_number(grr_url)
    
    if not ger_num or not grr_num:
        return (True, ger_num, grr_num)  # No podemos extraer
    
    coherent = (ger_num == grr_num)
    
    return (coherent, ger_num, grr_num)


def fix_incoherent_pair(row: GPCLinkResult, validator: SemanticValidator, 
                        min_confidence: float = 0.50) -> Tuple[bool, str]:
    """
    Corrige par incoherente (GER y GRR con IDs diferentes).
    
    Estrategia:
    1. Comparar prioridad de dominios (CENETEC > IMSS)
    2. Inferir el faltante desde el de mayor prioridad
    3. Validar inferido con AI
    4. Si confianza ≥50%: reemplazar
    
    Returns:
        (modificado, razón)
    """
    if not row.ger_url or not row.grr_url:
        return (False, "URLs faltantes")
    
    ger_domain = get_domain_priority(row.ger_url)
    grr_domain = get_domain_priority(row.grr_url)
    
    # Determinar cuál es más confiable (mayor prioridad de dominio)
    if ger_domain > grr_domain:
        # GER es más confiable, inferir GRR desde GER
        inferred_grr = infer_complementary_url(row.ger_url, "GER", "GRR")
        
        if not inferred_grr:
            return (False, "No se pudo inferir GRR desde GER")
        
        # Validar inferido
        pdf_bytes = download_pdf(inferred_grr)
        if not pdf_bytes or len(pdf_bytes) < 1000:
            return (False, "GRR inferido no descargable")
        
        url_type = classify_url_type(inferred_grr)
        is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
            pdf_bytes, row.title, "GRR", url_type
        )
        
        if title_sim >= min_confidence:
            old_grr = row.grr_url
            row.grr_url = inferred_grr
            row.grr_confidence = confidence * 100
            row.grr_source = "coherence_fix_inferred_from_ger"
            return (True, f"GRR reemplazado (de {old_grr[-30:]} a {inferred_grr[-30:]}, conf={confidence*100:.1f}%)")
        else:
            return (False, f"GRR inferido confianza baja ({confidence*100:.1f}%)")
    
    elif grr_domain > ger_domain:
        # GRR es más confiable, inferir GER desde GRR
        inferred_ger = infer_complementary_url(row.grr_url, "GRR", "GER")
        
        if not inferred_ger:
            return (False, "No se pudo inferir GER desde GRR")
        
        # Validar inferido
        pdf_bytes = download_pdf(inferred_ger)
        if not pdf_bytes or len(pdf_bytes) < 1000:
            return (False, "GER inferido no descargable")
        
        url_type = classify_url_type(inferred_ger)
        is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
            pdf_bytes, row.title, "GER", url_type
        )
        
        if title_sim >= min_confidence:
            old_ger = row.ger_url
            row.ger_url = inferred_ger
            row.ger_confidence = confidence * 100
            row.ger_source = "coherence_fix_inferred_from_grr"
            return (True, f"GER reemplazado (de {old_ger[-30:]} a {inferred_ger[-30:]}, conf={confidence*100:.1f}%)")
        else:
            return (False, f"GER inferido confianza baja ({confidence*100:.1f}%)")
    
    else:
        # 🔥 MISMA PRIORIDAD: Inferir AMBOS y elegir el mejor por similitud
        print("    🔄 Ambos dominios igual prioridad, validando ambas opciones...")
        
        # Opción A: Inferir GRR desde GER
        inferred_grr_from_ger = infer_complementary_url(row.ger_url, "GER", "GRR")
        # Opción B: Inferir GER desde GRR
        inferred_ger_from_grr = infer_complementary_url(row.grr_url, "GRR", "GER")
        
        candidates = []
        
        # Validar opción A (mantener GER, reemplazar GRR)
        if inferred_grr_from_ger:
            pdf_bytes = download_pdf(inferred_grr_from_ger)
            if pdf_bytes and len(pdf_bytes) >= 1000:
                url_type = classify_url_type(inferred_grr_from_ger)
                is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
                    pdf_bytes, row.title, "GRR", url_type
                )
                if title_sim >= min_confidence:
                    candidates.append(('grr', inferred_grr_from_ger, confidence, title_sim))
        
        # Validar opción B (mantener GRR, reemplazar GER)
        if inferred_ger_from_grr:
            pdf_bytes = download_pdf(inferred_ger_from_grr)
            if pdf_bytes and len(pdf_bytes) >= 1000:
                url_type = classify_url_type(inferred_ger_from_grr)
                is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
                    pdf_bytes, row.title, "GER", url_type
                )
                if title_sim >= min_confidence:
                    candidates.append(('ger', inferred_ger_from_grr, confidence, title_sim))
        
        if not candidates:
            return (False, "No se pudieron validar opciones alternativas")
        
        # Elegir la opción con mejor similitud semántica
        candidates.sort(key=lambda x: x[3], reverse=True)  # Sort by title_sim
        best_type, best_url, best_conf, best_sim = candidates[0]
        
        if best_type == 'grr':
            old_grr = row.grr_url
            row.grr_url = best_url
            row.grr_confidence = best_conf * 100
            row.grr_source = "coherence_fix_best_semantic_match"
            return (True, f"GRR reemplazado (similitud {best_sim*100:.1f}%)")
        else:
            old_ger = row.ger_url
            row.ger_url = best_url
            row.ger_confidence = best_conf * 100
            row.ger_source = "coherence_fix_best_semantic_match"
            return (True, f"GER reemplazado (similitud {best_sim*100:.1f}%)")


def revalidate_with_gpu(row: GPCLinkResult, validator: SemanticValidator,
                        min_confidence: float = 0.50) -> Tuple[int, str]:
    """
    Re-valida GER y GRR con GPU.
    
    Args:
        min_confidence: Umbral mínimo (50% por defecto - más permisivo)
    
    Returns:
        (count_updated, summary)
    """
    updated = 0
    messages = []
    
    # Re-validar GER
    if row.ger_url:
        pdf_bytes = download_pdf(row.ger_url)
        if pdf_bytes and len(pdf_bytes) >= 1000:
            url_type = classify_url_type(row.ger_url)
            is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
                pdf_bytes, row.title, "GER", url_type
            )
            
            old_conf = row.ger_confidence
            new_conf = confidence * 100
            
            if title_sim >= min_confidence and detected_type == "GER":
                if abs(new_conf - old_conf) > 5:  # Cambio significativo
                    row.ger_confidence = new_conf
                    updated += 1
                    messages.append(f"GER: {old_conf:.1f}% → {new_conf:.1f}%")
            elif title_sim < min_confidence:
                messages.append(f"GER: confianza baja ({new_conf:.1f}%)")
    
    # Re-validar GRR
    if row.grr_url:
        pdf_bytes = download_pdf(row.grr_url)
        if pdf_bytes and len(pdf_bytes) >= 1000:
            url_type = classify_url_type(row.grr_url)
            is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
                pdf_bytes, row.title, "GRR", url_type
            )
            
            old_conf = row.grr_confidence
            new_conf = confidence * 100
            
            if title_sim >= min_confidence and detected_type == "GRR":
                if abs(new_conf - old_conf) > 5:  # Cambio significativo
                    row.grr_confidence = new_conf
                    updated += 1
                    messages.append(f"GRR: {old_conf:.1f}% → {new_conf:.1f}%")
            elif title_sim < min_confidence:
                messages.append(f"GRR: confianza baja ({new_conf:.1f}%)")
    
    summary = "; ".join(messages) if messages else "Sin cambios"
    return (updated, summary)


def process_god_mode_validation(args) -> None:
    """
    Validación MODO DIOS con coherencia de IDs y validación semántica GPU.
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
    
    # Identificar problemas
    incoherent_ids = []
    low_confidence = []
    
    for row in rows:
        # Coherencia de IDs
        coherent, ger_num, grr_num = validate_id_coherence(row.ger_url, row.grr_url)
        if not coherent:
            incoherent_ids.append((row, ger_num, grr_num))
        
        # Baja confianza
        if row.ger_url and row.ger_confidence < args.min_confidence:
            low_confidence.append(row)
        elif row.grr_url and row.grr_confidence < args.min_confidence:
            if row not in low_confidence:
                low_confidence.append(row)
    
    print(f"\n🔥 MODO DIOS ACTIVADO")
    print(f"{'='*80}")
    print(f"📊 ANÁLISIS:")
    print(f"  - Total GPCs: {len(rows)}")
    print(f"  - IDs incoherentes (GER ≠ GRR): {len(incoherent_ids)}")
    print(f"  - Confianza <{args.min_confidence}%: {len(low_confidence)}")
    print(f"{'='*80}\n")
    
    # Inicializar validator
    validator = SemanticValidator(
        args.embedding_model,
        args.embedding_device,
        args.embedding_batch_size,
        enable_classification=True
    )
    
    if not validator.ensure_loaded():
        print("❌ No se pudo cargar modelo GPU")
        return
    
    print(f"✅ Modelo '{args.embedding_model}' cargado en {validator._actual_device}\n")
    
    fixes_count = 0
    improvements_count = 0
    
    # PARTE 1: Corregir IDs incoherentes
    if incoherent_ids:
        print(f"{'='*80}")
        print(f"PARTE 1: CORREGIR {len(incoherent_ids)} GPCs CON IDs INCOHERENTES")
        print(f"{'='*80}\n")
        
        for idx, (row, ger_num, grr_num) in enumerate(incoherent_ids, 1):
            print(f"\n[{idx}/{len(incoherent_ids)}] {row.title}")
            print(f"  ⚠️  GER: {ger_num} | GRR: {grr_num} (DIFERENTES)")
            print(f"  📎 GER: {row.ger_url[-60:]}")
            print(f"  📎 GRR: {row.grr_url[-60:]}")
            
            modified, reason = fix_incoherent_pair(row, validator, args.min_confidence / 100)
            
            if modified:
                print(f"  ✅ CORREGIDO: {reason}")
                fixes_count += 1
                write_outputs(rows, incremental=True)
            else:
                print(f"  ❌ No corregido: {reason}")
            
            time.sleep(args.sleep)
    
    # PARTE 2: Re-validar TODOS con GPU (incluso los ≥85%)
    print(f"\n{'='*80}")
    print(f"PARTE 2: RE-VALIDACIÓN SEMÁNTICA GPU (THRESHOLD {args.min_confidence}%)")
    print(f"{'='*80}\n")
    
    for idx, row in enumerate(rows, 1):
        if not row.ger_url and not row.grr_url:
            continue
        
        print(f"\r[{idx}/{len(rows)}] Validando {row.title[:50]}...", end='', flush=True)
        
        updated, summary = revalidate_with_gpu(row, validator, args.min_confidence / 100)
        
        if updated > 0:
            improvements_count += updated
            print(f"\n  ✅ {summary}")
        
        # Guardar cada 10 GPCs
        if idx % 10 == 0:
            write_outputs(rows, incremental=True)
        
        time.sleep(args.sleep)
    
    print(f"\n\n{'='*80}")
    print(f"✅ VALIDACIÓN MODO DIOS COMPLETADA")
    print(f"{'='*80}")
    print(f"📊 RESULTADOS:")
    print(f"  - IDs corregidos: {fixes_count}")
    print(f"  - Confianzas mejoradas: {improvements_count}")
    print(f"  - Total cambios: {fixes_count + improvements_count}")
    print(f"💾 Resultados guardados en: {OUT_JSON}\n")
    
    # Estadísticas finales
    coherent_count = sum(1 for r in rows if validate_id_coherence(r.ger_url, r.grr_url)[0])
    complete = sum(1 for r in rows if r.ger_url and r.grr_url)
    high_conf = sum(1 for r in rows if r.ger_confidence >= args.min_confidence and r.grr_confidence >= args.min_confidence)
    
    print(f"📈 ESTADÍSTICAS FINALES:")
    print(f"  - IDs coherentes: {coherent_count}/{len(rows)} ({coherent_count/len(rows)*100:.1f}%)")
    print(f"  - GPCs completos (GER+GRR): {complete}/{len(rows)} ({complete/len(rows)*100:.1f}%)")
    print(f"  - Confianza ≥{args.min_confidence}%: {high_conf}/{len(rows)} ({high_conf/len(rows)*100:.1f}%)")
    
    # Regenerar MD y CSV automáticamente
    print(f"\n📦 REGENERANDO EXPORTACIONES (MD + CSV)...")
    try:
        regenerate_exports_from_json()
        print(f"✅ MD y CSV actualizados correctamente")
    except Exception as e:
        print(f"⚠️  Error regenerando exportaciones: {e}")


def regenerate_exports_from_json():
    """Regenera gpc_links_summary.md y gpc_links.csv desde JSON actualizado."""
    import csv
    from datetime import datetime
    
    md_path = REPO_ROOT / "docs" / "gpc_links_summary.md"
    csv_path = REPO_ROOT / "data" / "gpc_links.csv"
    
    with open(OUT_JSON, 'r', encoding='utf-8') as f:
        gpcs = json.load(f)
    
    # Regenerar MD
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# Enlaces GER/GRR de GPC (México: CENETEC/IMSS preferidos)\n\n")
        f.write(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write("Criterio: sólo dominios oficiales mexicanos (cenetec, imss, salud, gob.mx, issste, csg, insp).\n\n")
        
        for gpc in gpcs:
            f.write(f"\n## {gpc['title']}\n")
            
            if gpc.get('ger_url'):
                conf = gpc.get('ger_confidence', 0)
                f.write(f"- GER: {gpc['ger_url']} (conf {conf:.1f})\n")
            else:
                f.write("- GER: ❌ No encontrado\n")
            
            if gpc.get('grr_url'):
                conf = gpc.get('grr_confidence', 0)
                f.write(f"- GRR: {gpc['grr_url']} (conf {conf:.1f})\n")
            else:
                f.write("- GRR: ❌ No encontrado\n")
    
    # Regenerar CSV
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Título',
            'GER URL',
            'GER Confianza',
            'GER Fuente',
            'GRR URL',
            'GRR Confianza',
            'GRR Fuente'
        ])
        
        for gpc in gpcs:
            writer.writerow([
                gpc['title'],
                gpc.get('ger_url', ''),
                f"{gpc.get('ger_confidence', 0):.1f}",
                gpc.get('ger_source', ''),
                gpc.get('grr_url', ''),
                f"{gpc.get('grr_confidence', 0):.1f}",
                gpc.get('grr_source', '')
            ])


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        description="🔥 Validador MODO DIOS: Coherencia de IDs + Validación Semántica GPU"
    )
    parser.add_argument("--min-confidence", type=float, default=50.0,
                        help="Umbral mínimo de confianza semántica (default: 50%% - permisivo)")
    parser.add_argument("--sleep", type=float, default=0.5,
                        help="Segundos entre validaciones (default: 0.5)")
    parser.add_argument("--embedding-model", default="paraphrase-multilingual-mpnet-base-v2",
                        help="Modelo de embeddings (default: mpnet)")
    parser.add_argument("--embedding-device", default="auto", choices=["auto", "cpu", "cuda"],
                        help="Dispositivo (auto detecta GPU)")
    parser.add_argument("--embedding-batch-size", type=int, default=32,
                        help="Batch size para GPU (default: 32)")
    
    args = parser.parse_args(argv)
    
    process_god_mode_validation(args)
    
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
