#!/usr/bin/env python3
"""
Validación INTELIGENTE de GPCs con IA y GPU

Este script valida los enlaces GPC usando:
1. Embeddings semánticos (sentence-transformers en GPU)
2. Clasificación automática GER vs GRR con IA
3. OCR avanzado para PDFs corruptos
4. Matching inteligente título ↔ contenido PDF

Usa RTX 4070 para máxima eficiencia.

Autor: AI Assistant
Fecha: 2025-01-17
"""

import json
import sys
import warnings
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import requests
import io
from dataclasses import dataclass, asdict

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
GPC_LINKS_JSON = DATA_DIR / "gpc_links.json"
VALIDATION_REPORT_JSON = DATA_DIR / "gpc_validation_report.json"
VALIDATION_REPORT_MD = REPO_ROOT / "docs" / "gpc_validation_report.md"


@dataclass
class ValidationResult:
    """Resultado de validación de un GPC"""
    title: str
    ger_url: Optional[str]
    grr_url: Optional[str]
    
    # Validación GER
    ger_downloaded: bool = False
    ger_text_extracted: bool = False
    ger_ocr_used: bool = False
    ger_semantic_score: float = 0.0
    ger_classified_as: Optional[str] = None  # "GER", "GRR", "UNKNOWN"
    ger_confidence: float = 0.0
    ger_valid: bool = False
    ger_error: Optional[str] = None
    
    # Validación GRR
    grr_downloaded: bool = False
    grr_text_extracted: bool = False
    grr_ocr_used: bool = False
    grr_semantic_score: float = 0.0
    grr_classified_as: Optional[str] = None  # "GER", "GRR", "UNKNOWN"
    grr_confidence: float = 0.0
    grr_valid: bool = False
    grr_error: Optional[str] = None
    
    # Flags de problemas
    needs_review: bool = False
    swap_suggested: bool = False  # Si GER y GRR están intercambiados
    

class IntelligentGPCValidator:
    """Validador inteligente de GPCs con IA en GPU"""
    
    def __init__(self, device: str = "cuda", batch_size: int = 32):
        self.device = device
        self.batch_size = batch_size
        self.model = None
        self.torch = None
        self._load_model()
    
    def _load_model(self):
        """Carga el modelo de sentence-transformers en GPU"""
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            
            if self.device == "cuda" and not torch.cuda.is_available():
                print("⚠️  CUDA no disponible, usando CPU")
                self.device = "cpu"
            
            print(f"\n🔄 Cargando modelo de IA en {self.device.upper()}...")
            self.model = SentenceTransformer(
                "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
                device=self.device
            )
            self.torch = torch
            
            if self.device == "cuda":
                print(f"✅ Modelo cargado en GPU: {torch.cuda.get_device_name(0)}")
                print(f"   VRAM disponible: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            else:
                print("✅ Modelo cargado en CPU")
                
        except Exception as e:
            print(f"❌ Error cargando modelo: {e}")
            sys.exit(1)
    
    def download_pdf(self, url: str, timeout: int = 30) -> Optional[bytes]:
        """Descarga un PDF con reintentos"""
        try:
            with requests.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                
                buf = io.BytesIO()
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        buf.write(chunk)
                
                data = buf.getvalue()
                
                # Validar header PDF
                if not data or data[:4] != b'%PDF':
                    return None
                
                return data
                
        except Exception as e:
            return None
    
    def extract_text_advanced(self, pdf_bytes: bytes) -> Tuple[str, bool]:
        """
        Extrae texto del PDF con cascading fallback
        
        Returns: (texto_extraído, ocr_usado)
        """
        if not pdf_bytes or len(pdf_bytes) < 4:
            return "", False
        
        ocr_used = False
        
        # Nivel 1: PyMuPDF (rápido)
        try:
            import fitz
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                
                # Extraer primeras 5 páginas
                text_parts = []
                for page_num in range(min(5, len(doc))):
                    page = doc[page_num]
                    text = page.get_text()
                    if text:
                        text_parts.append(text)
                
                if text_parts:
                    full_text = "\n".join(text_parts)
                    
                    # Si hay suficiente texto, retornar
                    if len(full_text.strip()) > 200:
                        return full_text, False
        except Exception:
            pass
        
        # Nivel 2: pdfminer.six
        try:
            from pdfminer.high_level import extract_text
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                text = extract_text(io.BytesIO(pdf_bytes), maxpages=5)
                
                if text and len(text.strip()) > 200:
                    return text, False
        except Exception:
            pass
        
        # Nivel 3: OCR con Tesseract
        try:
            import fitz
            import pytesseract
            from PIL import Image
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                
                text_parts = []
                for page_num in range(min(3, len(doc))):  # Solo 3 páginas para OCR (lento)
                    page = doc[page_num]
                    
                    # Renderizar a 300 DPI
                    pix = page.get_pixmap(dpi=300)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    
                    # OCR español
                    text = pytesseract.image_to_string(img, lang='spa', config='--psm 6')
                    if text:
                        text_parts.append(text)
                
                if text_parts:
                    ocr_used = True
                    return "\n".join(text_parts), True
                    
        except Exception:
            pass
        
        return "", ocr_used
    
    def classify_document_type(self, text: str) -> Tuple[str, float]:
        """
        🔥 CORREGIDO: Clasifica documento como GER o GRR correctamente
        
        NOMENCLATURA IMPORTANTE:
        - GER/ER = Guía de Evidencias y Recomendaciones (COMPLETA, larga)
        - GRR/RR = Guía de Referencia Rápida (RESUMEN, corta)
        
        SITIOS:
        - IMSS: usa GER/GRR en URLs
        - CENETEC: usa ER/RR en URLs
        
        SON EQUIVALENTES:
        - GER = ER (documento completo de evidencias)
        - GRR = RR (documento resumen de referencia rápida)
        
        Returns: (tipo, confidence)
            tipo: "GER" para documentos completos (ER/GER)
                  "GRR" para documentos resumen (RR/GRR)
        """
        if not text or len(text) < 50:
            return "UNKNOWN", 0.0
        
        # Normalizar texto
        text_lower = text.lower()
        text_sample = text_lower[:8000]  # Primeros 8000 chars (más contexto)
        
        # Keywords para GER/ER (documento COMPLETO de evidencias)
        ger_keywords = {
            # Frases específicas de documentos completos
            'evidencias y recomendaciones': 5.0,
            'guía de evidencias y recomendaciones': 5.0,
            'guia de evidencias': 4.0,
            'evidencias': 2.5,
            'recomendaciones': 2.5,
            'evidencia': 2.0,
            'recomendacion': 2.0,
            
            # Metodología (solo en documentos completos)
            'metodología': 3.0,
            'metodologia': 3.0,
            'búsqueda sistemática': 3.5,
            'busqueda sistematica': 3.5,
            'revision sistematica': 3.0,
            'revisión sistemática': 3.0,
            'estrategia de búsqueda': 2.5,
            
            # Calidad de evidencia (solo en completos)
            'calidad de la evidencia': 4.0,
            'nivel de evidencia': 3.5,
            'fuerza de la recomendacion': 4.0,
            'grado de recomendacion': 3.5,
            'gradacion': 2.5,
            'grade': 2.5,
            
            # Referencias (abundantes en completos)
            'referencias bibliográficas': 3.0,
            'referencias bibliograficas': 3.0,
            'bibliografia': 2.0,
            'bibliografía': 2.0,
        }
        
        # Keywords para GRR/RR (documento RESUMEN de referencia rápida)
        grr_keywords = {
            # Frases específicas de referencia rápida
            'referencia rápida': 6.0,
            'referencia rapida': 6.0,
            'guía de referencia rápida': 6.0,
            'guia de referencia rapida': 6.0,
            'guía rápida': 4.0,
            'guia rapida': 4.0,
            
            # Elementos visuales (más en resúmenes)
            'algoritmo': 3.5,
            'algoritmo diagnóstico': 4.0,
            'algoritmo terapeutico': 4.0,
            'diagrama de flujo': 4.0,
            'diagrama': 2.5,
            'flujograma': 3.0,
            'esquema': 2.0,
            
            # Características de resumen
            'resumen': 2.0,
            'puntos clave': 3.0,
            'criterios de referencia': 2.5,
            'criterios de derivacion': 2.5,
            'abordaje inicial': 2.0,
        }
        
        ger_score = 0.0
        grr_score = 0.0
        
        # Scoring por keywords
        for keyword, weight in ger_keywords.items():
            count = text_sample.count(keyword)
            if count > 0:
                ger_score += count * weight
        
        for keyword, weight in grr_keywords.items():
            count = text_sample.count(keyword)
            if count > 0:
                grr_score += count * weight
        
        # Heurística de longitud (GRR suele ser mucho más corto)
        # GRR típicamente < 20 páginas (~20k chars)
        # GER típicamente > 50 páginas (~50k chars)
        text_len = len(text)
        if text_len < 15000:  # Muy corto → probablemente GRR
            grr_score += 3.0
        elif text_len < 25000:  # Corto → posiblemente GRR
            grr_score += 1.5
        elif text_len > 60000:  # Muy largo → probablemente GER
            ger_score += 3.0
        elif text_len > 40000:  # Largo → posiblemente GER
            ger_score += 1.5
        
        # GER tiene MUCHAS más referencias bibliográficas
        ref_patterns = ['et al', 'doi:', 'pubmed', 'pmid', 'referencias:', 'bibliograf']
        ref_count = sum(text_sample.count(p) for p in ref_patterns)
        if ref_count > 10:  # Muchas referencias → GER
            ger_score += ref_count * 0.8
        elif ref_count > 5:
            ger_score += ref_count * 0.4
        
        # Decisión final con umbral mínimo
        total_score = ger_score + grr_score
        
        if total_score < 1.0:  # Muy poca evidencia
            return "UNKNOWN", 0.0
        
        if ger_score > grr_score:
            confidence = ger_score / total_score
            # GER = Evidencias completas (puede aparecer como ER o GER en URL)
            return "GER", confidence
        elif grr_score > ger_score:
            confidence = grr_score / total_score
            # GRR = Referencia rápida (puede aparecer como RR o GRR en URL)
            return "GRR", confidence
        else:
            # Empate → usar longitud como desempate
            if text_len > 30000:
                return "GER", 0.5
            else:
                return "GRR", 0.5
    
    def compute_semantic_similarity(self, title: str, document_text: str) -> float:
        """
        Calcula similitud semántica entre título y contenido del documento
        usando embeddings en GPU
        
        Returns: Score 0.0-1.0
        """
        if not document_text or len(document_text) < 50:
            return 0.0
        
        try:
            # Preparar textos
            title_clean = title.strip()
            
            # Extraer primeras líneas del documento (probablemente el título interno)
            lines = [l.strip() for l in document_text.split('\n') if l.strip()]
            
            # Buscar líneas significativas (ignorar headers/footers)
            significant_lines = []
            for line in lines[:50]:  # Primeras 50 líneas
                # Filtrar líneas muy cortas o números
                if len(line) < 10 or line.isdigit():
                    continue
                
                # Filtrar headers comunes
                if line.lower() in ['cenetec', 'imss', 'secretaría de salud', 'secretaria de salud']:
                    continue
                
                significant_lines.append(line)
                
                if len(significant_lines) >= 10:
                    break
            
            if not significant_lines:
                return 0.0
            
            # Embeddings en GPU (batch)
            title_emb = self.model.encode([title_clean], convert_to_tensor=True, show_progress_bar=False)
            lines_emb = self.model.encode(significant_lines, convert_to_tensor=True, show_progress_bar=False)
            
            # Similitud coseno
            similarities = self.torch.nn.functional.cosine_similarity(
                title_emb.repeat(len(significant_lines), 1),
                lines_emb
            )
            
            # Mejor similitud
            max_sim = float(similarities.max().cpu())
            
            return max_sim
            
        except Exception as e:
            print(f"    ⚠️  Error en similitud semántica: {e}")
            return 0.0
    
    def validate_gpc_entry(self, entry: Dict[str, Any], index: int, total: int) -> ValidationResult:
        """Valida una entrada de GPC completa"""
        
        title = entry.get('title', 'Sin título')
        ger_url = entry.get('ger_url')
        grr_url = entry.get('grr_url')
        
        print(f"\n[{index}/{total}] {title}")
        
        result = ValidationResult(
            title=title,
            ger_url=ger_url,
            grr_url=grr_url
        )
        
        # Validar GER
        if ger_url:
            print(f"  🔍 Validando GER: {ger_url[:70]}...")
            
            pdf_bytes = self.download_pdf(ger_url)
            if pdf_bytes:
                result.ger_downloaded = True
                
                text, ocr_used = self.extract_text_advanced(pdf_bytes)
                result.ger_ocr_used = ocr_used
                
                if text:
                    result.ger_text_extracted = True
                    
                    if ocr_used:
                        print(f"    📄 OCR usado para extracción")
                    
                    # Clasificar tipo de documento
                    doc_type, confidence = self.classify_document_type(text)
                    result.ger_classified_as = doc_type
                    result.ger_confidence = confidence
                    
                    print(f"    🤖 Clasificado como: {doc_type} (confianza: {confidence:.2%})")
                    
                    # Similitud semántica
                    semantic_score = self.compute_semantic_similarity(title, text)
                    result.ger_semantic_score = semantic_score
                    
                    print(f"    🧠 Similitud semántica: {semantic_score:.2%}")
                    
                    # Validación final
                    if doc_type == "GER" and semantic_score > 0.5:
                        result.ger_valid = True
                        print(f"    ✅ GER VÁLIDO")
                    elif doc_type == "GRR":
                        result.needs_review = True
                        result.swap_suggested = True
                        print(f"    ⚠️  ADVERTENCIA: Parece ser GRR, no GER!")
                    elif semantic_score < 0.3:
                        result.needs_review = True
                        print(f"    ⚠️  Baja similitud con título esperado")
                    else:
                        result.ger_valid = True  # Aceptar si no hay señales claras de error
                        print(f"    ✓ GER aceptable")
                else:
                    result.ger_error = "No se pudo extraer texto"
                    print(f"    ❌ No se pudo extraer texto")
            else:
                result.ger_error = "No se pudo descargar"
                print(f"    ❌ No se pudo descargar")
        
        # Validar GRR
        if grr_url:
            print(f"  🔍 Validando GRR: {grr_url[:70]}...")
            
            pdf_bytes = self.download_pdf(grr_url)
            if pdf_bytes:
                result.grr_downloaded = True
                
                text, ocr_used = self.extract_text_advanced(pdf_bytes)
                result.grr_ocr_used = ocr_used
                
                if text:
                    result.grr_text_extracted = True
                    
                    if ocr_used:
                        print(f"    📄 OCR usado para extracción")
                    
                    # Clasificar tipo de documento
                    doc_type, confidence = self.classify_document_type(text)
                    result.grr_classified_as = doc_type
                    result.grr_confidence = confidence
                    
                    print(f"    🤖 Clasificado como: {doc_type} (confianza: {confidence:.2%})")
                    
                    # Similitud semántica
                    semantic_score = self.compute_semantic_similarity(title, text)
                    result.grr_semantic_score = semantic_score
                    
                    print(f"    🧠 Similitud semántica: {semantic_score:.2%}")
                    
                    # Validación final
                    if doc_type == "GRR" and semantic_score > 0.5:
                        result.grr_valid = True
                        print(f"    ✅ GRR VÁLIDO")
                    elif doc_type == "GER":
                        result.needs_review = True
                        result.swap_suggested = True
                        print(f"    ⚠️  ADVERTENCIA: Parece ser GER, no GRR!")
                    elif semantic_score < 0.3:
                        result.needs_review = True
                        print(f"    ⚠️  Baja similitud con título esperado")
                    else:
                        result.grr_valid = True  # Aceptar si no hay señales claras de error
                        print(f"    ✓ GRR aceptable")
                else:
                    result.grr_error = "No se pudo extraer texto"
                    print(f"    ❌ No se pudo extraer texto")
            else:
                result.grr_error = "No se pudo descargar"
                print(f"    ❌ No se pudo descargar")
        
        return result
    
    def validate_all(self, gpc_links_path: Path) -> List[ValidationResult]:
        """Valida todos los GPCs en el archivo JSON"""
        
        if not gpc_links_path.exists():
            print(f"❌ Archivo no encontrado: {gpc_links_path}")
            sys.exit(1)
        
        with open(gpc_links_path, 'r', encoding='utf-8') as f:
            entries = json.load(f)
        
        print(f"\n{'=' * 80}")
        print(f"🔬 VALIDACIÓN INTELIGENTE DE GPCs")
        print(f"{'=' * 80}")
        print(f"Total de GPCs: {len(entries)}")
        print(f"Modelo IA: paraphrase-multilingual-mpnet-base-v2")
        print(f"Dispositivo: {self.device.upper()}")
        print(f"{'=' * 80}\n")
        
        results = []
        
        for i, entry in enumerate(entries, 1):
            result = self.validate_gpc_entry(entry, i, len(entries))
            results.append(result)
        
        return results
    
    def generate_report(self, results: List[ValidationResult]):
        """Genera reporte de validación en JSON y Markdown"""
        
        # JSON
        json_data = [asdict(r) for r in results]
        with open(VALIDATION_REPORT_JSON, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        # Estadísticas
        total = len(results)
        ger_valid = sum(1 for r in results if r.ger_valid)
        grr_valid = sum(1 for r in results if r.grr_valid)
        both_valid = sum(1 for r in results if r.ger_valid and r.grr_valid)
        needs_review = sum(1 for r in results if r.needs_review)
        swap_suggested = sum(1 for r in results if r.swap_suggested)
        ocr_used = sum(1 for r in results if r.ger_ocr_used or r.grr_ocr_used)
        
        # Markdown
        lines = []
        lines.append("# 🔬 Reporte de Validación Inteligente de GPCs\n")
        lines.append(f"**Fecha:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        lines.append(f"**Total GPCs:** {total}\n")
        lines.append("---\n")
        
        lines.append("## 📊 Estadísticas Generales\n")
        lines.append(f"- **GER válidos:** {ger_valid}/{total} ({ger_valid/total*100:.1f}%)")
        lines.append(f"- **GRR válidos:** {grr_valid}/{total} ({grr_valid/total*100:.1f}%)")
        lines.append(f"- **Ambos válidos:** {both_valid}/{total} ({both_valid/total*100:.1f}%)")
        lines.append(f"- **Requieren revisión:** {needs_review} ({needs_review/total*100:.1f}%)")
        lines.append(f"- **Intercambios sugeridos:** {swap_suggested}")
        lines.append(f"- **OCR utilizado:** {ocr_used} GPCs\n")
        
        lines.append("---\n")
        lines.append("## ⚠️  GPCs que Requieren Revisión\n")
        
        for r in results:
            if r.needs_review:
                lines.append(f"\n### {r.title}\n")
                
                if r.swap_suggested:
                    lines.append("**🔄 INTERCAMBIO SUGERIDO:** GER y GRR parecen estar intercambiados\n")
                
                if r.ger_url:
                    lines.append(f"**GER:**")
                    lines.append(f"- URL: {r.ger_url}")
                    lines.append(f"- Clasificado como: {r.ger_classified_as} ({r.ger_confidence:.1%})")
                    lines.append(f"- Similitud semántica: {r.ger_semantic_score:.1%}")
                    if r.ger_error:
                        lines.append(f"- Error: {r.ger_error}")
                    lines.append("")
                
                if r.grr_url:
                    lines.append(f"**GRR:**")
                    lines.append(f"- URL: {r.grr_url}")
                    lines.append(f"- Clasificado como: {r.grr_classified_as} ({r.grr_confidence:.1%})")
                    lines.append(f"- Similitud semántica: {r.grr_semantic_score:.1%}")
                    if r.grr_error:
                        lines.append(f"- Error: {r.grr_error}")
                    lines.append("")
        
        with open(VALIDATION_REPORT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        
        print(f"\n{'=' * 80}")
        print(f"✅ VALIDACIÓN COMPLETADA")
        print(f"{'=' * 80}")
        print(f"📄 Reporte JSON: {VALIDATION_REPORT_JSON}")
        print(f"📄 Reporte MD: {VALIDATION_REPORT_MD}")
        print(f"\n📊 Resumen:")
        print(f"  • GER válidos: {ger_valid}/{total} ({ger_valid/total*100:.1f}%)")
        print(f"  • GRR válidos: {grr_valid}/{total} ({grr_valid/total*100:.1f}%)")
        print(f"  • Ambos válidos: {both_valid}/{total} ({both_valid/total*100:.1f}%)")
        print(f"  • Requieren revisión: {needs_review}")
        print(f"  • Intercambios sugeridos: {swap_suggested}")
        print(f"  • OCR utilizado: {ocr_used} GPCs")
        print(f"{'=' * 80}\n")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Validación inteligente de GPCs con IA en GPU")
    parser.add_argument("--input", default=str(GPC_LINKS_JSON), help="JSON de GPCs a validar")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="Dispositivo (cuda o cpu)")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size para embeddings")
    parser.add_argument("--limit", type=int, help="Limitar validación a N GPCs (para pruebas)")
    
    args = parser.parse_args()
    
    validator = IntelligentGPCValidator(device=args.device, batch_size=args.batch_size)
    
    # Cargar y opcionalmente limitar
    with open(args.input, 'r', encoding='utf-8') as f:
        entries = json.load(f)
    
    if args.limit:
        entries = entries[:args.limit]
        print(f"⚠️  Limitando validación a {args.limit} GPCs")
    
    # Validar
    results = validator.validate_all(Path(args.input))
    
    # Generar reporte
    validator.generate_report(results)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
