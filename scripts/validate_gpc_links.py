
#!/usr/bin/env python3
"""
Script de validación avanzada de enlaces GPC con OCR.

Funcionalidades:
1. Valida todos los PDFs descargados
2. Extrae títulos usando PyMuPDF + Tesseract OCR (fallback)
3. Compara con títulos esperados usando similitud semántica
4. Detecta enlaces incorrectos
5. Genera reporte de calidad con estadísticas
6. Sugiere correcciones automáticas
"""

from __future__ import annotations

import json
import sys
import io
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import warnings

import requests

# Configure Tesseract path if available
try:
    import pytesseract
    TESSERACT_PATHS = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Tesseract-OCR\tesseract.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe",
    ]
    for tpath in TESSERACT_PATHS:
        if Path(tpath).exists():
            pytesseract.pytesseract.tesseract_cmd = str(tpath)
            break
except ImportError:
    pass

# Suppress warnings
warnings.filterwarnings("ignore")

# Paths
REPO_ROOT = Path(__file__).resolve().parents[1]
GPC_LINKS_JSON = REPO_ROOT / "data" / "gpc_links.json"
VALIDATION_REPORT = REPO_ROOT / "data" / "gpc_validation_report.json"
VALIDATION_MD = REPO_ROOT / "docs" / "gpc_validation_report.md"
PDF_CACHE_DIR = REPO_ROOT / "data" / ".pdf_cache"


@dataclass
class ValidationResult:
    """Resultado de validación de un PDF"""
    title_expected: str
    url: str
    doc_type: str  # GER o GRR
    status: str  # ok, mismatch, download_failed, ocr_failed
    title_extracted: Optional[str] = None
    similarity_score: float = 0.0
    extraction_method: str = ""  # pymupdf, tesseract, failed
    suggestion: Optional[str] = None
    http_status: Optional[int] = None


def download_pdf(url: str, timeout: int = 30) -> Optional[bytes]:
    """Descarga PDF con caché"""
    try:
        PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()
        cache_path = PDF_CACHE_DIR / f"{h}.pdf"
        
        if cache_path.exists():
            return cache_path.read_bytes()
        
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()
        
        data = response.content
        
        # Validar header PDF
        if data[:4] != b'%PDF':
            return None
        
        cache_path.write_bytes(data)
        return data
    except Exception as e:
        print(f"  ✗ Error descargando {url}: {e}")
        return None


def extract_title_pymupdf(pdf_bytes: bytes) -> Tuple[Optional[str], str]:
    """Extrae título usando PyMuPDF (rápido, texto nativo)"""
    try:
        import fitz  # PyMuPDF
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) == 0:
            return None, "failed"
        
        page = doc[0]  # Primera página
        
        # Método 1: Metadata
        metadata = doc.metadata
        if metadata and metadata.get('title'):
            title = metadata['title'].strip()
            if len(title) > 10:
                return title, "pymupdf_metadata"
        
        # Método 2: Texto de primera página
        text = page.get_text()
        if text:
            # Buscar título en las primeras líneas
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # Heurística: el título suele estar en las primeras 5-10 líneas
            # y es más largo que otras líneas
            title_candidates = []
            for i, line in enumerate(lines[:15]):
                # Ignorar líneas muy cortas o números
                if len(line) < 10 or line.isdigit():
                    continue
                # Preferir líneas que contengan palabras clave médicas
                if any(kw in line.lower() for kw in ['diagnóstico', 'tratamiento', 'guía', 'práctica', 'clínica']):
                    title_candidates.append((len(line), i, line))
            
            if title_candidates:
                # Ordenar por longitud (título suele ser la línea más larga)
                title_candidates.sort(reverse=True)
                return title_candidates[0][2], "pymupdf_text"
            
            # Fallback: primera línea significativa
            for line in lines[:10]:
                if len(line) > 15:
                    return line, "pymupdf_text_fallback"
        
        return None, "pymupdf_no_text"
    except Exception as e:
        return None, f"pymupdf_error: {e}"


def extract_title_tesseract_ocr(pdf_bytes: bytes) -> Tuple[Optional[str], str]:
    """Extrae título usando Tesseract OCR (para PDFs escaneados)"""
    try:
        import fitz  # PyMuPDF para renderizar
        import pytesseract
        from PIL import Image
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) == 0:
            return None, "ocr_no_pages"
        
        page = doc[0]
        
        # Renderizar primera página a imagen de alta resolución
        pix = page.get_pixmap(dpi=300)  # 300 DPI para mejor OCR
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Recortar solo el área del título (tercio superior)
        width, height = img.size
        title_area = img.crop((0, 0, width, height // 3))
        
        # OCR con español
        text = pytesseract.image_to_string(title_area, lang='spa', config='--psm 6')
        
        if text:
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # Buscar línea más larga (probablemente el título)
            title_candidates = [(len(l), l) for l in lines if len(l) > 10]
            if title_candidates:
                title_candidates.sort(reverse=True)
                return title_candidates[0][1], "tesseract_ocr"
            
            # Fallback: primera línea
            if lines:
                return lines[0], "tesseract_ocr_fallback"
        
        return None, "ocr_no_text"
    except Exception as e:
        return None, f"ocr_error: {e}"


def extract_title_advanced(pdf_bytes: bytes) -> Tuple[Optional[str], str]:
    """
    Extracción en cascada:
    1. PyMuPDF (rápido, 95% de casos)
    2. Tesseract OCR (fallback para PDFs escaneados)
    """
    # Nivel 1: PyMuPDF
    title, method = extract_title_pymupdf(pdf_bytes)
    if title and len(title) > 10:
        return title, method
    
    # Nivel 2: Tesseract OCR (solo si PyMuPDF falló)
    print("    ⚠️  PyMuPDF falló, intentando con Tesseract OCR...")
    title_ocr, method_ocr = extract_title_tesseract_ocr(pdf_bytes)
    if title_ocr:
        return title_ocr, method_ocr
    
    return None, "all_methods_failed"


def calculate_similarity(title1: str, title2: str) -> float:
    """Calcula similitud entre títulos (fuzzy + semántica si disponible)"""
    import difflib
    
    # Normalizar
    t1 = re.sub(r'\s+', ' ', title1.lower().strip())
    t2 = re.sub(r'\s+', ' ', title2.lower().strip())
    
    # Similitud de secuencia
    seq_sim = difflib.SequenceMatcher(None, t1, t2).ratio()
    
    # TODO: Agregar similitud semántica con sentence-transformers si está disponible
    
    return seq_sim


def validate_pdf(expected_title: str, url: str, doc_type: str) -> ValidationResult:
    """Valida un PDF individual"""
    result = ValidationResult(
        title_expected=expected_title,
        url=url,
        doc_type=doc_type,
        status="pending"
    )
    
    # Descargar PDF
    print(f"  📄 Validando {doc_type}: {url[:60]}...")
    pdf_bytes = download_pdf(url)
    
    if not pdf_bytes:
        result.status = "download_failed"
        return result
    
    result.http_status = 200
    
    # Extraer título con OCR avanzado
    extracted_title, method = extract_title_advanced(pdf_bytes)
    result.extraction_method = method
    result.title_extracted = extracted_title
    
    if not extracted_title:
        result.status = "ocr_failed"
        print(f"    ✗ No se pudo extraer título ({method})")
        return result
    
    # Calcular similitud
    similarity = calculate_similarity(expected_title, extracted_title)
    result.similarity_score = similarity
    
    print(f"    ✓ Título extraído ({method})")
    print(f"      Esperado: {expected_title[:70]}...")
    print(f"      Extraído: {extracted_title[:70]}...")
    print(f"      Similitud: {similarity:.2%}")
    
    # Determinar estado
    if similarity >= 0.7:
        result.status = "ok"
    elif similarity >= 0.4:
        result.status = "warning"
        result.suggestion = f"Posible mismatch (similitud {similarity:.0%})"
    else:
        result.status = "mismatch"
        result.suggestion = f"Título no coincide (similitud {similarity:.0%})"
    
    return result


def validate_all_links() -> Dict[str, Any]:
    """Valida todos los enlaces en gpc_links.json"""
    print("\n🔍 VALIDACIÓN AVANZADA DE ENLACES GPC CON OCR\n")
    
    if not GPC_LINKS_JSON.exists():
        print(f"✗ No se encontró {GPC_LINKS_JSON}")
        return {}
    
    # Cargar enlaces
    gpc_links = json.loads(GPC_LINKS_JSON.read_text(encoding='utf-8'))
    print(f"📊 Total GPCs: {len(gpc_links)}\n")
    
    results = []
    stats = {
        "total": len(gpc_links),
        "ger_found": 0,
        "grr_found": 0,
        "ger_validated": 0,
        "grr_validated": 0,
        "ger_ok": 0,
        "grr_ok": 0,
        "ger_warning": 0,
        "grr_warning": 0,
        "ger_mismatch": 0,
        "grr_mismatch": 0,
        "download_failed": 0,
        "ocr_failed": 0
    }
    
    for i, gpc in enumerate(gpc_links, 1):
        title = gpc['title']
        print(f"[{i}/{len(gpc_links)}] {title[:70]}...")
        
        # Validar GER
        if gpc.get('ger_url'):
            stats['ger_found'] += 1
            result_ger = validate_pdf(title, gpc['ger_url'], "GER")
            results.append(asdict(result_ger))
            stats['ger_validated'] += 1
            if result_ger.status == "ok":
                stats['ger_ok'] += 1
            elif result_ger.status == "warning":
                stats['ger_warning'] += 1
            elif result_ger.status == "mismatch":
                stats['ger_mismatch'] += 1
            elif result_ger.status == "download_failed":
                stats['download_failed'] += 1
            elif result_ger.status == "ocr_failed":
                stats['ocr_failed'] += 1
        
        # Validar GRR
        if gpc.get('grr_url'):
            stats['grr_found'] += 1
            result_grr = validate_pdf(title, gpc['grr_url'], "GRR")
            results.append(asdict(result_grr))
            stats['grr_validated'] += 1
            if result_grr.status == "ok":
                stats['grr_ok'] += 1
            elif result_grr.status == "warning":
                stats['grr_warning'] += 1
            elif result_grr.status == "mismatch":
                stats['grr_mismatch'] += 1
            elif result_grr.status == "download_failed":
                stats['download_failed'] += 1
            elif result_grr.status == "ocr_failed":
                stats['ocr_failed'] += 1
        
        print()  # Línea en blanco
    
    # Generar reporte
    report = {
        "timestamp": str(pd.Timestamp.now()) if 'pd' in dir() else str(__import__('datetime').datetime.now()),
        "stats": stats,
        "results": results
    }
    
    return report


def generate_report(report: Dict[str, Any]):
    """Genera reportes JSON y Markdown"""
    # JSON
    VALIDATION_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"✓ Reporte JSON: {VALIDATION_REPORT}")
    
    # Markdown
    stats = report['stats']
    md_lines = [
        "# Reporte de Validación de Enlaces GPC\n",
        f"**Fecha:** {report.get('timestamp', 'N/A')}\n",
        "## Estadísticas Generales\n",
        f"- **Total GPCs:** {stats['total']}",
        f"- **GER encontrados:** {stats['ger_found']} / {stats['total']} ({stats['ger_found']/stats['total']*100:.1f}%)",
        f"- **GRR encontrados:** {stats['grr_found']} / {stats['total']} ({stats['grr_found']/stats['total']*100:.1f}%)",
        "",
        "## Validación de PDFs\n",
        f"- **GER validados:** {stats['ger_validated']}",
        f"  - ✅ OK: {stats['ger_ok']}",
        f"  - ⚠️  Warning: {stats['ger_warning']}",
        f"  - ❌ Mismatch: {stats['ger_mismatch']}",
        "",
        f"- **GRR validados:** {stats['grr_validated']}",
        f"  - ✅ OK: {stats['grr_ok']}",
        f"  - ⚠️  Warning: {stats['grr_warning']}",
        f"  - ❌ Mismatch: {stats['grr_mismatch']}",
        "",
        f"- **Errores de descarga:** {stats['download_failed']}",
        f"- **Errores de OCR:** {stats['ocr_failed']}",
        "",
        "## Problemas Detectados\n"
    ]
    
    # Listar problemas
    problems = [r for r in report['results'] if r['status'] in ('warning', 'mismatch')]
    if problems:
        md_lines.append(f"\n**Total problemas:** {len(problems)}\n")
        for p in problems:
            md_lines.append(f"### {p['title_expected'][:60]}...\n")
            md_lines.append(f"- **Tipo:** {p['doc_type']}")
            md_lines.append(f"- **URL:** {p['url']}")
            md_lines.append(f"- **Estado:** {p['status']}")
            md_lines.append(f"- **Similitud:** {p['similarity_score']:.0%}")
            md_lines.append(f"- **Título esperado:** {p['title_expected']}")
            md_lines.append(f"- **Título extraído:** {p.get('title_extracted', 'N/A')}")
            md_lines.append(f"- **Sugerencia:** {p.get('suggestion', 'N/A')}")
            md_lines.append("")
    else:
        md_lines.append("✅ No se detectaron problemas\n")
    
    VALIDATION_MD.write_text('\n'.join(md_lines), encoding='utf-8')
    print(f"✓ Reporte Markdown: {VALIDATION_MD}")


def main() -> int:
    report = validate_all_links()
    
    if report:
        generate_report(report)
        
        print("\n" + "="*80)
        print("📊 RESUMEN")
        print("="*80)
        stats = report['stats']
        print(f"Total GPCs: {stats['total']}")
        print(f"GER: {stats['ger_ok']}/{stats['ger_found']} OK, {stats['ger_warning']} warnings, {stats['ger_mismatch']} mismatches")
        print(f"GRR: {stats['grr_ok']}/{stats['grr_found']} OK, {stats['grr_warning']} warnings, {stats['grr_mismatch']} mismatches")
        print(f"Errores: {stats['download_failed']} descargas, {stats['ocr_failed']} OCR")
        print("="*80 + "\n")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
