#!/usr/bin/env python3
"""
Find GER and GRR links for Mexican GPCs (prefer CENETEC and IMSS) from the temario Markdown.

Defaults:
- Restricts to Mexican official domains (CENETEC, IMSS, Salud, gob.mx, ISSSTE, CSG, INSP)
- Prefers CENETEC and IMSS when selecting among results
- Searches PDFs for GER (Guía de Evidencias y Recomendaciones) and GRR (Guía de Referencia Rápida)

Providers (set one): SERPER_API_KEY, SERPAPI_API_KEY, or GOOGLE_API_KEY + GOOGLE_CSE_ID

Outputs: data/gpc_links.csv, data/gpc_links.json, docs/gpc_links_summary.md
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import warnings
import logging
import io
import hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import difflib
import requests

# Configure Tesseract path if available (for OCR fallback)
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

# Suppress annoying pypdf and pdfminer warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pypdf")
warnings.filterwarnings("ignore", category=UserWarning, module="pdfminer")
warnings.filterwarnings("ignore", message="Multiple definitions in dictionary")
warnings.filterwarnings("ignore", message=".*Advanced encoding.*not implemented yet.*")

# Configure logging to suppress all PDF library messages except errors
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfminer.pdfpage").setLevel(logging.ERROR)
logging.getLogger("pdfminer.pdfinterp").setLevel(logging.ERROR)
logging.getLogger("pdfminer.converter").setLevel(logging.ERROR)
logging.getLogger("pdfminer.cmapdb").setLevel(logging.ERROR)
logging.getLogger("pdfminer.pdffont").setLevel(logging.ERROR)


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMARIO_MD = REPO_ROOT / "docs" / "# Temario ENARM - Guías de Práctica Clín.md"
OUT_DIR = REPO_ROOT / "data"
OUT_CSV = OUT_DIR / "gpc_links.csv"
OUT_JSON = OUT_DIR / "gpc_links.json"
OUT_MD = REPO_ROOT / "docs" / "gpc_links_summary.md"
PDF_CACHE_DIR = OUT_DIR / ".pdf_cache"


@dataclass
class GPCLinkResult:
    title: str
    query_ger: str
    query_grr: str
    ger_url: Optional[str] = None
    grr_url: Optional[str] = None
    ger_source: Optional[str] = None
    grr_source: Optional[str] = None
    ger_status: Optional[int] = None
    grr_status: Optional[int] = None
    ger_confidence: float = 0.0
    grr_confidence: float = 0.0


# Strictly prefer Mexican official sources; order defines preference
PREFERRED_HOSTS = [
    "cenetec.salud.gob.mx",  # CENETEC-GPC
    "cenetec-difusion",      # CENETEC difusión/mirrors
    "imss.gob.mx",           # IMSS
    "salud.gob.mx",          # Secretaría de Salud
    "issste.gob.mx",         # ISSSTE
    "csg.gob.mx",            # Consejo de Salubridad General
    "insp.mx",               # Instituto Nacional de Salud Pública
    "gob.mx",                # Portal gob.mx (menos específico)
]

# Allowed substrings in host/path (stricter than generic .mx)
ALLOWED_HOST_PATTERNS = [
    "cenetec.salud.gob.mx",
    "cenetec-difusion",  # mirror frecuente
    "imss.gob.mx",
    "salud.gob.mx",
    "issste.gob.mx",
    "csg.gob.mx",
    "insp.mx",
    # gob.mx sections used por CENETEC/Salud
    "gob.mx/cenetec",
    "gob.mx/salud",
]

# Trusted domains for smart validation (same as PREFERRED_HOSTS but for site: queries)
TRUSTED_DOMAINS = [
    "cenetec-difusion.com",
    "cenetec.salud.gob.mx",
    "imss.gob.mx",
    "salud.gob.mx",
]


def host_score(url: str) -> int:
    url_l = url.lower()
    for i, host in enumerate(PREFERRED_HOSTS):
        if host in url_l:
            # earlier in list -> higher score
            return len(PREFERRED_HOSTS) - i
    return 0


def is_allowed_host(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in ALLOWED_HOST_PATTERNS)


def extract_gpc_titles(md_text: str, subset_filter: Optional[str] = None) -> List[str]:
    pattern = re.compile(r"\*\*GPC\s+([^*\n]+)\*\*")
    titles = [m.group(1).strip() for m in pattern.finditer(md_text)]
    titles = [re.sub(r"\s+", " ", t) for t in titles]
    if subset_filter:
        sf = subset_filter.lower()
        titles = [t for t in titles if sf in t.lower()]
    seen = set()
    unique: List[str] = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


class SearchProvider:
    def search(self, query: str, num: int = 10) -> List[Dict[str, Any]]:
        raise NotImplementedError


class SerperProvider(SearchProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, num: int = 10) -> List[Dict[str, Any]]:
        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}
        payload = {"q": query, "num": num}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        results = data.get("organic", [])
        return [{"link": item.get("link"), "title": item.get("title"), "snippet": item.get("snippet")}
                for item in results if item.get("link")]


class SerpAPIProvider(SearchProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, num: int = 10) -> List[Dict[str, Any]]:
        url = "https://serpapi.com/search.json"
        params = {"engine": "google", "q": query, "num": num, "api_key": self.api_key}
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        results = data.get("organic_results", [])
        return [{"link": item.get("link"), "title": item.get("title"), "snippet": item.get("snippet")}
                for item in results if item.get("link")]


class GoogleCSEProvider(SearchProvider):
    def __init__(self, api_key: str, cse_id: str) -> None:
        self.api_key = api_key
        self.cse_id = cse_id

    def search(self, query: str, num: int = 10) -> List[Dict[str, Any]]:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": self.api_key, "cx": self.cse_id, "q": query, "num": min(num, 10)}
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        return [{"link": item.get("link"), "title": item.get("title"), "snippet": item.get("snippet")}
                for item in items if item.get("link")]


def pick_best_pdf(results: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str], float]:
    pdfs = [r for r in results if r.get("link", "").lower().endswith(".pdf")]
    if not pdfs:
        pdfs = [r for r in results if ".pdf" in r.get("link", "").lower()]
    if not pdfs:
        return None, None, 0.0
    best = None
    best_score = -1
    for rank, r in enumerate(pdfs):
        url = r.get("link", "")
        score = host_score(url) * 10 + max(0, 10 - rank)
        if score > best_score:
            best = r
            best_score = score
    return best.get("link"), best.get("title"), float(best_score)


def extract_gpc_number(url: str) -> Optional[str]:
    """
    🔢 Extrae el número de GPC del URL.
    
    Patrones soportados:
    - IMSS: guiasclinicas/049GER.pdf → "049"
    - CENETEC: IMSS-031-08/ER.pdf → "031"
    - Con guiones: 412-10/ER.pdf → "412"
    
    Returns: Número de GPC (str) o None
    """
    if not url:
        return None
    
    # Patrón 1: guiasclinicas/XXXGER.pdf o XXXGRR.pdf
    match = re.search(r'guiasclinicas/(\d+)(?:GER|GRR)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Patrón 2: IMSS-XXX-YY/ER.pdf o RR.pdf
    match = re.search(r'IMSS-(\d+)-\d+/', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Patrón 3: SS-XXX-YY/ER.pdf (Secretaría de Salud)
    match = re.search(r'SS-(\d+)-\d+/', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Patrón 4: Búsqueda flexible de número antes de GER/GRR/ER/RR
    match = re.search(r'/(\d{3,4})(?:GER|GRR|ER|RR|_)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    return None


def classify_doc_type(url: str, title: Optional[str]) -> Optional[str]:
    """
    🏷️ Clasifica documento como GER (completo) o GRR (referencia rápida).
    
    IMPORTANTE:
    - GER/ER = Guía de Evidencias y Recomendaciones (COMPLETA)
    - GRR/RR = Guía de Referencia Rápida (RESUMEN)
    
    Nomenclatura por sitio:
    - IMSS: usa GER/GRR
    - CENETEC: usa ER/RR
    """
    s = (url or "") + " " + (title or "")
    s = s.lower()
    
    # GER/ER = Evidencias (completa)
    if any(marker in s for marker in [
        " ger", "_ger", "-ger", "/ger", "ger.pdf",
        " er.pdf", "/er.pdf", "_er.pdf",
        " evidencias", "evidencia",
        "guia_de_evidencias", "evidencias_y_recomendaciones"
    ]):
        return "GER"
    
    # GRR/RR = Referencia Rápida
    if any(marker in s for marker in [
        " grr", "_grr", "-grr", "/grr", "grr.pdf",
        " rr.pdf", "/rr.pdf", "_rr.pdf",
        "referencia rapida", "referencia rápida",
        "guia_de_referencia", "referencia_rapida"
    ]):
        return "GRR"
    
    return None


def infer_complementary_url(found_url: str, found_type: str, target_type: str) -> Optional[str]:
    """
    🔗 MODO DIOS: Infiere URL complementario (GER ↔ GRR) con VALIDACIÓN de coherencia.
    
    Patrones soportados:
    - CENETEC: /ER.pdf ↔ /RR.pdf (MISMO número IMSS-XXX-YY)
    - IMSS: /XXXGER.pdf ↔ /XXXGRR.pdf (MISMO número XXX)
    
    REGLA CRÍTICA: GER y GRR deben tener el MISMO número de GPC.
    No se permite 049GER.pdf con 175GRR.pdf ❌
    
    Returns: URL inferida o None si no se puede inferir
    """
    if not found_url:
        return None
    
    url_lower = found_url.lower()
    
    # Extraer número de GPC del URL encontrado
    gpc_number = extract_gpc_number(found_url)
    
    if found_type == "GER" and target_type == "GRR":
        # Patrón 1: CENETEC /ER.pdf → /RR.pdf
        if url_lower.endswith("/er.pdf"):
            inferred = found_url[:-6] + "RR.pdf"
            # Validar que el número de GPC se mantenga
            if gpc_number and extract_gpc_number(inferred) == gpc_number:
                return inferred
            return found_url[:-6] + "RR.pdf"  # Intentar de todos modos
        
        # Patrón 2: IMSS XXXGER.pdf → XXXGRR.pdf
        if "ger.pdf" in url_lower:
            inferred = re.sub(r'GER\.pdf$', 'GRR.pdf', found_url, flags=re.IGNORECASE)
            # Validar coherencia de número
            if gpc_number and extract_gpc_number(inferred) == gpc_number:
                return inferred
            return inferred  # Si no hay número, confiar en el patrón
    
    if found_type == "GRR" and target_type == "GER":
        # Patrón 1: CENETEC /RR.pdf → /ER.pdf  
        if url_lower.endswith("/rr.pdf"):
            inferred = found_url[:-6] + "ER.pdf"
            if gpc_number and extract_gpc_number(inferred) == gpc_number:
                return inferred
            return found_url[:-6] + "ER.pdf"
        
        # Patrón 2: IMSS XXXGRR.pdf → XXXGER.pdf
        if "grr.pdf" in url_lower:
            inferred = re.sub(r'GRR\.pdf$', 'GER.pdf', found_url, flags=re.IGNORECASE)
            if gpc_number and extract_gpc_number(inferred) == gpc_number:
                return inferred
            return inferred
    
    return None


def classify_url_type(url: str) -> Optional[str]:
    """
    🏷️ Clasifica tipo de documento por URL (más confiable que contenido).
    
    CENETEC usa ER/RR, IMSS usa GER/GRR.
    
    Returns: "GER" o "GRR" o None
    """
    url_lower = url.lower()
    
    # CENETEC patterns: /ER.pdf = GER (completa), /RR.pdf = GRR (rápida)
    if url_lower.endswith("/er.pdf"):
        return "GER"
    if url_lower.endswith("/rr.pdf"):
        return "GRR"
    
    # IMSS patterns: XXXGER.pdf, XXXGRR.pdf
    if "ger.pdf" in url_lower:
        return "GER"
    if "grr.pdf" in url_lower:
        return "GRR"
    
    # Patterns in path
    if "/ger/" in url_lower or "_ger_" in url_lower or "-ger-" in url_lower:
        return "GER"
    if "/grr/" in url_lower or "_grr_" in url_lower or "-grr-" in url_lower:
        return "GRR"
    
    return None


def get_domain_priority(url: str) -> int:
    """
    Retorna prioridad del dominio (mayor = mejor).
    
    CENETEC > IMSS > otros
    """
    url_lower = url.lower()
    
    if "cenetec-difusion.com" in url_lower:
        return 100
    if "cenetec.salud.gob.mx" in url_lower:
        return 90
    if "imss.gob.mx" in url_lower:
        return 80
    if "salud.gob.mx" in url_lower:
        return 70
    
    return 50


def download_pdf(url: str, timeout: int = 25, max_bytes: int = 8 * 1024 * 1024, max_retries: int = 3) -> Optional[bytes]:
    """Download PDF with retry logic and better error handling."""
    for attempt in range(max_retries):
        try:
            # Cache by URL hash to avoid repeated downloads
            PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha1(url.encode("utf-8", errors="ignore")).hexdigest()
            cache_path = PDF_CACHE_DIR / f"{h}.pdf"
            if cache_path.exists():
                try:
                    data = cache_path.read_bytes()
                    # Validate cached PDF has proper header
                    if data[:4] == b'%PDF':
                        return data
                    else:
                        # Invalid cache, delete and retry
                        cache_path.unlink(missing_ok=True)
                except Exception:
                    pass
            
            with requests.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                content_type = (r.headers.get("Content-Type") or "").lower()
                # Accept octet-stream or pdf content types
                if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                    # Some servers mislabel; still proceed but be cautious
                    pass
                buf = io.BytesIO()
                total = 0
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        break
                    buf.write(chunk)
                    total += len(chunk)
                    if total > max_bytes:
                        break
                data = buf.getvalue()
                
                # Validate PDF header before caching
                if not data or data[:5] == b'<html' or data[:5] == b'<!DOC':
                    if attempt < max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                        continue
                    return None
                
                if data[:4] != b'%PDF':
                    if attempt < max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    return None
                
                try:
                    cache_path.write_bytes(data)
                except Exception:
                    pass
                return data
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
            return None
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            return None
    return None


def extract_title_from_first_page_ocr(data: bytes) -> Optional[str]:
    """
    Extrae el título de la primera página del PDF usando OCR avanzado.
    
    Estrategia en cascada:
    1. PyMuPDF (fitz) - Rápido, texto nativo
    2. Tesseract OCR - Para PDFs escaneados/corruptos
    
    Returns: Título extraído o None
    """
    if not data or len(data) < 4 or data[:4] != b'%PDF':
        return None
    
    # Nivel 1: PyMuPDF (rápido, funciona en 95% de casos)
    try:
        import fitz  # PyMuPDF
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            doc = fitz.open(stream=data, filetype="pdf")
            
            if len(doc) == 0:
                return None
            
            page = doc[0]  # Primera página
            
            # Método 1: Metadata del documento
            metadata = doc.metadata
            if metadata and metadata.get('title'):
                title = metadata['title'].strip()
                if len(title) > 10 and not title.isdigit():
                    return title
            
            # Método 2: Texto de la primera página
            text = page.get_text()
            if text:
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                # Buscar título en las primeras líneas (suele estar en líneas 2-10)
                title_candidates = []
                for i, line in enumerate(lines[:15]):
                    # Ignorar líneas muy cortas, números, o encabezados comunes
                    if len(line) < 10 or line.isdigit():
                        continue
                    if line.lower() in ('cenetec', 'imss', 'secretaría de salud'):
                        continue
                    
                    # Preferir líneas con palabras clave médicas
                    has_keywords = any(kw in line.lower() for kw in [
                        'diagnóstico', 'tratamiento', 'guía', 'práctica', 'clínica',
                        'evidencias', 'recomendaciones', 'prevención', 'manejo'
                    ])
                    
                    # Score: longitud + keywords
                    score = len(line)
                    if has_keywords:
                        score += 50
                    
                    title_candidates.append((score, i, line))
                
                # Ordenar por score y tomar el mejor
                if title_candidates:
                    title_candidates.sort(reverse=True)
                    return title_candidates[0][2]
                
                # Fallback: primera línea significativa
                for line in lines[:10]:
                    if len(line) > 15:
                        return line
    except Exception:
        pass
    
    # Nivel 2: Tesseract OCR (solo si PyMuPDF falló o no hay texto)
    try:
        import fitz  # PyMuPDF para renderizar
        import pytesseract
        from PIL import Image
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            doc = fitz.open(stream=data, filetype="pdf")
            
            if len(doc) == 0:
                return None
            
            page = doc[0]
            
            # Renderizar primera página a imagen de alta calidad
            pix = page.get_pixmap(dpi=300)  # 300 DPI para mejor OCR
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Recortar solo el área del título (tercio superior)
            width, height = img.size
            title_area = img.crop((0, 0, width, height // 3))
            
            # OCR con idioma español
            text = pytesseract.image_to_string(title_area, lang='spa', config='--psm 6')
            
            if text:
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                # Buscar línea más larga (probablemente el título)
                title_candidates = [(len(l), l) for l in lines if len(l) > 10]
                if title_candidates:
                    title_candidates.sort(reverse=True)
                    return title_candidates[0][1]
                
                # Fallback: primera línea válida
                for line in lines[:5]:
                    if len(line) > 10:
                        return line
    except Exception:
        pass
    
    return None


def extract_pdf_text_first_pages(data: bytes, max_pages: int = 2, quiet: bool = True) -> str:
    """Extract text from PDF with better error handling and quiet mode by default."""
    # Validate PDF header first
    if not data or len(data) < 4:
        return ""
    
    # Quick check for valid PDF
    if data[:4] != b'%PDF':
        return ""
    
    # Try PyPDF2 (pypdf) first - it's faster
    try:
        import pypdf  # type: ignore
        
        # Suppress warnings during extraction
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reader = pypdf.PdfReader(io.BytesIO(data), strict=False)
            texts: List[str] = []
            
            # Extract text from first N pages
            page_count = min(len(reader.pages), max_pages)
            for i in range(page_count):
                try:
                    page_text = reader.pages[i].extract_text() or ""
                    if page_text:
                        texts.append(page_text)
                except Exception:
                    continue
            
            # Try to get metadata title
            try:
                if hasattr(reader, 'metadata') and reader.metadata:
                    meta_title = reader.metadata.title or ""
                    if meta_title:
                        texts.insert(0, str(meta_title))
            except Exception:
                pass
            
            if texts:
                return "\n".join(texts)
    except Exception:
        pass
    
    # Fallback: pdfminer.six (slower but more robust)
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            text = extract_text(io.BytesIO(data), maxpages=max_pages)
            return text or ""
    except Exception:
        return ""
    
    return ""


def normalize_text(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    return s.strip()


def title_match_score(gpc_title: str, doc_text: str) -> float:
    if not doc_text:
        return 0.0
    t_norm = normalize_text(gpc_title)
    d_norm = normalize_text(doc_text[:5000])  # limit cost
    # 1) token overlap score
    tokens = [w for w in re.split(r"[^a-z0-9]+", t_norm) if len(w) >= 4]
    if not tokens:
        return 0.0
    hits = sum(1 for w in tokens if w in d_norm)
    overlap = hits / max(1, len(tokens))
    # 2) fuzzy ratio on a trimmed window: try to find a line-like title
    lines = [ln.strip() for ln in d_norm.split("\n") if ln.strip()]
    best_ratio = 0.0
    for ln in lines[:30]:  # examine first 30 lines
        ratio = difflib.SequenceMatcher(None, t_norm, ln).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
    # Weighted combination
    return 0.6 * overlap + 0.4 * best_ratio


class SemanticValidator:
    def __init__(self, model_name: str = "paraphrase-multilingual-mpnet-base-v2", device: str = "auto", batch_size: int = 32, enable_classification: bool = False) -> None:
        """
        🔥 UPGRADED: Modelo más potente (mpnet) + clasificación GER/GRR opcional
        
        Args:
            model_name: Modelo para embeddings (por defecto: paraphrase-multilingual-mpnet-base-v2)
            device: 'cuda', 'cpu', o 'auto'
            batch_size: Tamaño de batch para GPU
            enable_classification: Si True, clasifica documentos como GER/GRR
        """
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.enable_classification = enable_classification
        self._model = None
        self._torch = None
        self._np = None
        self._actual_device = None

    def ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            import numpy as np
            dev = None
            if self.device == "cuda" or (self.device == "auto" and torch.cuda.is_available()):
                dev = "cuda"
                print(f"[GPU] CUDA disponible: {torch.cuda.get_device_name(0)}")
            else:
                dev = "cpu"
                print(f"[CPU] CUDA no disponible, usando CPU")
            self._model = SentenceTransformer(self.model_name, device=dev)
            self._torch = torch
            self._np = np
            self._actual_device = dev
            print(f"[SemanticValidator] Modelo cargado en {dev}")
            return True
        except Exception as e:
            print(f"[SemanticValidator] Error cargando modelo: {e}")
            return False

    def similarity(self, title: str, candidates: List[str]) -> float:
        if not self.ensure_loaded():
            return 0.0
        # Embed title and candidate lines
        model = self._model
        import numpy as np
        vec_t = model.encode([title], normalize_embeddings=True, batch_size=self.batch_size, show_progress_bar=False)[0]
        vec_c = model.encode(candidates, normalize_embeddings=True, batch_size=self.batch_size, show_progress_bar=False)
        # cosine similarity
        sims = (vec_c @ vec_t)
        return float(np.max(sims)) if len(candidates) else 0.0
    
    def classify_document_type(self, text: str) -> Tuple[str, float]:
        """
        🤖 Clasifica documento como GER, GRR o UNKNOWN usando keywords ponderados.
        
        Returns:
            (tipo, confianza) donde tipo='GER'|'GRR'|'UNKNOWN' y confianza=[0.0-1.0]
        """
        if not text:
            return ("UNKNOWN", 0.0)
        
        text_lower = text.lower()
        
        # Keywords ponderados (basado en validate_gpc_intelligent.py)
        ger_keywords = {
            'evidencias': 3.0,
            'recomendaciones': 3.0,
            'metodología': 2.0,
            'busqueda': 1.5,
            'calidad de la evidencia': 3.0,
            'grado de recomendación': 2.5,
            'referencias bibliográficas': 2.0,
            'algoritmo de manejo': 1.0,
            'niveles de evidencia': 2.5,
        }
        
        grr_keywords = {
            'referencia rapida': 4.0,
            'algoritmo': 2.5,
            'diagrama de flujo': 3.0,
            'guia rapida': 3.0,
            'flujograma': 2.5,
            'cuadro de decisión': 2.0,
            'quick reference': 2.0,
        }
        
        # Calcular scores
        ger_score = sum(weight for keyword, weight in ger_keywords.items() if keyword in text_lower)
        grr_score = sum(weight for keyword, weight in grr_keywords.items() if keyword in text_lower)
        
        # Heurísticas adicionales (longitud)
        text_len = len(text)
        if text_len < 10000:
            grr_score += 1.0  # GRRs suelen ser más cortos
        elif text_len > 30000:
            ger_score += 1.0  # GERs suelen ser más largos
        
        # Determinar tipo
        total_score = ger_score + grr_score
        if total_score == 0:
            return ("UNKNOWN", 0.0)
        
        if ger_score > grr_score:
            confidence = ger_score / total_score
            return ("GER", confidence)
        elif grr_score > ger_score:
            confidence = grr_score / total_score
            return ("GRR", confidence)
        else:
            return ("UNKNOWN", 0.5)
    
    def batch_similarity(self, titles: List[str], all_candidates: List[List[str]]) -> List[float]:
        """
        Batch process multiple title-candidates pairs for GPU efficiency.
        Returns max similarity for each title.
        """
        if not self.ensure_loaded():
            return [0.0] * len(titles)
        model = self._model
        import numpy as np
        # Encode all titles at once
        title_vecs = model.encode(titles, normalize_embeddings=True, batch_size=self.batch_size, show_progress_bar=False)
        results = []
        for i, (title_vec, candidates) in enumerate(zip(title_vecs, all_candidates)):
            if not candidates:
                results.append(0.0)
                continue
            cand_vecs = model.encode(candidates, normalize_embeddings=True, batch_size=self.batch_size, show_progress_bar=False)
            sims = cand_vecs @ title_vec
            results.append(float(np.max(sims)))
        return results
    
    def extract_text_smart(self, pdf_bytes: bytes) -> Tuple[str, List[str]]:
        """
        Extrae texto del PDF usando estrategia en cascada:
        1. PyMuPDF (nativo, rápido)
        2. Tesseract OCR (si falla o texto muy corto)
        
        🔥 MEJORADO: Detecta si texto es seleccionable. Si no lo es, usa OCR directamente.
        
        Returns: (texto_completo, líneas_título_candidatas)
        """
        if not pdf_bytes or len(pdf_bytes) < 4:
            return ("", [])
        
        # Nivel 1: PyMuPDF (rápido, funciona en 95% de casos)
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if len(doc) == 0:
                return ("", [])
            
            # Extraer primera página
            page = doc[0]
            text = page.get_text()
            
            # 🔥 MEJORA: Detectar si hay texto seleccionable
            text_length = len(text.strip())
            has_selectable_text = text_length > 50  # Al menos 50 caracteres
            
            if has_selectable_text:
                # Texto nativo extraído correctamente
                doc.close()
                
                # Extraer candidatos de título (líneas 3-25)
                lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                
                # Filtrar headers comunes
                skip_patterns = [
                    "gobierno", "república", "secretaría", "cenetec", "imss", 
                    "salud", "página", "fecha", "evidencias", "guía"
                ]
                
                candidates = []
                for i, line in enumerate(lines[2:25], start=2):  # Líneas 3-25
                    if len(line) < 15 or len(line) > 200:
                        continue
                    
                    # Evitar headers
                    line_lower = line.lower()
                    if any(pattern in line_lower for pattern in skip_patterns):
                        if len(line) < 30:  # Si es corta y tiene patrón, skip
                            continue
                    
                    candidates.append(line)
                    
                    # Combinar con siguiente línea (títulos multilínea)
                    if i + 1 < len(lines):
                        combined = line + " " + lines[i + 1].strip()
                        if len(combined) < 200:
                            candidates.append(combined)
                
                # Mantener top 20
                candidates = candidates[:20]
                
                return (text, candidates)
            else:
                # 🔥 TEXTO NO SELECCIONABLE: Usar OCR directamente
                print("      [OCR] Texto no seleccionable, usando Tesseract...")
                doc.close()
                # Continuar a Nivel 2 (OCR)
        
        except Exception as e:
            pass
        
        # Nivel 2: Tesseract OCR (PDFs escaneados o sin texto seleccionable)
        try:
            import fitz  # PyMuPDF para renderizar
            import pytesseract
            from PIL import Image
            import io
            
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if len(doc) == 0:
                return ("", [])
            
            # Renderizar primera página como imagen de ALTA calidad
            page = doc[0]
            pix = page.get_pixmap(dpi=300)  # 300 DPI para mejor OCR
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))
            
            # OCR con español
            text = pytesseract.image_to_string(img, lang="spa", config="--psm 6")
            doc.close()
            
            if text and len(text.strip()) > 50:
                lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                candidates = [ln for ln in lines[2:25] if 15 < len(ln) < 200][:20]
                print(f"      [OCR] Extraídos {len(candidates)} candidatos de título")
                return (text, candidates)
        
        except Exception as e:
            print(f"      [OCR] Error: {e}")
            pass
        
        return ("", [])
    
    def validate_pdf(self, pdf_bytes: bytes, expected_title: str, expected_type: str, 
                     url_type: Optional[str] = None) -> Tuple[bool, float, str, float]:
        """
        Valida PDF con OCR + AI classification.
        
        Args:
            pdf_bytes: Bytes del PDF
            expected_title: Título esperado del GPC
            expected_type: "GER" o "GRR" esperado
            url_type: Tipo detectado del URL (priority sobre contenido)
        
        Returns: (es_válido, confianza, tipo_detectado, similitud_título)
        """
        text, title_candidates = self.extract_text_smart(pdf_bytes)
        
        if not text:
            return (False, 0.0, "UNKNOWN", 0.0)
        
        # 1. Similitud de título
        title_similarity = self.similarity(expected_title, title_candidates) if title_candidates else 0.0
        
        # 2. Clasificación de tipo
        if url_type:
            # URL type tiene prioridad (95% de confianza)
            detected_type = url_type
            type_confidence = 0.95
        else:
            # Clasificación por contenido
            detected_type, type_confidence = self.classify_document_type(text)
        
        # 3. Validación
        type_match = (detected_type == expected_type)
        
        # Confianza combinada
        confidence = 0.6 * title_similarity + 0.4 * type_confidence
        
        # Umbral: 35% para búsqueda normal
        is_valid = title_similarity >= 0.35 and type_match
        
        return (is_valid, confidence, detected_type, title_similarity)


def http_head_status(url: str, timeout: int = 20) -> Optional[int]:
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        return r.status_code
    except Exception:
        return None


def build_queries(title: str) -> Tuple[str, str]:
    base = title
    ger_syn = "\"Guía de Evidencias y Recomendaciones\" OR \"Guia de Evidencias y Recomendaciones\" OR GER"
    grr_syn = "\"Guía de Referencia Rápida\" OR \"Guia de Referencia Rapida\" OR GRR"
    site_bias = (
        "(site:cenetec-difusion.com OR site:cenetec.salud.gob.mx OR site:imss.gob.mx OR site:salud.gob.mx OR "
        "site:gob.mx OR site:issste.gob.mx OR site:csg.gob.mx OR site:insp.mx)"
    )
    q_ger = f"{base} {ger_syn} filetype:pdf {site_bias}"
    q_grr = f"{base} {grr_syn} filetype:pdf {site_bias}"
    return q_ger, q_grr


def choose_provider() -> SearchProvider:
    """
    🔄 PRIORIDAD: Google CSE > SerpAPI > Serper
    
    Google CSE es más confiable y tiene mejor cuota.
    """
    g_key = os.environ.get("GOOGLE_API_KEY")
    g_cse = os.environ.get("GOOGLE_CSE_ID")
    serpapi_key = os.environ.get("SERPAPI_API_KEY")
    serper_key = os.environ.get("SERPER_API_KEY")
    
    # ✅ PRIORIDAD 1: Google CSE (mejor cuota, más confiable)
    if g_key and g_cse:
        return GoogleCSEProvider(g_key, g_cse)
    
    # Fallbacks
    if serpapi_key:
        return SerpAPIProvider(serpapi_key)
    if serper_key:
        return SerperProvider(serper_key)
    
    raise RuntimeError(
        "No search provider configured. Set GOOGLE_API_KEY+GOOGLE_CSE_ID, SERPAPI_API_KEY, or SERPER_API_KEY.")


def load_temario_text() -> str:
    if not TEMARIO_MD.exists():
        raise FileNotFoundError(f"Temario file not found at {TEMARIO_MD}")
    return TEMARIO_MD.read_text(encoding="utf-8")


def load_imss_catalog() -> Optional[List[Dict[str, Any]]]:
    """
    Carga el catálogo IMSS scrapeado desde el caché.
    
    Returns: Lista de entradas IMSS o None si no existe/expiró
    """
    imss_cache = OUT_DIR / "imss_catalog_cache.json"
    
    if not imss_cache.exists():
        print("⚠️  Catálogo IMSS no encontrado. Ejecuta: python scripts/scrape_imss_catalog.py")
        return None
    
    try:
        import datetime
        data = json.loads(imss_cache.read_text(encoding='utf-8'))
        
        # Verificar edad del caché
        cache_time = datetime.datetime.fromisoformat(data['timestamp'])
        age = datetime.datetime.now() - cache_time
        
        if age.days > 7:
            print(f"⚠️  Caché IMSS antiguo ({age.days} días). Considera re-ejecutar scraper.")
        else:
            print(f"✓ Catálogo IMSS cargado ({data['total']} GPCs, {age.days} días de antigüedad)")
        
        return data.get('entries', [])
    except Exception as e:
        print(f"⚠️  Error leyendo catálogo IMSS: {e}")
        return None


def find_gpc_smart(title: str, doc_type: str, validator: SemanticValidator, provider: SearchProvider, imss_catalog: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    """
    🎯 ESTRATEGIA SMART VALIDADA (desde find_gpc_smart_validated.py):
    1. Buscar SOLO en CENETEC primero (site:cenetec-difusion.com)
    2. Si no encuentra, buscar en IMSS (site:imss.gob.mx)
    3. Validar con OCR + AI (GPU-accelerated)
    4. Fallback a IMSS cache si todo falla
    5. NUNCA mezclar dominios
    
    Args:
        title: Título del GPC a buscar
        doc_type: "GER" o "GRR"
        validator: Instancia de SemanticValidator con modelo cargado
        provider: Proveedor de búsqueda
        imss_catalog: Catálogo IMSS opcional para fallback
    
    Returns: URL del PDF o None
    """
    # Construir query con PRIORIDAD CENETEC
    doc_keywords = {
        "GER": '"Guía de Evidencias y Recomendaciones" OR GER OR ER',
        "GRR": '"Guía de Referencia Rápida" OR GRR OR RR'
    }
    
    # PASO 1: Buscar SOLO en CENETEC primero
    cenetec_domains = ["cenetec-difusion.com", "cenetec.salud.gob.mx"]
    cenetec_restriction = " OR ".join([f"site:{d}" for d in cenetec_domains])
    query = f'{title} {doc_keywords[doc_type]} filetype:pdf ({cenetec_restriction})'
    
    # Buscar en CENETEC
    results = []
    try:
        results = provider.search(query, num=10)
    except Exception as e:
        print(f"    ❌ Error búsqueda CENETEC: {e}")
        # NO FALLBACK - Si falla CENETEC, mostramos error y seguimos
    
    # PASO 2: Si no hay resultados en CENETEC, buscar en IMSS
    if not results:
        imss_query = f'{title} {doc_keywords[doc_type]} filetype:pdf site:imss.gob.mx'
        try:
            results = provider.search(imss_query, num=10)
            if results:
                print(f"    🔄 Fallback a IMSS (no encontrado en CENETEC)")
        except Exception as e:
            print(f"    ❌ Error búsqueda IMSS: {e}")
    
    # PASO 3: Solo si NO hay resultados, usar IMSS cache como último recurso
    if not results and imss_catalog:
        imss_match = find_in_imss_catalog(title, imss_catalog)
        if imss_match:
            url_key = 'ger_url' if doc_type == "GER" else 'grr_url'
            url = imss_match.get(url_key)
            if url:
                print(f"    💾 IMSS cache: {url[-50:]}")
                return url
        return None
    
    # Filtrar y validar candidatos
    candidates: List[Tuple[float, str, int]] = []  # (confidence, url, domain_priority)
    
    for result in results[:8]:  # Limitar para no saturar
        url = result.get("link", "")
        
        if not url or not url.lower().endswith(".pdf"):
            continue
        
        if not is_allowed_host(url):
            continue
        
        # Clasificar por URL (más confiable)
        url_type = classify_url_type(url)
        
        # Early filter: skip si URL claramente del tipo incorrecto
        if url_type and url_type != doc_type:
            continue
        
        # Descargar
        pdf_bytes = download_pdf(url)
        if not pdf_bytes or len(pdf_bytes) < 1000:
            continue
        
        # Validar con OCR + AI
        is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
            pdf_bytes, title, doc_type, url_type
        )
        
        if not is_valid:
            continue
        
        domain_priority = get_domain_priority(url)
        candidates.append((confidence, url, domain_priority))
    
    if not candidates:
        # Fallback a IMSS cache
        if imss_catalog:
            imss_match = find_in_imss_catalog(title, imss_catalog)
            if imss_match:
                url_key = 'ger_url' if doc_type == "GER" else 'grr_url'
                url = imss_match.get(url_key)
                if url:
                    print(f"    💾 Fallback IMSS: {url[-50:]}")
                    return url
        return None
    
    # Seleccionar mejor (prioridad: dominio > confianza)
    candidates.sort(key=lambda x: (x[2], x[0]), reverse=True)
    best_conf, best_url, best_domain = candidates[0]
    
    print(f"    ✅ {best_url[-50:]} (conf={best_conf:.1%}, domain={best_domain})")
    
    return best_url


def find_in_imss_catalog(gpc_title: str, imss_catalog: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Busca un GPC en el catálogo IMSS por similitud de título.
    
    Args:
        gpc_title: Título del GPC a buscar
        imss_catalog: Lista de entradas del catálogo IMSS
    
    Returns: Entrada IMSS con mejor match o None
    """
    gpc_norm = normalize_text(gpc_title)
    
    best_match = None
    best_score = 0.0
    
    for entry in imss_catalog:
        entry_title = entry.get('title', '')
        if not entry_title:
            continue
        
        entry_norm = normalize_text(entry_title)
        
        # Similitud de secuencia
        score = difflib.SequenceMatcher(None, gpc_norm, entry_norm).ratio()
        
        if score > best_score:
            best_score = score
            best_match = entry
    
    # Threshold: 70% de similitud para considerar match
    if best_score >= 0.7:
        return best_match
    
    return None


def write_outputs(rows: List[GPCLinkResult], incremental: bool = False) -> None:
    """
    Escribe resultados en CSV, JSON y Markdown.
    
    Args:
        rows: Lista de resultados
        incremental: Si True, guarda inmediatamente (para no perder progreso)
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    
    # CSV
    with OUT_CSV.open("w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "title", "query_ger", "query_grr", "ger_url", "grr_url",
            "ger_source", "grr_source", "ger_status", "grr_status",
            "ger_confidence", "grr_confidence",
        ])
        for r in rows:
            writer.writerow([
                r.title, r.query_ger, r.query_grr, r.ger_url or "", r.grr_url or "",
                r.ger_source or "", r.grr_source or "", r.ger_status or "", r.grr_status or "",
                f"{r.ger_confidence:.1f}", f"{r.grr_confidence:.1f}",
            ])
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in rows], f, ensure_ascii=False, indent=2)
    lines = []
    lines.append("# Enlaces GER/GRR de GPC (México: CENETEC/IMSS preferidos)\n")
    import datetime as _dt
    lines.append(f"Generado: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append(
        "Criterio: sólo dominios oficiales mexicanos (cenetec, imss, salud, gob.mx, issste, csg, insp).\n"
    )
    for r in rows:
        lines.append(f"\n## {r.title}")
        if r.ger_url:
            lines.append(f"- GER: {r.ger_url} (conf {r.ger_confidence:.1f})")
        else:
            lines.append("- GER: No encontrado")
        if r.grr_url:
            lines.append(f"- GRR: {r.grr_url} (conf {r.grr_confidence:.1f})")
        else:
            lines.append("- GRR: No encontrado")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main(argv: List[str]) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Find GER/GRR links (MX official domains, CENETEC/IMSS preferred)")
    parser.add_argument("--filter", dest="subset", help="Substring to filter titles (case-insensitive)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of titles (debug)")
    parser.add_argument("--sleep", type=float, default=0.8, help="Sleep seconds between queries to be polite")
    parser.add_argument("--no-head", action="store_true", help="Skip HTTP HEAD checks")
    parser.add_argument("--allow-mx-mirrors", action="store_true", help="Si no hay oficial, permite PDFs en dominios .mx")
    parser.add_argument("--allow-any-domain", action="store_true", help="No limitar por dominio (no recomendado)")
    parser.add_argument("--max-results", type=int, default=6, help="Resultados por consulta para ahorrar tokens (default 6)")
    parser.add_argument("--only-missing", action="store_true", help="Buscar sólo títulos con GER o GRR faltantes en el JSON existente")
    parser.add_argument("--in-json", default=str(OUT_JSON), help="Ruta al JSON existente (por defecto data/gpc_links.json)")
    parser.add_argument("--no-validate-pdf", action="store_true", help="No validar el contenido del PDF contra el título (más rápido, menos preciso)")
    parser.add_argument("--min-title-match", type=float, default=0.35, help="Umbral mínimo de coincidencia título<->PDF (0-1)")
    parser.add_argument("--use-embeddings", action="store_true", help="Usar modelos de oraciones (GPU si disponible) para validar coincidencia semántica")
    parser.add_argument("--embedding-model", default="paraphrase-multilingual-mpnet-base-v2", help="Modelo de sentence-transformers (por defecto: mpnet, más potente)")
    parser.add_argument("--embedding-device", default="auto", choices=["auto","cpu","cuda"], help="Dispositivo para embeddings")
    parser.add_argument("--embedding-batch-size", type=int, default=32, help="Batch size para embeddings (más grande = más GPU usage)")
    parser.add_argument("--max-embed-lines", type=int, default=25, help="Máximo de líneas del PDF para la comparación semántica")
    parser.add_argument("--enable-classification", action="store_true", help="🤖 Activar clasificación IA de GER/GRR (requiere --use-embeddings)")
    parser.add_argument("--aggressive", action="store_true", help="Modo agresivo: más reintentos, más resultados, no se rinde fácil")
    parser.add_argument("--use-scraping", action="store_true", help="Usar scraping IMSS como base (gratis, 198 GPCs), luego buscar en CENETEC para actualizar/complementar")
    parser.add_argument("--prefer-cenetec", action="store_true", default=True, help="Si existe en IMSS y CENETEC, preferir CENETEC (más actualizado)")
    parser.add_argument("--use-smart-validation", action="store_true", default=True, help="🔥 Usar estrategia SMART validada (OCR + AI + GPU). Recomendado para máxima calidad.")
    args = parser.parse_args(argv)

    text = load_temario_text()
    titles = extract_gpc_titles(text, args.subset)
    if args.limit:
        titles = titles[: args.limit]
    print(f"Found {len(titles)} GPC titles to search.")

    provider = choose_provider()

    # Load existing JSON if present to skip complete rows
    existing: Dict[str, Dict[str, Any]] = {}
    in_json_path = Path(args.in_json)
    if in_json_path.exists():
        try:
            existing_list = json.loads(in_json_path.read_text(encoding="utf-8"))
            for item in existing_list:
                if isinstance(item, dict) and "title" in item:
                    existing[item["title"]] = item
        except Exception:
            pass

    # Initialize semantic validator ONCE before the loop if needed
    global_sem_validator: Optional[SemanticValidator] = None
    
    # 🔥 SMART VALIDATION: Force embeddings + classification if smart validation enabled
    if args.use_smart_validation:
        args.use_embeddings = True
        args.enable_classification = True
        print("\n🔥 ESTRATEGIA SMART ACTIVADA: Google + OCR + AI Classifier")
        print("=" * 80)
        print("✓ OCR: Tesseract + PyMuPDF")
        print("✓ GPU: Sentence-transformers (semantic similarity)")
        print("✓ AI: Clasificación GER/GRR automática")
        print("✓ Prioridad: CENETEC > IMSS")
        print("=" * 80 + "\n")
    
    if args.use_embeddings or args.use_smart_validation:
        # 🔥 UPGRADED: Activate AI classification if requested
        enable_ai_classification = args.enable_classification or args.use_smart_validation
        global_sem_validator = SemanticValidator(
            args.embedding_model, 
            args.embedding_device, 
            args.embedding_batch_size,
            enable_classification=enable_ai_classification
        )
        # Preload model once at the start
        if global_sem_validator.ensure_loaded():
            print(f"✅ Modelo '{args.embedding_model}' cargado en {global_sem_validator._actual_device}")
            if enable_ai_classification:
                print(f"🤖 Clasificación IA activada (GER/GRR automático)")
            print("")
        else:
            print(f"⚠️  No se pudo cargar el modelo, continuando sin validación semántica\n")
            global_sem_validator = None

    # Load IMSS catalog (always try if smart validation OR scraping enabled)
    imss_catalog = None
    if args.use_scraping or args.use_smart_validation:
        if args.use_smart_validation:
            print("📦 Cargando catálogo IMSS para fallback...")
        else:
            print("\n🕷️  MODO HÍBRIDO ACTIVADO: Scraping IMSS + Búsqueda CENETEC")
            print("=" * 80)
        
        imss_catalog = load_imss_catalog()
        
        if imss_catalog:
            if not args.use_smart_validation:
                print(f"✓ {len(imss_catalog)} GPCs disponibles en catálogo IMSS")
                print("📌 Estrategia:")
                print("   1. Buscar en IMSS (gratis, rápido)")
                print("   2. Buscar en CENETEC para faltantes (prioridad máxima)")
                print("   3. REEMPLAZAR IMSS → CENETEC si ambos existen (más actualizado)")
                print("=" * 80 + "\n")
        else:
            if not args.use_smart_validation:
                print("⚠️  Scraping IMSS no disponible, usando solo búsqueda API\n")

    # 🔄 RESUME: Cargar resultados existentes para evitar reprocesar
    rows: List[GPCLinkResult] = []
    processed_titles = set()
    
    if OUT_JSON.exists():
        try:
            existing_data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
            for item in existing_data:
                # Convertir dict a GPCLinkResult
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
                processed_titles.add(result.title)
            
            if processed_titles:
                print(f"🔄 RESUMIENDO: {len(processed_titles)} GPCs ya procesados, continuando desde ahí...\n")
        except Exception as e:
            print(f"⚠️  No se pudo cargar progreso anterior: {e}\n")
    
    for i, title in enumerate(titles, 1):
        # Skip if already processed
        if title in processed_titles:
            continue
        
        q_ger, q_grr = build_queries(title)
        row = GPCLinkResult(title=title, query_ger=q_ger, query_grr=q_grr)

        # 🔥 SMART VALIDATION PATH: Simplified high-quality search
        if args.use_smart_validation and global_sem_validator:
            print(f"\n[{i}/{len(titles)}] {title}")
            
            # Search GER
            print("  🔍 Buscando GER...")
            ger_url = find_gpc_smart(title, "GER", global_sem_validator, provider, imss_catalog)
            
            # Search GRR
            print("  🔍 Buscando GRR...")
            grr_url = find_gpc_smart(title, "GRR", global_sem_validator, provider, imss_catalog)
            
            # 🔗 INFERENCIA AGRESIVA: Si uno está en CENETEC, el otro DEBE estar en CENETEC
            if ger_url and grr_url:
                ger_domain = get_domain_priority(ger_url)
                grr_domain = get_domain_priority(grr_url)
                
                # Si dominios diferentes, priorizar CENETEC
                if ger_domain != grr_domain:
                    if ger_domain >= 90:  # GER es CENETEC
                        # Inferir GRR desde GER (CENETEC)
                        inferred_grr = infer_complementary_url(ger_url, "GER", "GRR")
                        if inferred_grr:
                            print(f"  🔄 Coherencia: Reemplazando GRR IMSS con CENETEC inferido")
                            pdf_bytes = download_pdf(inferred_grr)
                            if pdf_bytes and len(pdf_bytes) > 1000:
                                text, title_cands = global_sem_validator.extract_text_smart(pdf_bytes)
                                if text:
                                    title_sim = global_sem_validator.similarity(title, title_cands) if title_cands else 0.0
                                    if title_sim >= 0.20:  # Umbral muy bajo para coherencia
                                        grr_url = inferred_grr
                                        print(f"    ✅ GRR CENETEC inferido (sim={title_sim:.1%})")
                    
                    elif grr_domain >= 90:  # GRR es CENETEC
                        # Inferir GER desde GRR (CENETEC)
                        inferred_ger = infer_complementary_url(grr_url, "GRR", "GER")
                        if inferred_ger:
                            print(f"  🔄 Coherencia: Reemplazando GER IMSS con CENETEC inferido")
                            pdf_bytes = download_pdf(inferred_ger)
                            if pdf_bytes and len(pdf_bytes) > 1000:
                                text, title_cands = global_sem_validator.extract_text_smart(pdf_bytes)
                                if text:
                                    title_sim = global_sem_validator.similarity(title, title_cands) if title_cands else 0.0
                                    if title_sim >= 0.20:
                                        ger_url = inferred_ger
                                        print(f"    ✅ GER CENETEC inferido (sim={title_sim:.1%})")
            
            # Try inference if one is missing
            if ger_url and not grr_url:
                inferred_grr = infer_complementary_url(ger_url, "GER", "GRR")
                if inferred_grr:
                    print(f"  🔗 Infiriendo GRR desde GER: {inferred_grr[-50:]}")
                    # Validate inferred URL
                    pdf_bytes = download_pdf(inferred_grr)
                    if pdf_bytes and len(pdf_bytes) > 1000:
                        text, title_cands = global_sem_validator.extract_text_smart(pdf_bytes)
                        if text:
                            title_sim = global_sem_validator.similarity(title, title_cands) if title_cands else 0.0
                            # Lower threshold for inferred (25% vs 35%)
                            if title_sim >= 0.25:
                                grr_url = inferred_grr
                                print(f"    ✅ GRR inferido válido (sim={title_sim:.1%})")
                            else:
                                print(f"    ❌ GRR inferido rechazado (sim={title_sim:.1%} < 25%)")
            
            elif grr_url and not ger_url:
                inferred_ger = infer_complementary_url(grr_url, "GRR", "GER")
                if inferred_ger:
                    print(f"  🔗 Infiriendo GER desde GRR: {inferred_ger[-50:]}")
                    pdf_bytes = download_pdf(inferred_ger)
                    if pdf_bytes and len(pdf_bytes) > 1000:
                        text, title_cands = global_sem_validator.extract_text_smart(pdf_bytes)
                        if text:
                            title_sim = global_sem_validator.similarity(title, title_cands) if title_cands else 0.0
                            if title_sim >= 0.25:
                                ger_url = inferred_ger
                                print(f"    ✅ GER inferido válido (sim={title_sim:.1%})")
                            else:
                                print(f"    ❌ GER inferido rechazado (sim={title_sim:.1%} < 25%)")
            
            # Store results
            row.ger_url = ger_url
            row.grr_url = grr_url
            row.ger_source = "Smart+OCR+AI" if ger_url else None
            row.grr_source = "Smart+OCR+AI" if grr_url else None
            row.ger_confidence = 85.0 if ger_url else 0.0
            row.grr_confidence = 85.0 if grr_url else 0.0
            
            # Summary
            status = []
            if ger_url:
                status.append("✅ GER")
            else:
                status.append("❌ GER")
            if grr_url:
                status.append("✅ GRR")
            else:
                status.append("❌ GRR")
            print(f"  📊 Resultado: {' | '.join(status)}")
            
            rows.append(row)
            
            # 💾 GUARDADO INCREMENTAL: Guardar después de cada GPC
            write_outputs(rows, incremental=True)
            
            # Sleep to be polite
            if i < len(titles):
                time.sleep(args.sleep)
            
            continue  # Skip legacy path
        
        # LEGACY PATH: Original complex search logic
        # STEP 1: Try IMSS catalog first if scraping enabled
        imss_ger_url = None
        imss_grr_url = None
        found_in_imss = False
        
        if imss_catalog:
            imss_match = find_in_imss_catalog(title, imss_catalog)
            if imss_match:
                imss_ger_url = imss_match.get('ger_url')
                imss_grr_url = imss_match.get('grr_url')
                found_in_imss = bool(imss_ger_url or imss_grr_url)
                
                if found_in_imss:
                    print(f"[{i}/{len(titles)}] {title}")
                    print(f"  🕷️  Encontrado en IMSS (scraping):")
                    if imss_ger_url:
                        print(f"    GER: {imss_ger_url[:80]}...")
                    if imss_grr_url:
                        print(f"    GRR: {imss_grr_url[:80]}...")
                    
                    # Temporarily store IMSS results
                    row.ger_url = imss_ger_url
                    row.grr_url = imss_grr_url
                    row.ger_source = "IMSS_SCRAPING" if imss_ger_url else None
                    row.grr_source = "IMSS_SCRAPING" if imss_grr_url else None
                    row.ger_confidence = 0.85 if imss_ger_url else 0.0  # High confidence for scraping
                    row.grr_confidence = 0.85 if imss_grr_url else 0.0

        # Skip if only-missing and both present in existing and allowed
        ex = existing.get(title)
        if args.only_missing and ex:
            ex_ger = ex.get("ger_url")
            ex_grr = ex.get("grr_url")
            if ex_ger and is_allowed_host(ex_ger) and ex_grr and is_allowed_host(ex_grr):
                # Check if we should update with IMSS (only if prefer-cenetec is False)
                if not args.prefer_cenetec or not found_in_imss:
                    row.ger_url = ex_ger
                    row.grr_url = ex_grr
                    row.ger_source = ex.get("ger_source")
                    row.grr_source = ex.get("grr_source")
                    row.ger_confidence = float(ex.get("ger_confidence", 0.0) or 0.0)
                    row.grr_confidence = float(ex.get("grr_confidence", 0.0) or 0.0)
                    rows.append(row)
                    print(f"[{i}/{len(titles)}] {title}\n  SKIP: ambos enlaces existentes (oficiales)")
                    continue

        # STEP 2: CENETEC Search (API) - Search if:
        # a) No IMSS results found, OR
        # b) prefer-cenetec flag is True (will replace IMSS if both exist)
        cenetec_ger_results = []
        cenetec_grr_results = []
        
        should_search_cenetec = (
            not found_in_imss or  # Missing in IMSS
            (found_in_imss and args.prefer_cenetec)  # Have IMSS but want CENETEC too
        )
        
        if should_search_cenetec:
            if not found_in_imss:
                print(f"[{i}/{len(titles)}] {title}")
                print(f"  🔍 No encontrado en IMSS, buscando en CENETEC...")
            else:
                print(f"  🔄 Buscando también en CENETEC (prefer-cenetec activo)...")
            
            # Search both queries with reduced results
            try:
                cenetec_ger_results = provider.search(q_ger, num=args.max_results)
            except Exception as e:
                print(f"  ❌ Error searching GER for '{title}': {e}")
                cenetec_ger_results = []
            try:
                cenetec_grr_results = provider.search(q_grr, num=args.max_results)
            except Exception as e:
                print(f"  ❌ Error searching GRR for '{title}': {e}")
                cenetec_grr_results = []
        
        # Combine CENETEC results for validation
        ger_results = cenetec_ger_results
        grr_results = cenetec_grr_results

        # Combine, filter allowed hosts and PDFs, then classify
        combined = []
        for r in (ger_results + grr_results):
            link = (r.get("link") or "")
            if not link:
                continue
            if not args.allow_any_domain and not is_allowed_host(link):
                continue
            if ".pdf" not in link.lower():
                continue
            combined.append(r)

        # Validate candidates by downloading and checking PDF text against title (unless skipped)
        validated: List[Dict[str, Any]] = []
        
        # Use the global validator instead of creating a new one each time
        sem_validator = global_sem_validator
        
        # Download and extract all PDFs first for batch processing
        pdf_data: List[Tuple[Dict[str, Any], str]] = []  # (result_dict, extracted_text)
        failed_downloads = 0
        failed_extractions = 0
        
        for r in combined:
            if args.no_validate_pdf:
                r_copy = dict(r)
                r_copy["_match_score"] = 0.0
                r_copy["_doc_kind"] = classify_doc_type(r.get("link", ""), r.get("title")) or ""
                validated.append(r_copy)
                continue
            
            pdf_url = r.get("link", "")
            pdf_bytes = download_pdf(pdf_url)
            
            if not pdf_bytes:
                failed_downloads += 1
                continue
            
            # Intentar extracción normal primero
            text = extract_pdf_text_first_pages(pdf_bytes, max_pages=2, quiet=True)
            
            # Si falla o el texto es muy corto, intentar OCR avanzado
            if not text or len(text.strip()) < 50:
                ocr_title = extract_title_from_first_page_ocr(pdf_bytes)
                if ocr_title:
                    # Usar el título OCR como texto principal
                    text = ocr_title + "\n" + (text or "")
                    print(f"  🔍 OCR usado para: {pdf_url[:60]}...")
                elif not text:
                    # Si todo falló, registrar como falla de extracción
                    failed_extractions += 1
                    continue
            
            pdf_data.append((r, text))
        
        # Log summary of failures if any
        if failed_downloads > 0 or failed_extractions > 0:
            print(f"  [INFO] Descargados: {len(pdf_data)}, Falló descarga: {failed_downloads}, Falló extracción: {failed_extractions}")
        
        # GPU batch processing: compute all title matches + semantic similarities at once
        if sem_validator is not None and pdf_data:
            # Prepare batch data: collect all candidate lines from all PDFs
            batch_titles: List[str] = []
            batch_candidates: List[List[str]] = []
            for _, text in pdf_data:
                lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                lines = lines[: args.max_embed_lines]
                batch_titles.append(title)  # Same title for all candidates in this GPC
                batch_candidates.append(lines)
            
            # Single GPU call for all PDFs
            semantic_scores = sem_validator.batch_similarity(batch_titles, batch_candidates)
        else:
            semantic_scores = [0.0] * len(pdf_data)
        
        # Now process results with precomputed semantic scores
        for idx, (r, text) in enumerate(pdf_data):
            match = title_match_score(title, text)
            # Combine fuzzy + semantic if embeddings enabled
            semantic_score = 0.0
            if sem_validator is not None:
                sem_sim = semantic_scores[idx]
                semantic_score = sem_sim
                match = max(match, 0.5 * match + 0.7 * sem_sim)
            
            if match < args.min_title_match:
                continue
            
            # 🤖 IMPROVED: Use AI classification instead of simple keyword matching
            kind = classify_doc_type(r.get("link", ""), r.get("title"))
            ai_classification = None
            ai_confidence = 0.0
            
            # If classification unclear from URL/title AND semantic validator has classification enabled
            if not kind and sem_validator is not None and sem_validator.enable_classification:
                ai_classification, ai_confidence = sem_validator.classify_document_type(text)
                # Use AI classification if confidence > 60%
                if ai_confidence >= 0.6:
                    kind = ai_classification
            
            # Fallback to simple keyword search if still unclear
            if not kind:
                tnorm = normalize_text(text[:600])
                if "guia de referencia rapida" in tnorm or "referencia rapida" in tnorm:
                    kind = "GRR"
                elif "guia de evidencias" in tnorm or "evidencias y recomendaciones" in tnorm:
                    kind = "GER"
            
            r_copy = dict(r)
            r_copy["_match_score"] = match
            r_copy["_semantic_score"] = semantic_score
            r_copy["_doc_kind"] = kind or ""
            r_copy["_ai_classification"] = ai_classification
            r_copy["_ai_confidence"] = ai_confidence
            validated.append(r_copy)

        # Select best GER and best GRR independently by classification + host score + match score
        ger_candidates: List[Tuple[float, Dict[str, Any]]] = []
        grr_candidates: List[Tuple[float, Dict[str, Any]]] = []
        for r in validated:
            link = r.get("link", "")
            kind = r.get("_doc_kind") or classify_doc_type(link, r.get("title"))
            score = host_score(link) + float(r.get("_match_score", 0.0)) * 10.0
            if kind == "GER":
                ger_candidates.append((score, r))
            elif kind == "GRR":
                grr_candidates.append((score, r))
            else:
                # If unclear, use as weak candidate for both
                ger_candidates.append((score - 2, r))
                grr_candidates.append((score - 2, r))

        ger_candidates.sort(key=lambda x: x[0], reverse=True)
        grr_candidates.sort(key=lambda x: x[0], reverse=True)

        # STEP 3: SELECTION LOGIC - CENETEC > IMSS priority
        # If CENETEC results found, they REPLACE IMSS results
        cenetec_ger_url = None
        cenetec_grr_url = None
        cenetec_ger_source = None
        cenetec_grr_source = None
        cenetec_ger_confidence = 0.0
        cenetec_grr_confidence = 0.0
        
        if ger_candidates:
            r0 = ger_candidates[0][1]
            cenetec_ger_url = r0.get("link")
            cenetec_ger_source = r0.get("title")
            cenetec_ger_confidence = float(10 + ger_candidates[0][0])
        if grr_candidates:
            r0 = grr_candidates[0][1]
            cenetec_grr_url = r0.get("link")
            cenetec_grr_source = r0.get("title")
            cenetec_grr_confidence = float(10 + grr_candidates[0][0])
        
        # Decision: CENETEC > IMSS (if prefer-cenetec flag is True)
        if args.prefer_cenetec and found_in_imss:
            # We have IMSS results stored in row
            # Replace with CENETEC if found (higher quality)
            replaced_ger = False
            replaced_grr = False
            
            if cenetec_ger_url:
                # CENETEC found for GER - REPLACE IMSS
                if row.ger_url:  # Had IMSS
                    print(f"  ✅ REEMPLAZANDO GER: IMSS → CENETEC (más actualizado)")
                    replaced_ger = True
                row.ger_url = cenetec_ger_url
                row.ger_source = "CENETEC_API"
                row.ger_confidence = cenetec_ger_confidence
            
            if cenetec_grr_url:
                # CENETEC found for GRR - REPLACE IMSS
                if row.grr_url:  # Had IMSS
                    print(f"  ✅ REEMPLAZANDO GRR: IMSS → CENETEC (más actualizado)")
                    replaced_grr = True
                row.grr_url = cenetec_grr_url
                row.grr_source = "CENETEC_API"
                row.grr_confidence = cenetec_grr_confidence
            
            # If CENETEC didn't find something, keep IMSS (already in row)
            if not cenetec_ger_url and imss_ger_url:
                print(f"  ℹ️  Manteniendo GER de IMSS (no encontrado en CENETEC)")
            if not cenetec_grr_url and imss_grr_url:
                print(f"  ℹ️  Manteniendo GRR de IMSS (no encontrado en CENETEC)")
        
        elif not found_in_imss:
            # No IMSS results, use CENETEC directly
            if cenetec_ger_url:
                row.ger_url = cenetec_ger_url
                row.ger_source = "CENETEC_API"
                row.ger_confidence = cenetec_ger_confidence
            if cenetec_grr_url:
                row.grr_url = cenetec_grr_url
                row.grr_source = "CENETEC_API"
                row.grr_confidence = cenetec_grr_confidence
        
        # HTTP HEAD check for final URLs
        if row.ger_url and not args.no_head:
            row.ger_status = http_head_status(row.ger_url)
        if row.grr_url and not args.no_head:
            row.grr_status = http_head_status(row.grr_url)

        # 🔥 VALIDACIÓN DE COHERENCIA: GER y GRR deben tener el MISMO número de GPC
        if row.ger_url and row.grr_url:
            ger_num = extract_gpc_number(row.ger_url)
            grr_num = extract_gpc_number(row.grr_url)
            
            if ger_num and grr_num and ger_num != grr_num:
                print(f"  ⚠️  INCOHERENCIA DETECTADA: GER #{ger_num} ≠ GRR #{grr_num}")
                print(f"      GER: {row.ger_url}")
                print(f"      GRR: {row.grr_url}")
                
                # Decidir cuál mantener (el de mayor confianza)
                if row.ger_confidence > row.grr_confidence:
                    print(f"  🔧 Manteniendo GER (conf {row.ger_confidence:.1f}), descartando GRR")
                    row.grr_url = None
                    row.grr_source = None
                    row.grr_confidence = 0.0
                else:
                    print(f"  🔧 Manteniendo GRR (conf {row.grr_confidence:.1f}), descartando GER")
                    row.ger_url = None
                    row.ger_source = None
                    row.ger_confidence = 0.0

        # SMART INFERENCE: If one is found, try to infer the other from URL patterns
        # Works for CENETEC-DIFUSION (ER.pdf ↔ RR.pdf) and IMSS (xxxGER.pdf ↔ xxxGRR.pdf)
        if row.ger_url and not row.grr_url:
            inferred_grr = infer_complementary_url(row.ger_url, "GER", "GRR")
            if inferred_grr:
                # Validar HTTP HEAD antes de agregar
                if not args.no_head:
                    status = http_head_status(inferred_grr)
                    if status == 200:
                        row.grr_url = inferred_grr
                        row.grr_source = f"(inferido de {row.ger_url.split('/')[-1]})"
                        row.grr_confidence = row.ger_confidence * 0.9
                        print(f"  🔗 GRR inferido automáticamente: {inferred_grr}")
                    else:
                        print(f"  ❌ GRR inferido no existe (HTTP {status}): {inferred_grr}")
                else:
                    # Sin validación HTTP, confiar en la inferencia
                    row.grr_url = inferred_grr
                    row.grr_source = f"(inferido de {row.ger_url.split('/')[-1]})"
                    row.grr_confidence = row.ger_confidence * 0.9
                    print(f"  🔗 GRR inferido: {inferred_grr}")
        
        if row.grr_url and not row.ger_url:
            inferred_ger = infer_complementary_url(row.grr_url, "GRR", "GER")
            if inferred_ger:
                if not args.no_head:
                    status = http_head_status(inferred_ger)
                    if status == 200:
                        row.ger_url = inferred_ger
                        row.ger_source = f"(inferido de {row.grr_url.split('/')[-1]})"
                        row.ger_confidence = row.grr_confidence * 0.9
                        print(f"  🔗 GER inferido automáticamente: {inferred_ger}")
                    else:
                        print(f"  ❌ GER inferido no existe (HTTP {status}): {inferred_ger}")
                else:
                    row.ger_url = inferred_ger
                    row.ger_source = f"(inferido de {row.grr_url.split('/')[-1]})"
                    row.ger_confidence = row.grr_confidence * 0.9
                    print(f"  🔗 GER inferido: {inferred_ger}")

        rows.append(row)

        # Show results
        ger_display = row.ger_url or '-'
        grr_display = row.grr_url or '-'
        print(f"[{i}/{len(titles)}] {title}\n  GER: {ger_display} (conf {row.ger_confidence:.1f})\n  GRR: {grr_display} (conf {row.grr_confidence:.1f})")
        
        # In aggressive mode, if both are missing, try alternative search strategies
        if args.aggressive and not row.ger_url and not row.grr_url:
            print(f"  ⚠️  Modo agresivo: Ningún resultado encontrado, intentando estrategias alternativas...")
            
            # Strategy 1: Remove year/edition info
            simple_title = re.sub(r'\d{4}', '', title).strip()
            simple_title = re.sub(r'\b(primera|segunda|tercera|cuarta|quinta)\s+(edición|edicion)\b', '', simple_title, flags=re.IGNORECASE).strip()
            
            # Strategy 2: Try very broad search on key domains
            if len(simple_title) > 10:
                # Build simpler queries focusing on CENETEC-DIFUSION and IMSS
                alt_q_ger = f'"{simple_title}" GER filetype:pdf (site:cenetec-difusion.com OR site:imss.gob.mx OR site:cenetec.salud.gob.mx)'
                alt_q_grr = f'"{simple_title}" GRR filetype:pdf (site:cenetec-difusion.com OR site:imss.gob.mx OR site:cenetec.salud.gob.mx)'
                
                print(f"  🔄 Estrategia 1: Título simplificado ('{simple_title[:40]}...')")
                
                try:
                    alt_ger = provider.search(alt_q_ger)
                    alt_grr = provider.search(alt_q_grr)
                    
                    if alt_ger or alt_grr:
                        print(f"  ✓ Encontrados {len(alt_ger)} GER y {len(alt_grr)} GRR")
                        # Show first result as suggestion
                        if alt_ger:
                            print(f"    💡 GER sugerido: {alt_ger[0].get('link', 'N/A')[:70]}...")
                        if alt_grr:
                            print(f"    💡 GRR sugerido: {alt_grr[0].get('link', 'N/A')[:70]}...")
                except Exception as e:
                    pass
            
            # Strategy 3: Try without quotes for very flexible matching
            keywords = ' '.join([w for w in simple_title.split() if len(w) > 3][:5])  # First 5 significant words
            if keywords:
                broad_q = f'{keywords} GPC filetype:pdf (site:cenetec-difusion.com OR site:imss.gob.mx)'
                print(f"  🔄 Estrategia 2: Búsqueda amplia ('{keywords[:40]}...')")
                
                try:
                    broad_results = provider.search(broad_q)
                    if broad_results:
                        print(f"  ✓ Encontrados {len(broad_results)} resultados amplios")
                        print(f"    💡 Primer resultado: {broad_results[0].get('link', 'N/A')[:70]}...")
                except Exception:
                    pass
        
        time.sleep(args.sleep)

    write_outputs(rows)
    print(f"\nWrote: {OUT_CSV}, {OUT_JSON}, and {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
